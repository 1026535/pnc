"""Mailbox entry."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import KeyEventAction, TapAction
from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures


class MailboxEntryTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves mailbox entry."""

    def test_open_mail_hub_uses_bottom_nav_mail(self) -> None:
        """Uses the shared mail bottom-nav selector to open the canonical mail hub."""

        actions = self.flows.open_mail_hub(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_MAIL,),
            )
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MAIL)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAIL_HUB, ScreenType.PNC_MAILBOX_LIST),
        )

    def test_open_mail_hub_uses_visible_bottom_nav_from_world_map(self) -> None:
        """Uses the visible Mail bottom nav directly when world-adjacent screens already expose it."""

        actions = self.flows.open_mail_hub(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_MAIL,),
            )
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MAIL)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAIL_HUB, ScreenType.PNC_MAILBOX_LIST),
        )

    def test_open_mail_hub_from_unknown_only_uses_in_game_recovery_first(self) -> None:
        """Keeps mail-hub navigation incremental when starting from an unknown screen."""

        actions = self.flows.open_mail_hub(make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_open_mailbox_from_mail_hub_taps_requested_category(self) -> None:
        """Uses the requested mailbox category row instead of duplicating hub-specific navigation logic."""

        actions = self.flows.open_mailbox(
            make_observation(
                ScreenType.PNC_MAIL_HUB,
                visible_ids=(UiElementId.PNC_MAIL_ROW_PLAYER_MAIL,),
            ),
            MailboxType.PLAYER,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_MAIL_ROW_PLAYER_MAIL)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAILBOX_LIST, ScreenType.PNC_MAIL_HUB),
        )

    def test_open_mailbox_from_home_only_opens_mail_hub_first(self) -> None:
        """Keeps mailbox navigation incremental so the task can observe mail-hub no-op states cleanly."""

        actions = self.flows.open_mailbox(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_MAIL,),
            ),
            MailboxType.PLAYER,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MAIL)
