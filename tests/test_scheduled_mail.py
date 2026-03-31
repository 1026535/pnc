"""Scheduled-mail authoring, runtime, API, and CLI tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.script_runner import ScriptRunner
from pnc_automation.app.automation.engine.task import TaskId, TaskResult
from pnc_automation.app.authoring.config.loader import load_app_config
from pnc_automation.app.authoring.config.models import (
    BlueStacksInstanceConfig,
    CastleIdentity,
)
from pnc_automation.app.authoring.mail.loader import (
    build_generated_send_mail_script,
    load_mail_schedule_catalog,
    resolve_due_mail_definitions,
)
from pnc_automation.app.authoring.mail.models import AuthoredMailDefinition
from pnc_automation.app.entrypoints.api import AutomationApi
from pnc_automation.app.entrypoints.cli import main as cli_main
from pnc_automation.app.pnc.domain.mail import MailRecipientKind, PlayerProfileRoute, SendMailParams
from pnc_automation.app.pnc.enums.mail import PlayerProfileRouteKind
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.adb.command_result import CommandResult
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from tests.test_support import build_logger


class ScheduledMailCatalogTests(unittest.TestCase):
    """Validates authored scheduled-mail loading and deterministic due resolution."""

    def test_load_mail_schedule_catalog_parses_valid_files(self) -> None:
        """Loads reusable mail definitions and schedules through the canonical parser."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog = load_mail_schedule_catalog(
                definitions_path=_write_mail_definitions(root),
                schedules_path=_write_mail_schedules(root),
            )

        self.assertEqual(catalog.start_utc, datetime(2026, 3, 30, 0, 0, tzinfo=UTC))
        self.assertEqual([definition.id for definition in catalog.definitions], ["alliance_reset", "player_followup"])
        self.assertEqual([schedule.id for schedule in catalog.schedules], ["mailschedule_1", "mailschedule_2"])

    def test_load_mail_schedule_catalog_rejects_invalid_rotation_anchor(self) -> None:
        """Rejects rotation anchors that are not Monday midnight UTC."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            definitions_path = _write_mail_definitions(root)
            schedules_path = root / "mail_schedules.yaml"
            schedules_path.write_text(
                textwrap.dedent(
                    """
                    rotation:
                      cycle_days: 14
                      start_utc: 2026-03-31T01:00:00Z
                    mail_schedules:
                      - id: mailschedule_1
                        day_indices: [0]
                        hour_utc: 5
                        mail_ids: [alliance_reset]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_mail_schedule_catalog(definitions_path=definitions_path, schedules_path=schedules_path)

    def test_load_mail_schedule_catalog_rejects_unknown_mail_reference(self) -> None:
        """Rejects schedules that reference a non-existent authored mail id."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            definitions_path = _write_mail_definitions(root)
            schedules_path = root / "mail_schedules.yaml"
            schedules_path.write_text(
                textwrap.dedent(
                    """
                    rotation:
                      cycle_days: 14
                      start_utc: 2026-03-30T00:00:00Z
                    mail_schedules:
                      - id: mailschedule_1
                        day_indices: [0]
                        hour_utc: 5
                        mail_ids: [missing_mail]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_mail_schedule_catalog(definitions_path=definitions_path, schedules_path=schedules_path)

    def test_resolve_due_mail_definitions_uses_authored_order_by_default(self) -> None:
        """Preserves authored schedule order and authored mail order within each schedule."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog = load_mail_schedule_catalog(
                definitions_path=_write_mail_definitions(root),
                schedules_path=_write_mail_schedules(root),
            )

        due = resolve_due_mail_definitions(catalog, scheduled_for_utc=datetime(2026, 3, 30, 5, 45, tzinfo=UTC))

        self.assertEqual([definition.id for definition in due], ["alliance_reset", "player_followup"])

    def test_resolve_due_mail_definitions_preserves_requested_schedule_order(self) -> None:
        """Uses the caller-provided schedule ordering when filtering to explicit schedule ids."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            definitions_path = _write_mail_definitions(root)
            schedules_path = root / "mail_schedules.yaml"
            schedules_path.write_text(
                textwrap.dedent(
                    """
                    rotation:
                      cycle_days: 14
                      start_utc: 2026-03-30T00:00:00Z
                    mail_schedules:
                      - id: mailschedule_1
                        enabled: true
                        day_indices: [7]
                        hour_utc: 5
                        mail_ids:
                          - alliance_reset
                      - id: mailschedule_2
                        enabled: true
                        day_indices: [7]
                        hour_utc: 5
                        mail_ids:
                          - player_followup
                    """
                ).strip(),
                encoding="utf-8",
            )
            catalog = load_mail_schedule_catalog(definitions_path=definitions_path, schedules_path=schedules_path)

        due = resolve_due_mail_definitions(
            catalog,
            scheduled_for_utc=datetime(2026, 4, 6, 5, 0, tzinfo=UTC),
            schedule_ids=["mailschedule_2", "mailschedule_1"],
        )

        self.assertEqual([definition.id for definition in due], ["player_followup", "alliance_reset"])

    def test_resolve_due_mail_definitions_rejects_duplicate_mail_collision(self) -> None:
        """Rejects one execution window that would send the same mail id twice."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            definitions_path = _write_mail_definitions(root)
            schedules_path = root / "mail_schedules.yaml"
            schedules_path.write_text(
                textwrap.dedent(
                    """
                    rotation:
                      cycle_days: 14
                      start_utc: 2026-03-30T00:00:00Z
                    mail_schedules:
                      - id: mailschedule_1
                        day_indices: [0]
                        hour_utc: 5
                        mail_ids: [alliance_reset]
                      - id: mailschedule_2
                        day_indices: [0]
                        hour_utc: 5
                        mail_ids: [alliance_reset]
                    """
                ).strip(),
                encoding="utf-8",
            )
            catalog = load_mail_schedule_catalog(definitions_path=definitions_path, schedules_path=schedules_path)

        with self.assertRaises(ConfigurationError):
            resolve_due_mail_definitions(catalog, scheduled_for_utc=datetime(2026, 3, 30, 5, 0, tzinfo=UTC))

    def test_build_generated_send_mail_script_emits_canonical_steps(self) -> None:
        """Builds ensure/login plus canonical send_mail steps with preserved castle refs."""

        due_mail_definitions = (
            AuthoredMailDefinition(
                id="alliance_reset",
                castle_ref="main",
                params=SendMailParams(
                    recipient_kind=MailRecipientKind.ALLIANCE,
                    player_name=None,
                    profile_route=None,
                    subject="Reset",
                    body="Please donate.",
                ),
            ),
            AuthoredMailDefinition(
                id="player_followup",
                castle_ref=None,
                params=SendMailParams(
                    recipient_kind=MailRecipientKind.PLAYER,
                    player_name=None,
                    profile_route=PlayerProfileRoute(
                        kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                        player_name="SomePlayer",
                    ),
                    subject="Hi",
                    body="Checking in.",
                ),
            ),
        )

        script = build_generated_send_mail_script(
            scheduled_for_utc=datetime(2026, 3, 31, 5, 0, tzinfo=UTC),
            due_mail_definitions=due_mail_definitions,
        )

        self.assertEqual(script.name, "generated_mail_schedule_20260331T050000Z")
        self.assertEqual([step.task for step in script.steps], [TaskId.ENSURE_GAME_RUNNING, TaskId.LOGIN, TaskId.SEND_MAIL, TaskId.SEND_MAIL])
        self.assertEqual(script.steps[2].castle_ref, "main")
        self.assertEqual(script.steps[2].params["recipient_kind"], "alliance")
        self.assertEqual(script.steps[3].params["profile_route"], {"kind": "alliance_member", "player_name": "SomePlayer"})

    def test_load_app_config_loads_optional_scheduled_mail_catalog(self) -> None:
        """Wires the sibling mail definition and schedule files into AppConfig."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = _write_accounts_config(root)
            _write_mail_definitions(root)
            _write_mail_schedules(root)

            config = load_app_config(config_path)

        self.assertIsNotNone(config.mail_schedule_catalog)
        self.assertEqual(config.mail_definitions_path, (root / "mail_definitions.yaml").resolve())
        self.assertEqual(config.mail_schedules_path, (root / "mail_schedules.yaml").resolve())

    def test_load_app_config_rejects_partial_scheduled_mail_files(self) -> None:
        """Rejects workspaces that author only one half of the scheduled-mail catalog."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = _write_accounts_config(root)
            _write_mail_definitions(root)

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path)


class ScheduledMailRuntimeTests(unittest.TestCase):
    """Validates the generated-script runtime entry points for scheduled mail."""

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

            with patch.object(ScriptRunner, "run_script", return_value=run_result) as run_script:
                result = runner.run_mail_schedules(
                    account_id="account_a",
                    scheduled_for_utc=datetime(2026, 3, 30, 5, 30, tzinfo=UTC),
                )

        self.assertIs(result, run_result)
        script = run_script.call_args.kwargs["script"]
        self.assertEqual(script.name, "generated_mail_schedule_20260330T050000Z")
        self.assertEqual([step.task for step in script.steps], [TaskId.ENSURE_GAME_RUNNING, TaskId.LOGIN, TaskId.SEND_MAIL, TaskId.SEND_MAIL])
        self.assertEqual(script.steps[2].castle_ref, "main")
        self.assertEqual(script.steps[3].params["player_name"], "SomePlayer")


class ScheduledMailApiAndCliTests(unittest.TestCase):
    """Validates the direct scheduled-mail API and CLI surfaces."""

    def test_python_api_run_mail_schedules_resolves_account_from_active_context(self) -> None:
        """Allows scheduled-mail runs to reuse the current bound `use_account(...)` session scope."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a"):
            api.run_mail_schedules(schedule_ids=["mailschedule_1"])

        self.assertEqual(fake_runner.prepare_calls, [("account_a", None)])
        self.assertEqual(
            fake_runner.mail_schedule_calls,
            [("account_a", ["mailschedule_1"], None)],
        )

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


