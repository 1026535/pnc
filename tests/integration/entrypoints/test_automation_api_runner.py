"""Automation api runner: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pnc_automation.app.entrypoints.api import AutomationApi
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.core.infra.emulator.session import BlueStacksSessionCleanupPolicy

from tests.support.entrypoints.castle_targeting.runtime_castle_targeting_fixtures import (
    RuntimeCastleTargetingFixtures,
)
from tests.support.entrypoints.castle_targeting.fake_application_runner import (
    _FakeApplicationRunner,
)
from tests.support.entrypoints.castle_targeting.real_lease_application_runner import (
    _RealLeaseApplicationRunner,
)


class AutomationApiRunnerTests(RuntimeCastleTargetingFixtures, unittest.TestCase):
    """Proves automation api runner."""

    def test_python_use_account_holds_real_lease_through_prepare_and_action(self) -> None:
        """Exercises the public API scope against a real temp lease and competing registry."""

        with tempfile.TemporaryDirectory() as temp_directory:
            application = _RealLeaseApplicationRunner(Path(temp_directory))
            api = AutomationApi(application=application)

            with api.use_account("account_a") as session:
                session.research(priority=["economy"])

            application.probe_after_scope()
            self.assertTrue(application.competitor_acquired_after_scope)

    def test_python_use_account_propagates_one_cleanup_policy_across_the_phase(self) -> None:
        """Applies the outer cleanup decision to preparation and every dependent action."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)
        policy = BlueStacksSessionCleanupPolicy.close_at_phase_end(
            close_preexisting_instance=True,
        )

        with api.use_account("account_a", session_cleanup_policy=policy) as session:
            session.research(priority=["economy"])

        self.assertEqual(fake_runner.prepare_cleanup_policies, [policy])
        self.assertEqual(fake_runner.task_cleanup_policies, [policy])

    def test_python_use_account_holds_real_lease_between_dependent_actions(self) -> None:
        """Prevents another process-shaped registry from entering between two dependent actions."""

        with tempfile.TemporaryDirectory() as temp_directory:
            application = _RealLeaseApplicationRunner(Path(temp_directory))
            api = AutomationApi(application=application)

            with api.use_account("account_a") as session:
                session.research(priority=["economy"])
                session.building_construct(building="farm")

            application.probe_after_scope()
            self.assertTrue(application.competitor_acquired_after_scope)

    def test_python_reserve_accounts_holds_scope_for_multi_step_workflow(self) -> None:
        """Provides an explicit reservation for dependent calls without account preparation helpers."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.reserve_accounts(("account_a",)):
            api.research(priority=["economy"])
            api.building_construct(building="farm")

        self.assertEqual(len(fake_runner.reservations), 1)
        self.assertTrue(fake_runner.reservations[0].closed)
        self.assertEqual(
            fake_runner.task_calls,
            [
                (TaskId.RESEARCH, "account_a", {"priority": ["economy"]}),
                (TaskId.BUILDING_CONSTRUCT, "account_a", {"building": "farm"}),
            ],
        )

    def test_python_reservation_rejects_account_outside_declared_bundle(self) -> None:
        """Fails before execution when a workflow tries to escape its declared account bundle."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.reserve_accounts(("account_a",)):
            with self.assertRaisesRegex(RuntimeError, "outside the active workflow reservation"):
                api.research(account_id="account_b")

        self.assertTrue(fake_runner.reservations[0].closed)
        self.assertEqual(fake_runner.task_calls, [])

    def test_python_reservation_rejects_incremental_bundle_expansion(self) -> None:
        """Requires all accounts to be declared before a workflow acquires its first instance."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.reserve_accounts(("account_a",)):
            with self.assertRaisesRegex(RuntimeError, "Cannot expand an active workflow reservation"):
                with api.reserve_accounts(("account_a", "account_b")):
                    pass

        self.assertEqual(len(fake_runner.reservations), 1)
        self.assertTrue(fake_runner.reservations[0].closed)

    def test_python_use_account_failed_preparation_releases_real_lease(self) -> None:
        """Allows a competitor to acquire immediately after a failed public API preparation."""

        with tempfile.TemporaryDirectory() as temp_directory:
            application = _RealLeaseApplicationRunner(Path(temp_directory), preparation_failed=True)
            api = AutomationApi(application=application)

            with self.assertRaisesRegex(RuntimeError, "preparation failed"):
                with api.use_account("account_a"):
                    self.fail("failed preparation must not enter the API scope")

            application.probe_after_scope()
            self.assertTrue(application.competitor_acquired_after_scope)

    def test_python_building_upgrade_loads_priority_file(self) -> None:
        """Allows direct building-upgrade calls to load their ordered priority list from a text file."""

        with tempfile.TemporaryDirectory() as temp_directory:
            priority_file = Path(temp_directory) / "buildings.txt"
            priority_file.write_text("institute\nwarehouse\n", encoding="utf-8")
            fake_runner = _FakeApplicationRunner()
            api = AutomationApi(application=fake_runner)

            api.building_upgrade(account_id="account_a", priority_file=str(priority_file))

        self.assertEqual(
            fake_runner.task_calls,
            [
                (
                    TaskId.BUILDING_UPGRADE,
                    "account_a",
                    {
                        "priority": ["institute", "warehouse"],
                        "allow_speedups": False,
                        "prerequisite_mode": "fail",
                        "allow_premium_material_purchases": False,
                    },
                )
            ],
        )
