"""Mail action follow up: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import InputTextAction, TapAction
from pnc_automation.app.pnc.domain.mail import MailboxType, MailRecipientKind, SendMailParams
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.automation.session import FakeSession
from tests.support.pnc.observations import make_observation
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures


class MailActionFollowUpTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves mail action follow up."""

    def test_action_executor_stops_mail_sequence_after_unexpected_follow_up_screen(self) -> None:
        """Stops a multi-step mail action sequence when the previous observed follow-up missed its expected screen."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_MAILBOX_LIST,
                    mailbox_type=MailboxType.PLAYER,
                )
            ]
        )

        result = executor.execute_actions(
            [
                TapAction(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_BUTTON,
                    reason="open_player_mail_compose",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_compose_follow_up(),
                ),
                InputTextAction(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD,
                    text="Enemy Bob",
                    replace_existing=True,
                ),
            ],
            make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                visible_ids=(UiElementId.PNC_MAIL_COMPOSE_BUTTON,),
            ),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertEqual(executor.session.texts, [])
        self.assertEqual(fake_observer.requests, [ObservationRequest.mail_compose_follow_up()])

    def test_mail_compose_follow_up_keeps_compose_origin_screens_visible_on_compose_miss(self) -> None:
        """Lets compose-entry follow-ups preserve every supported source screen when the popup does not open."""

        request = ObservationRequest.mail_compose_follow_up()

        self.assertEqual(
            request.candidate_screen_types,
            frozenset(
                {
                    ScreenType.PNC_MAIL_COMPOSE_POPUP,
                    ScreenType.PNC_ALLIANCE_HOME,
                    ScreenType.PNC_PLAYER_PROFILE,
                }
            ),
        )
        self.assertEqual(request.ocr_screen_types, request.candidate_screen_types)

    def test_send_mail_flow_from_compose_enters_subject_body_and_sends(self) -> None:
        """Builds the canonical compose-send action sequence from an already-open popup."""

        params = SendMailParams(
            recipient_kind=MailRecipientKind.ALLIANCE,
            player_name=None,
            profile_route=None,
            subject="Rally",
            body="Join now.",
        )

        actions = self.flows.send_mail(make_observation(ScreenType.PNC_MAIL_COMPOSE_POPUP), params)

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], InputTextAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD)
        self.assertIsInstance(actions[1], InputTextAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD)
        self.assertIsInstance(actions[2], TapAction)
        self.assertEqual(actions[2].selector_id, UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON)