@dataclass(slots=True)
class _FakeApplicationRunner:
    """Records API and CLI scheduled-mail calls without constructing the full runtime."""

    prepare_calls: list[tuple[str, CastleIdentity | None]] = field(default_factory=list)
    task_calls: list[tuple[TaskId, str, dict[str, object] | None]] = field(default_factory=list)
    mail_schedule_calls: list[tuple[str, list[str] | None, datetime | None]] = field(default_factory=list)

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
    ) -> RunResult:
        """Records one session-preparation request and returns a synthetic success result."""

        self.prepare_calls.append((account_id, castle))
        return _make_run_result(script_name="prepare_account_session")

    def run_task(
        self,
        *,
        account_id: str,
        task_id: TaskId,
        params: dict[str, object] | None = None,
    ) -> StepRunResult:
        """Records one direct task call and returns a synthetic success result."""

        self.task_calls.append((task_id, account_id, params))
        return StepRunResult(
            task_id=task_id,
            status=TaskResult.success("ok").status,
            attempts=1,
            message="ok",
        )

    def run_mail_schedules(
        self,
        *,
        account_id: str,
        schedule_ids: list[str] | None = None,
        scheduled_for_utc: datetime | None = None,
    ) -> RunResult:
        """Records one scheduled-mail run request and returns a synthetic success result."""

        self.mail_schedule_calls.append((account_id, schedule_ids, scheduled_for_utc))
        return _make_run_result(script_name="generated_mail_schedule_20260331T050000Z")


