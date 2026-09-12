"""Scheduled mail resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile
import textwrap
import unittest

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.mail.loader import (
    build_generated_send_mail_script,
    load_mail_schedule_catalog,
    resolve_due_mail_definitions,
    resolve_scheduled_hour_bucket,
)
from pnc_automation.app.authoring.mail.models import AuthoredMailDefinition, ScheduledMailDispatch
from pnc_automation.app.pnc.domain.mail import MailRecipientKind, PlayerProfileRoute, SendMailParams
from pnc_automation.app.pnc.enums.mail import PlayerProfileRouteKind
from pnc_automation.core.errors import ConfigurationError

from tests.support.entrypoints.scheduled_mail.write_mail_definitions import _write_mail_definitions
from tests.support.entrypoints.scheduled_mail.write_mail_schedules import _write_mail_schedules


class ScheduledMailResolutionTests(unittest.TestCase):
    """Proves scheduled mail resolution."""

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

    def test_resolve_due_mail_definitions_returns_nothing_before_rotation_start(self) -> None:
        """Keeps the rotation inactive until the authored Monday midnight UTC start anchor."""

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
                        day_indices: [13]
                        hour_utc: 23
                        mail_ids: [alliance_reset]
                    """
                ).strip(),
                encoding="utf-8",
            )
            catalog = load_mail_schedule_catalog(definitions_path=definitions_path, schedules_path=schedules_path)

        due = resolve_due_mail_definitions(catalog, scheduled_for_utc=datetime(2026, 3, 29, 23, 0, tzinfo=UTC))

        self.assertEqual(due, ())

    def test_resolve_scheduled_hour_bucket_rejects_non_utc_runtime_offset(self) -> None:
        """Rejects runtime replay timestamps whose original offset is not already UTC."""

        with self.assertRaises(ConfigurationError):
            resolve_scheduled_hour_bucket(datetime.fromisoformat("2026-03-30T05:00:00+02:00"))

    def test_build_generated_send_mail_script_emits_canonical_steps(self) -> None:
        """Builds ensure/login plus canonical send_mail steps with preserved castle refs and provenance."""

        due_mail_dispatches = (
            ScheduledMailDispatch(
                schedule_id="mailschedule_1",
                definition=AuthoredMailDefinition(
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
            ),
            ScheduledMailDispatch(
                schedule_id="mailschedule_2",
                definition=AuthoredMailDefinition(
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
            ),
        )

        script = build_generated_send_mail_script(
            scheduled_for_utc=datetime(2026, 3, 31, 5, 0, tzinfo=UTC),
            due_mail_dispatches=due_mail_dispatches,
        )

        self.assertEqual(script.name, "generated_mail_schedule_20260331T050000Z")
        self.assertEqual([step.task for step in script.steps], [TaskId.ENSURE_GAME_RUNNING, TaskId.LOGIN, TaskId.SEND_MAIL, TaskId.SEND_MAIL])
        self.assertEqual(script.steps[2].castle_ref, "main")
        self.assertEqual(script.steps[2].params["recipient_kind"], "alliance")
        self.assertEqual(script.steps[2].provenance, {"mail_id": "alliance_reset", "schedule_id": "mailschedule_1"})
        self.assertEqual(script.steps[3].params["profile_route"], {"kind": "alliance_member", "player_name": "SomePlayer"})
        self.assertEqual(script.steps[3].provenance, {"mail_id": "player_followup", "schedule_id": "mailschedule_2"})
