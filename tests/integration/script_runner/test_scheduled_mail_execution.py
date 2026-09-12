"""Scheduled mail execution: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from pnc_automation.app.automation.engine.script_runner import ScriptRunner
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.loader import load_app_config
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance

from tests.support.core.logging import build_logger
from tests.support.entrypoints.scheduled_mail.fake_adb_client import _FakeAdbClient
from tests.support.entrypoints.scheduled_mail.fake_instance_resolver import _FakeInstanceResolver
from tests.support.entrypoints.scheduled_mail.make_run_result import _make_run_result
from tests.support.entrypoints.scheduled_mail.write_accounts_config import _write_accounts_config
from tests.support.entrypoints.scheduled_mail.write_mail_definitions import _write_mail_definitions
from tests.support.entrypoints.scheduled_mail.write_mail_schedules import _write_mail_schedules


class ScheduledMailExecutionTests(unittest.TestCase):
    """Proves scheduled mail execution."""

    def test_script_runner_run_mail_schedules_short_circuits_when_nothing_is_due(self) -> None:
        """Returns a successful no-op result without touching the emulator when the hour is empty."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            _write_accounts_config(root)
            _write_mail_definitions(root)
            _write_mail_schedules(root)
            config = load_app_config(_write_accounts_config(root))
            instance = config.instances[0]
            account = config.accounts[0]
            resolver = _FakeInstanceResolver(
                resolved_instance=BlueStacksInstance(
                    id=instance.id,
                    display_name=instance.display_name,
                    device_id="127.0.0.1:5566",
                    app_package=instance.app_package,
                )
            )
            adb_client = _FakeAdbClient()
            runner = ScriptRunner(
                config=config,
                task_registry=object(),
                screenshot_service=object(),
                observation_builder=object(),
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=adb_client,
                instance_resolver=resolver,
                logger=build_logger(),
            )

            result = runner.run_mail_schedules(
                account_id=account.id,
                scheduled_for_utc=datetime(2026, 3, 30, 4, 0, tzinfo=UTC),
            )

        self.assertEqual(result.account_id, account.id)
        self.assertEqual(result.script_name, "generated_mail_schedule_20260330T040000Z")
        self.assertEqual(result.steps, ())
        self.assertEqual(adb_client.connect_calls, [])
        self.assertEqual(resolver.requested_configs, [])

    def test_script_runner_run_mail_schedules_rejects_unknown_account_during_empty_hour(self) -> None:
        """Fails fast on unknown accounts even when no schedules are due for that hour."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = _write_accounts_config(root)
            _write_mail_definitions(root)
            _write_mail_schedules(root)
            config = load_app_config(config_path)
            instance = config.instances[0]
            resolver = _FakeInstanceResolver(
                resolved_instance=BlueStacksInstance(
                    id=instance.id,
                    display_name=instance.display_name,
                    device_id="127.0.0.1:5566",
                    app_package=instance.app_package,
                )
            )
            adb_client = _FakeAdbClient()
            runner = ScriptRunner(
                config=config,
                task_registry=object(),
                screenshot_service=object(),
                observation_builder=object(),
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=adb_client,
                instance_resolver=resolver,
                logger=build_logger(),
            )

            with self.assertRaises(ConfigurationError):
                runner.run_mail_schedules(
                    account_id="missing_account",
                    scheduled_for_utc=datetime(2026, 3, 30, 4, 0, tzinfo=UTC),
                )

        self.assertEqual(adb_client.connect_calls, [])
        self.assertEqual(resolver.requested_configs, [])

    def test_script_runner_run_mail_schedules_rejects_non_utc_runtime_timestamp(self) -> None:
        """Rejects runtime replay timestamps whose original offset is not already UTC."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = _write_accounts_config(root)
            _write_mail_definitions(root)
            _write_mail_schedules(root)
            config = load_app_config(config_path)
            runner = ScriptRunner(
                config=config,
                task_registry=object(),
                screenshot_service=object(),
                observation_builder=object(),
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=object(),
                instance_resolver=object(),
                logger=build_logger(),
            )

            with self.assertRaises(ConfigurationError):
                runner.run_mail_schedules(
                    account_id="account_a",
                    scheduled_for_utc=datetime.fromisoformat("2026-03-30T05:00:00+02:00"),
                )

    def test_script_runner_run_mail_schedules_fails_fast_when_lazy_loaded_catalog_is_invalid(self) -> None:
        """Fails on malformed optional scheduled-mail files only when scheduled-mail execution is invoked."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = _write_accounts_config(root)
            _write_mail_definitions(root)
            malformed_schedules_path = root / "mail_schedules.yaml"
            malformed_schedules_path.write_text(
                textwrap.dedent(
                    """
                    rotation:
                      cycle_days: 14
                      start_utc: 2026-03-30T00:00:00Z
                    mail_schedules:
                      - id: mailschedule_1
                        day_indices: [0]
                        hour_utc: 24
                        mail_ids: [alliance_reset]
                    """
                ).strip(),
                encoding="utf-8",
            )
            config = load_app_config(config_path)
            instance = config.instances[0]
            resolver = _FakeInstanceResolver(
                resolved_instance=BlueStacksInstance(
                    id=instance.id,
                    display_name=instance.display_name,
                    device_id="127.0.0.1:5566",
                    app_package=instance.app_package,
                )
            )
            adb_client = _FakeAdbClient()
            runner = ScriptRunner(
                config=config,
                task_registry=object(),
                screenshot_service=object(),
                observation_builder=object(),
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=adb_client,
                instance_resolver=resolver,
                logger=build_logger(),
            )

            with self.assertRaises(ConfigurationError):
                runner.run_mail_schedules(account_id="account_a")

        self.assertEqual(adb_client.connect_calls, [])
        self.assertEqual(resolver.requested_configs, [])

    def test_script_runner_run_mail_schedules_builds_and_executes_generated_script(self) -> None:
        """Expands due schedules into a generated canonical send_mail script before execution."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = _write_accounts_config(root)
            _write_mail_definitions(root)
            _write_mail_schedules(root)
            config = load_app_config(config_path)
            runner = ScriptRunner(
                config=config,
                task_registry=object(),
                screenshot_service=object(),
                observation_builder=object(),
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=object(),
                instance_resolver=object(),
                logger=build_logger(),
            )
            run_result = _make_run_result(script_name="generated_mail_schedule_20260330T050000Z")

            with patch.object(ScriptRunner, "_run_script_for_account", return_value=run_result) as run_script:
                result = runner.run_mail_schedules(
                    account_id="account_a",
                    scheduled_for_utc=datetime(2026, 3, 30, 5, 30, tzinfo=UTC),
                )

        self.assertIs(result, run_result)
        script = run_script.call_args.kwargs["script"]
        account = run_script.call_args.kwargs["account"]
        self.assertEqual(account.id, "account_a")
        self.assertEqual(script.name, "generated_mail_schedule_20260330T050000Z")
        self.assertEqual([step.task for step in script.steps], [TaskId.ENSURE_GAME_RUNNING, TaskId.LOGIN, TaskId.SEND_MAIL, TaskId.SEND_MAIL])
        self.assertEqual(script.steps[2].castle_ref, "main")
        self.assertEqual(script.steps[3].params["player_name"], "SomePlayer")
        self.assertEqual(script.steps[2].provenance, {"mail_id": "alliance_reset", "schedule_id": "mailschedule_1"})
        self.assertEqual(script.steps[3].provenance, {"mail_id": "player_followup", "schedule_id": "mailschedule_1"})
