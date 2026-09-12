"""Send mail confirmation."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.send_mail_task import SendMailTask
from pnc_automation.app.pnc.domain.action_requests import TapPointAction
from pnc_automation.app.pnc.domain.mail import (
    MailboxType,
    MailRecipientKind,
    PlayerProfileRoute,
    PlayerProfileRouteKind,
    SendMailParams,
)
from pnc_automation.app.pnc.domain.observation import ListEntryKind, ObservedTextFieldState
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.make_task_context import _make_task_context


class SendMailConfirmationTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves send mail confirmation."""

    def test_send_mail_verify_replans_when_direct_player_compose_target_still_needs_manual_entry(self) -> None:
        """Replans for target entry instead of failing as soon as the direct-player compose popup opens."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Hello",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )

        result = task.verify(
            context,
            before=make_observation(ScreenType.PNC_MAILBOX_LIST, mailbox_type=MailboxType.PLAYER),
            after=make_observation(
                ScreenType.PNC_MAIL_COMPOSE_POPUP,
                text_field_states={
                    UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD: ObservedTextFieldState(
                        selector_id=UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD,
                        text="",
                        empty=True,
                    )
                },
            ),
        )

        self.assertEqual(result.status.value, "replan")
        self.assertIn("needs the requested player target typed", result.message)

    def test_send_mail_verify_prefers_observed_profile_header_name_over_route_lookup_name(self) -> None:
        """Uses the opened profile header as the authoritative target once a profile-route send reaches compose."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name=None,
                profile_route=PlayerProfileRoute(
                    kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                    player_name="Cutie",
                ),
                subject="Hello",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )

        result = task.verify(
            context,
            before=make_observation(
                ScreenType.PNC_PLAYER_PROFILE,
                profile_player_name="Cutie Voj",
            ),
            after=make_observation(
                ScreenType.PNC_MAIL_COMPOSE_POPUP,
                text_field_states={
                    UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD: ObservedTextFieldState(
                        selector_id=UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD,
                        text="Cutie Voj",
                        empty=False,
                    )
                },
            ),
        )

        self.assertEqual(result.status.value, "replan")
        self.assertEqual(context.runtime_state["expected_profile_target"], "Cutie Voj")

    def test_send_mail_verify_mail_plan_opens_ambiguous_same_recipient_row_for_thread_confirmation(self) -> None:
        """Promotes a same-recipient mailbox row to thread confirmation instead of accepting it as proof."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Fresh hello",
                body="New message",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        context.runtime_state["send_mail_phase"] = "verify_mailbox"

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", subtitle="Older preview"),),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(context.runtime_state["send_mail_phase"], "verify_thread")

    def test_send_mail_verify_succeeds_when_matching_sent_row_is_visible(self) -> None:
        """Accepts mailbox-only verification only when the visible row already contains strong subject/body evidence."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.ALLIANCE,
                player_name=None,
                profile_route=None,
                subject="Test",
                body="test",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        context.runtime_state["send_mail_phase"] = "verify_mailbox"

        result = task.verify(
            context,
            before=make_observation(ScreenType.PNC_MAIL_HUB),
            after=make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.ALLIANCE,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Alliance", subtitle="Test test"),),
            ),
        )

        self.assertEqual(result.status.value, "success")
        self.assertIn("located in the reopened mailbox", result.message)

    def test_send_mail_verify_succeeds_when_ambiguous_row_opens_matching_thread(self) -> None:
        """Allows ambiguous mailbox rows to succeed once the opened thread confirms the just-sent content."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Fresh hello",
                body="New message",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        context.runtime_state["send_mail_phase"] = "verify_mailbox"
        mailbox = make_observation(
            ScreenType.PNC_MAILBOX_LIST,
            mailbox_type=MailboxType.PLAYER,
            list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", subtitle="Older preview"),),
        )

        actions = task.plan(context, mailbox)
        result = task.verify(
            context,
            before=mailbox,
            after=make_observation(
                ScreenType.PNC_MAIL_THREAD,
                list_entries=(
                    make_entry(ListEntryKind.MAIL_MESSAGE, title="Fresh hello"),
                    make_entry(ListEntryKind.MAIL_MESSAGE, title="New message"),
                ),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(result.status.value, "success")
        self.assertIn("confirmed in the reopened mailbox thread", result.message)

    def test_send_mail_verify_fails_when_ambiguous_row_opens_wrong_thread(self) -> None:
        """Fails when a same-recipient mailbox row leads to a thread whose content does not match the send."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Fresh hello",
                body="New message",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        context.runtime_state["send_mail_phase"] = "verify_mailbox"
        mailbox = make_observation(
            ScreenType.PNC_MAILBOX_LIST,
            mailbox_type=MailboxType.PLAYER,
            list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", subtitle="Older preview"),),
        )

        actions = task.plan(context, mailbox)
        result = task.verify(
            context,
            before=mailbox,
            after=make_observation(
                ScreenType.PNC_MAIL_THREAD,
                list_entries=(make_entry(ListEntryKind.MAIL_MESSAGE, title="Completely unrelated history"),),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(result.status.value, "failed")
        self.assertTrue(result.retryable)
        self.assertIn("did not contain the expected sent subject or body", result.message)
