"""Navigation core mail tests."""

from datetime import UTC, datetime, timedelta
import unittest

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapPointAction
from pnc_automation.app.pnc.domain.mail import (
    MailboxAvailability,
    MailboxType,
    mail_thread_row_key,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.navigation.core_frames import Actuator
from tests.support.pnc.navigation.core_mail import (
    mail_frame,
    mail_thread_entry,
    mailbox_category,
)
from tests.support.pnc.navigation.core_recording import RecordedFramesCore


class NavigationCoreTests(RecordedFramesCore, unittest.TestCase):
    def test_open_mailbox_unavailable_category_returns_without_tap(self):
        actuator = Actuator()
        now = datetime(2026, 9, 12, tzinfo=UTC)
        core = NavigationCore(
            actuator,
            lambda _: mail_frame(ScreenType.PNC_MAIL_HUB, selector=UiElementId.PNC_MAIL_ROW_PLAYER_MAIL),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        hub = mail_frame(
            ScreenType.PNC_MAIL_HUB,
            entries=(mailbox_category(MailboxType.PLAYER, available=False),),
            captured_at=now,
        )
        self.assertEqual(
            core.open_mailbox(MailboxType.PLAYER, observe_content=lambda _: hub),
            MailboxAvailability.UNAVAILABLE,
        )
        self.assertEqual(actuator.actions, [])


    def test_open_mailbox_available_category_uses_exact_reviewed_tap_once(self):
        actuator = Actuator()
        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter(
            (
                mail_frame(ScreenType.PNC_MAIL_HUB, selector=UiElementId.PNC_MAIL_ROW_PLAYER_MAIL, captured_at=now),
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=1)),
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=2)),
            )
        )
        core = NavigationCore(
            actuator,
            lambda _: next(frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        hub = mail_frame(
            ScreenType.PNC_MAIL_HUB,
            entries=(mailbox_category(MailboxType.PLAYER, available=True),),
            captured_at=now,
        )
        self.assertEqual(
            core.open_mailbox(MailboxType.PLAYER, observe_content=lambda _: hub),
            MailboxAvailability.AVAILABLE,
        )
        self.assertEqual(len(actuator.actions), 1)
        self.assertEqual(actuator.actions[0].selector_id, UiElementId.PNC_MAIL_ROW_PLAYER_MAIL)


    def test_open_mailbox_ambiguous_or_missing_category_sends_no_action(self):
        for entries in (
            (),
            (mailbox_category(MailboxType.PLAYER, available=True), mailbox_category(MailboxType.PLAYER, available=True)),
        ):
            actuator = Actuator()
            core = NavigationCore(
                actuator,
                lambda _: mail_frame(ScreenType.PNC_MAIL_HUB),
                reviewed_navigation_edges(),
                NavigationPolicy(max_observations=4),
                sleep=lambda _: None,
            )
            with self.assertRaisesRegex(RuntimeError, "missing or ambiguous"):
                core.open_mailbox(
                    MailboxType.PLAYER,
                    observe_content=lambda _: mail_frame(ScreenType.PNC_MAIL_HUB, entries=entries),
                )
            self.assertEqual(actuator.actions, [])


    def test_open_mail_thread_matches_one_row_and_rejects_stale_or_popup_completion(self):
        row = mail_thread_entry()
        row_key = mail_thread_row_key(row)
        now = datetime(2026, 9, 12, tzinfo=UTC)
        for completion in (
            (
                mail_frame(ScreenType.PNC_MAIL_THREAD, captured_at=now),
                mail_frame(ScreenType.PNC_MAIL_THREAD, captured_at=now),
            ),
            (
                mail_frame(ScreenType.PNC_POPUP, blocked=True, captured_at=now + timedelta(seconds=1)),
            ),
        ):
            actuator = Actuator()
            frames = iter(completion)
            core = NavigationCore(
                actuator,
                lambda _: next(frames),
                reviewed_navigation_edges(),
                NavigationPolicy(max_observations=4),
                sleep=lambda _: None,
            )
            with self.assertRaises(RuntimeError):
                core.open_mail_thread(
                    row_key,
                    observe_content=lambda _: mail_frame(
                        ScreenType.PNC_MAILBOX_LIST,
                        entries=(row,),
                        captured_at=now,
                    ),
                )
            self.assertEqual(len(actuator.actions), 1)
            self.assertIsInstance(actuator.actions[0], TapPointAction)


    def test_open_mail_thread_missing_or_ambiguous_row_sends_no_action(self):
        row = mail_thread_entry()
        for entries in ((), (row, row)):
            actuator = Actuator()
            core = NavigationCore(
                actuator,
                lambda _: mail_frame(ScreenType.PNC_MAIL_THREAD),
                reviewed_navigation_edges(),
                NavigationPolicy(max_observations=4),
                sleep=lambda _: None,
            )
            with self.assertRaisesRegex(RuntimeError, "absent, ambiguous"):
                core.open_mail_thread(
                    mail_thread_row_key(row),
                    observe_content=lambda _: mail_frame(ScreenType.PNC_MAILBOX_LIST, entries=entries),
                )
            self.assertEqual(actuator.actions, [])


    def test_scroll_mailbox_uses_one_bounded_swipe_without_replay(self):
        actuator = Actuator()
        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter(
            (
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=1)),
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=2)),
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=3)),
            )
        )
        core = NavigationCore(
            actuator,
            lambda _: mail_frame(ScreenType.PNC_MAILBOX_LIST),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        result = core.scroll_mailbox(observe_content=lambda _: next(frames))
        self.assertEqual(result.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertEqual(len(actuator.actions), 1)
        self.assertIsInstance(actuator.actions[0], SwipeAction)
