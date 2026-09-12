"""Automation api."""

from __future__ import annotations

import unittest

from pnc_automation.app.entrypoints.api import AutomationApi
from pnc_automation.app.automation.engine.task import TaskId

from tests.support.entrypoints.castle_targeting.runtime_castle_targeting_fixtures import (
    RuntimeCastleTargetingFixtures,
)
from tests.support.entrypoints.castle_targeting.fake_application_runner import (
    _FakeApplicationRunner,
)
from tests.support.entrypoints.castle_targeting.make_failed_run_result import (
    _make_failed_run_result,
)


class AutomationApiTests(RuntimeCastleTargetingFixtures, unittest.TestCase):
    """Proves automation api."""

    def test_python_use_account_prepares_session_with_optional_castle(self) -> None:
        """Delegates context entry to the shared session-preparation path."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a", castle=self.target_castle) as session:
            self.assertIsNotNone(session.preparation_result)

        self.assertEqual(fake_runner.prepare_calls, [("account_a", self.target_castle)])

    def test_python_use_account_releases_reservation_when_preparation_reports_failure(self) -> None:
        """Closes the physical reservation when preparation returns a failed step result."""

        fake_runner = _FakeApplicationRunner(preparation_result=_make_failed_run_result())
        api = AutomationApi(application=fake_runner)

        with self.assertRaisesRegex(RuntimeError, "preparation failed"):
            with api.use_account("account_a"):
                self.fail("failed preparation must not expose an active session")

        self.assertEqual(len(fake_runner.reservations), 1)
        self.assertTrue(fake_runner.reservations[0].closed)

    def test_python_use_account_exit_performs_no_cleanup(self) -> None:
        """Leaves the live session untouched on context exit by default."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a"):
            pass

        self.assertEqual(fake_runner.prepare_calls, [("account_a", None)])
        self.assertEqual(fake_runner.task_calls, [])

    def test_python_direct_task_calls_use_current_castle_semantics(self) -> None:
        """Runs direct task wrappers without injecting hidden castle switching."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        result = api.research(account_id="account_a", priority=["economy"])

        self.assertEqual(result.task_id, TaskId.RESEARCH)
        self.assertEqual(fake_runner.task_calls, [(TaskId.RESEARCH, "account_a", {"priority": ["economy"]})])
        self.assertEqual(fake_runner.prepare_calls, [])

    def test_python_generic_run_task_no_longer_accepts_castle_targeting(self) -> None:
        """Keeps explicit castle alignment out of the public direct-call task API."""

        api = AutomationApi(application=_FakeApplicationRunner())

        with self.assertRaises(TypeError):
            api.run_task(account_id="account_a", task_id=TaskId.RESEARCH, castle=self.target_castle)

    def test_python_building_construct_forwards_exact_target(self) -> None:
        """Exposes construction through the canonical direct task runner."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        api.building_construct(account_id="account_a", building="farm")

        self.assertEqual(
            fake_runner.task_calls,
            [(TaskId.BUILDING_CONSTRUCT, "account_a", {"building": "farm"})],
        )

    def test_python_direct_task_calls_resolve_account_from_active_context(self) -> None:
        """Allows direct task wrappers to use the currently active `use_account(...)` scope."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a", castle=self.target_castle):
            api.building_upgrade(priority=["castle"])

        self.assertEqual(
            fake_runner.task_calls,
            [
                (
                    TaskId.BUILDING_UPGRADE,
                    "account_a",
                    {
                        "priority": ["castle"],
                        "allow_speedups": False,
                        "prerequisite_mode": "fail",
                        "allow_premium_material_purchases": False,
                    },
                )
            ],
        )

    def test_python_generic_run_task_resolves_account_from_active_context(self) -> None:
        """Allows the generic direct-call task API to reuse the active prepared session scope."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a"):
            api.run_task(task_id=TaskId.RESEARCH, params={"priority": ["economy"]})

        self.assertEqual(fake_runner.task_calls, [(TaskId.RESEARCH, "account_a", {"priority": ["economy"]})])