@dataclass(slots=True)
class _FakeAdbClient:
    """Records whether the runner tried to connect to a live emulator."""

    connect_calls: list[str] = field(default_factory=list)

    def connect(self, device_id: str) -> CommandResult:
        """Records one connect call and returns success."""

        self.connect_calls.append(device_id)
        return _command_result(returncode=0, stdout_text="connected")

    def get_state(self, device_id: str) -> CommandResult:
        """Returns a ready device state for completeness when a session is used."""

        return _command_result(returncode=0, stdout_text="device")

    def shell(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Returns a non-empty shell response for completeness when a session is used."""

        del device_id, arguments, timeout_seconds
        return _command_result(returncode=0, stdout_text="BlueStacks")


@dataclass(slots=True)
class _FakeInstanceResolver:
    """Records whether the runner tried to resolve a configured emulator instance."""

    resolved_instance: BlueStacksInstance
    requested_configs: list[BlueStacksInstanceConfig] = field(default_factory=list)

    def resolve(self, config: BlueStacksInstanceConfig) -> BlueStacksInstance:
        """Records one resolve request and returns the seeded runtime instance."""

        self.requested_configs.append(config)
        return self.resolved_instance


def _write_accounts_config(root: Path) -> Path:
    """Writes one minimal valid accounts config in the requested directory."""

    config_path = root / "accounts.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            instances:
              - id: bs-main
                display_name: serious_stuff
                app_package: com.global.tmslg
            accounts:
              - id: account_a
                instance_id: bs-main
                pnc_account_id: inline_user
                username: inline_user
                password: inline_pass
            """
        ).strip(),
        encoding="utf-8",
    )
    return config_path


