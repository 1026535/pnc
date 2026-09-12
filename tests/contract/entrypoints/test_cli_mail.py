"""Cli mail."""

from __future__ import annotations

from datetime import UTC, datetime
import unittest
from unittest.mock import patch

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.entrypoints.cli import main as cli_main

from tests.support.entrypoints.scheduled_mail.fake_application_runner import _FakeApplicationRunner


class CliMailTests(unittest.TestCase):
    """Proves cli mail."""

    def test_cli_send_mail_translates_flat_arguments_to_canonical_task_params(self) -> None:
        """Builds the nested canonical profile_route mapping before delegating to send_mail."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
            exit_code = cli_main(
                [
                    "send-mail",
                    "--account",
                    "account_a",
                    "--config",
                    "config/accounts.yaml",
                    "--recipient-kind",
                    "player",
                    "--profile-route-kind",
                    "alliance_member",
                    "--profile-route-player-name",
                    "SomePlayer",
                    "--subject",
                    "Hi",
                    "--body",
                    "Checking in",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_runner.prepare_calls, [])
        self.assertEqual(
            fake_runner.task_calls,
            [
                (
                    TaskId.SEND_MAIL,
                    "account_a",
                    {
                        "recipient_kind": "player",
                        "subject": "Hi",
                        "body": "Checking in",
                        "profile_route": {"kind": "alliance_member", "player_name": "SomePlayer"},
                    },
                )
            ],
        )

    def test_cli_run_mail_schedules_translates_schedule_filters_and_replay_time(self) -> None:
        """Forwards direct scheduled-mail CLI inputs into the application-level runtime surface."""

        fake_runner = _FakeApplicationRunner()
        with patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=fake_runner), patch("builtins.print"):
            exit_code = cli_main(
                [
                    "run-mail-schedules",
                    "--account",
                    "account_a",
                    "--config",
                    "config/accounts.yaml",
                    "--schedule-id",
                    "mailschedule_2",
                    "--schedule-id",
                    "mailschedule_1",
                    "--scheduled-for-utc",
                    "2026-03-31T05:00:00Z",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            fake_runner.mail_schedule_calls,
            [("account_a", ["mailschedule_2", "mailschedule_1"], datetime(2026, 3, 31, 5, 0, tzinfo=UTC))],
        )
