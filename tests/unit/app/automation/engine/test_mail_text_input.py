"""Mail text input."""

from __future__ import annotations

from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import InputTextAction
from pnc_automation.app.pnc.domain.observation import ObservedTextFieldState
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.automation.session import FakeSession
from tests.support.pnc.observations import make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures


class MailTextInputTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves mail text input."""

    def test_action_executor_clears_existing_mail_subject_field_before_typing(self) -> None:
        """Uses the generic observed text-field state to replace mail subject content in place."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_MAIL_COMPOSE_POPUP,
            visible_ids=(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD,),
            text_field_states={
                UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD: ObservedTextFieldState(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD,
                    text="Existing Subject",
                    empty=False,
                )
            },
        )

        executor.execute_action(
            InputTextAction(
                selector_id=UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD,
                text="Updated Subject",
                replace_existing=True,
            ),
            observation,
        )

        self.assertEqual(executor.session.key_events[0], "KEYCODE_MOVE_END")
        self.assertGreaterEqual(executor.session.key_events.count("KEYCODE_DEL"), 24)
        self.assertEqual(executor.session.texts, ["Updated Subject"])

    def test_action_executor_enters_multiline_mail_body(self) -> None:
        """Uses the shared multiline policy for the compose body instead of rejecting newlines outright."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_MAIL_COMPOSE_POPUP,
            visible_ids=(UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,),
            text_field_states={
                UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD: ObservedTextFieldState(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,
                    text=None,
                    empty=True,
                )
            },
        )

        executor.execute_action(
            InputTextAction(
                selector_id=UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,
                text="First line\nSecond line",
                replace_existing=True,
            ),
            observation,
        )

        self.assertEqual(executor.session.texts, ["First line", "Second line"])
        self.assertEqual(executor.session.key_events, ["KEYCODE_ENTER"])