def _write_mail_definitions(root: Path) -> Path:
    """Writes one valid sample mail-definitions catalog."""

    definitions_path = root / "mail_definitions.yaml"
    definitions_path.write_text(
        textwrap.dedent(
            """
            mails:
              - id: alliance_reset
                castle_ref: main
                recipient_kind: alliance
                subject: Alliance Reset Reminder
                body: |
                  Reset is today.
                  Please donate.
              - id: player_followup
                recipient_kind: player
                player_name: SomePlayer
                subject: Follow-up
                body: |
                  Hi,
                  Checking in.
            """
        ).strip(),
        encoding="utf-8",
    )
    return definitions_path


def _write_mail_schedules(root: Path) -> Path:
    """Writes one valid sample mail-schedules catalog."""

    schedules_path = root / "mail_schedules.yaml"
    schedules_path.write_text(
        textwrap.dedent(
            """
            rotation:
              cycle_days: 14
              start_utc: 2026-03-30T00:00:00Z
            mail_schedules:
              - id: mailschedule_1
                enabled: true
                day_indices: [0, 7]
                hour_utc: 5
                mail_ids:
                  - alliance_reset
                  - player_followup
              - id: mailschedule_2
                enabled: true
                day_indices: [7]
                hour_utc: 5
                mail_ids:
                  - player_followup
                  - alliance_reset
            """
        ).strip(),
        encoding="utf-8",
    )
    return schedules_path


def _make_run_result(*, script_name: str) -> RunResult:
    """Builds one minimal successful run result for scheduled-mail API and CLI tests."""

    now = datetime.now(tz=UTC)
    return RunResult(
        account_id="account_a",
        script_name=script_name,
        steps=(),
        started_at=now,
        finished_at=now,
    )


def _command_result(*, returncode: int, stdout_text: str = "", stderr_text: str = "") -> CommandResult:
    """Builds one deterministic raw ADB command result for runtime wiring tests."""

    return CommandResult(
        command=("adb",),
        returncode=returncode,
        stdout=stdout_text.encode("utf-8"),
        stderr=stderr_text.encode("utf-8"),
        duration_seconds=0.01,
    )


if __name__ == "__main__":
    unittest.main()
