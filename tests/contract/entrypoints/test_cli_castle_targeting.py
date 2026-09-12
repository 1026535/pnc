"""Cli castle targeting."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pnc_automation.core.vision.observation_policy import ObservationMode
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.entrypoints.cli import main as cli_main

from tests.support.entrypoints.castle_targeting.runtime_castle_targeting_fixtures import (
    RuntimeCastleTargetingFixtures,
)
from tests.support.entrypoints.castle_targeting.fake_application_runner import (
    _FakeApplicationRunner,
)
from tests.support.entrypoints.castle_targeting.make_failed_run_result import (
    _make_failed_run_result,
)


class CliCastleTargetingTests(RuntimeCastleTargetingFixtures, unittest.TestCase):
    """Proves cli castle targeting."""

    def test_cli_login_without_castle_reuses_session_preparation_service(self) -> None:
        """Calls the shared preparation path without mutating the current castle when no target is given."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
            exit_code = cli_main(["login", "--account", "account_a", "--config", "config/accounts.yaml"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runner.prepare_calls, [("account_a", None)])
        self.assertEqual(fake_runner.task_calls, [])

    def test_cli_construct_runs_the_distinct_construction_task(self) -> None:
        """Keeps construction separate from the existing building-upgrade command."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner), patch(
            "builtins.print"
        ):
            exit_code = cli_main(
                ["construct", "--account", "account_a", "--building", "farm", "--config", "config/accounts.yaml"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            fake_runner.task_calls,
            [(TaskId.BUILDING_CONSTRUCT, "account_a", {"building": "farm"})],
        )

    def test_cli_login_with_castle_reuses_session_preparation_service(self) -> None:
        """Calls the shared preparation path with the explicit CLI castle target when one is provided."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
            exit_code = cli_main(
                [
                    "login",
                    "--account",
                    "account_a",
                    "--config",
                    "config/accounts.yaml",
                    "--kingdom",
                    "K230",
                    "--castle-name",
                    "Main",
                    "--castle-level",
                    "8",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runner.prepare_calls, [("account_a", self.target_castle)])
        self.assertEqual(fake_runner.task_calls, [])

    def test_cli_build_without_castle_runs_direct_build_task(self) -> None:
        """Uses the direct build command without forcing session preparation when no explicit castle target was given."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
            exit_code = cli_main(
                [
                    "build",
                    "--account",
                    "account_a",
                    "--config",
                    "config/accounts.yaml",
                    "--priority",
                    "institute",
                    "warehouse",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runner.prepare_calls, [])
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

    def test_cli_build_with_castle_and_priority_file_prepares_then_runs_direct_build_task(self) -> None:
        """Allows one direct build invocation to load priorities from a file after explicit castle preparation."""

        with tempfile.TemporaryDirectory() as temp_directory:
            priority_file = Path(temp_directory) / "buildings.txt"
            priority_file.write_text("institute\nwarehouse\n", encoding="utf-8")
            fake_runner = _FakeApplicationRunner()
            with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
                exit_code = cli_main(
                    [
                        "build",
                        "--account",
                        "account_a",
                        "--config",
                        "config/accounts.yaml",
                        "--kingdom",
                        "K230",
                        "--castle-name",
                        "Main",
                        "--castle-level",
                        "8",
                        "--priority-file",
                        str(priority_file),
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runner.prepare_calls, [("account_a", self.target_castle)])
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

    def test_cli_prepare_then_action_releases_reservation_when_preparation_reports_failure(self) -> None:
        """Rejects a failed preparation result before running the dependent CLI task."""

        fake_runner = _FakeApplicationRunner(preparation_result=_make_failed_run_result())
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner):
            with self.assertRaisesRegex(RuntimeError, "preparation failed"):
                cli_main(
                    [
                        "build",
                        "--account",
                        "account_a",
                        "--config",
                        "config/accounts.yaml",
                        "--kingdom",
                        "K230",
                        "--castle-name",
                        "Main",
                        "--castle-level",
                        "8",
                        "--priority",
                        "institute",
                    ]
                )

        self.assertEqual(len(fake_runner.reservations), 1)
        self.assertTrue(fake_runner.reservations[0].closed)
        self.assertEqual(fake_runner.task_calls, [])

    def test_cli_legacy_run_flags_still_route_through_the_shared_run_path(self) -> None:
        """Keeps the flag-only legacy invocation shape while executing the canonical run command path."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
            exit_code = cli_main(
                ["--account", "account_a", "--config", "config/accounts.yaml", "--script", "scripts/daily.yaml"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runner.run_calls, [("account_a", "scripts/daily.yaml", None)])

    def test_cli_forwards_ordered_runtime_castle_refs(self) -> None:
        """Binds one canonical routine to repeated account-scoped aliases from the CLI."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner), patch(
            "builtins.print"
        ):
            exit_code = cli_main(
                [
                    "run",
                    "--account",
                    "account_a",
                    "--config",
                    "config/accounts.yaml",
                    "--script",
                    "scripts/daily.yaml",
                    "--castle-ref",
                    "main",
                    "--castle-ref",
                    "farm",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            fake_runner.run_calls,
            [("account_a", "scripts/daily.yaml", ["main", "farm"])],
        )

    def test_cli_passes_observation_mode_override_to_application_builder(self) -> None:
        """Threads the explicit CLI observation-mode override into the canonical application builder."""

        fake_runner = _FakeApplicationRunner()
        with (
            patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner) as build_runner,
            patch("builtins.print"),
        ):
            exit_code = cli_main(
                [
                    "run",
                    "--account",
                    "account_a",
                    "--config",
                    "config/accounts.yaml",
                    "--script",
                    "scripts/daily.yaml",
                    "--observation-mode",
                    "light",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(build_runner.call_args.kwargs["observation_mode"], ObservationMode.LIGHT)
