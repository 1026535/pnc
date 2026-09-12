"""Mail parameters."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.tasks.collect_mail_task import CollectMailTask
from pnc_automation.app.automation.tasks.send_mail_task import SendMailTask
from pnc_automation.core.errors import ScriptValidationError
from pnc_automation.app.pnc.domain.mail import (
    CollectMailParams,
    MailArchiveMode,
    MailboxType,
    MailRecipientKind,
    SendMailParams,
)

from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures


class MailParametersTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves mail parameters."""

    def test_send_mail_task_parses_direct_player_params(self) -> None:
        """Accepts the canonical player-mail task shape with one explicit player name."""

        task = SendMailTask()

        params = task.parse_params(
            {
                "recipient_kind": "player",
                "player_name": "Enemy Bob",
                "subject": "Hello",
                "body": "Welcome to the kingdom.",
            }
        )

        self.assertEqual(
            params,
            SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Hello",
                body="Welcome to the kingdom.",
            ),
        )

    def test_send_mail_task_rejects_invalid_recipient_shapes(self) -> None:
        """Rejects alliance/player payloads that violate the canonical recipient contract."""

        task = SendMailTask()

        with self.assertRaises(ScriptValidationError):
            task.parse_params(
                {
                    "recipient_kind": "alliance",
                    "player_name": "Should Fail",
                    "subject": "Hello",
                    "body": "World",
                }
            )
        with self.assertRaises(ScriptValidationError):
            task.parse_params(
                {
                    "recipient_kind": "player",
                    "subject": "Hello",
                    "body": "World",
                }
            )

    def test_send_mail_task_rejects_invalid_profile_route_shapes(self) -> None:
        """Rejects profile routes whose player-name requirements do not match the supported route kind."""

        task = SendMailTask()

        with self.assertRaises(ScriptValidationError):
            task.parse_params(
                {
                    "recipient_kind": "player",
                    "profile_route": {"kind": "player_territory", "player_name": "Enemy Bob"},
                    "subject": "Hello",
                    "body": "World",
                }
            )
        with self.assertRaises(ScriptValidationError):
            task.parse_params(
                {
                    "recipient_kind": "player",
                    "profile_route": {"kind": "chat_message"},
                    "subject": "Hello",
                    "body": "World",
                }
            )

    def test_collect_mail_task_parses_deduplicated_mailboxes(self) -> None:
        """Collapses duplicate mailbox names while preserving canonical ordering."""

        task = CollectMailTask()

        params = task.parse_params(
            {
                "mailboxes": ["player", "alliance", "player"],
                "archive_mode": "both",
                "limit_per_mailbox": 7,
                "only_new": True,
            }
        )

        self.assertEqual(
            params,
            CollectMailParams(
                mailboxes=(MailboxType.PLAYER, MailboxType.ALLIANCE),
                archive_mode=MailArchiveMode.BOTH,
                limit_per_mailbox=7,
                only_new=True,
            ),
        )
