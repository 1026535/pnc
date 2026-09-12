"""Mail compose entry."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.mail import (
    MailboxType,
    MailRecipientKind,
    PlayerProfileRoute,
    PlayerProfileRouteKind,
    SendMailParams,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures


class MailComposeEntryTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves mail compose entry."""

    def test_open_mail_compose_from_player_profile_taps_mail_button(self) -> None:
        """Uses the shared player-profile compose route for personal mail sends."""

        params = SendMailParams(
            recipient_kind=MailRecipientKind.PLAYER,
            player_name=None,
            profile_route=PlayerProfileRoute(kind=PlayerProfileRouteKind.PLAYER_TERRITORY),
            subject="Hello",
            body="World",
        )

        actions = self.flows.open_mail_compose(
            make_observation(
                ScreenType.PNC_PLAYER_PROFILE,
                visible_ids=(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON,),
            ),
            params,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.mail_compose_follow_up())

    def test_open_mail_compose_from_player_mailbox_only_taps_compose(self) -> None:
        """Uses one compose-opening increment from the player mailbox so the compose popup is observed before target entry."""

        params = SendMailParams(
            recipient_kind=MailRecipientKind.PLAYER,
            player_name="Enemy Bob",
            profile_route=None,
            subject="Hello",
            body="World",
        )

        actions = self.flows.open_mail_compose(
            make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                visible_ids=(UiElementId.PNC_MAIL_COMPOSE_BUTTON,),
            ),
            params,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_MAIL_COMPOSE_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.mail_compose_follow_up())
