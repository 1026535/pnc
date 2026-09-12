"""Chat draft input."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import InputTextAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)


class ChatDraftInputTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves chat draft input."""

    def test_input_text_action_clears_an_existing_chat_draft_before_typing(self) -> None:
        """Uses the shared clear-and-replace policy instead of appending onto a stale chat draft."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        executor.execute_action(
            InputTextAction(
                selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                text="hello",
                replace_existing=True,
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(UiElementId.PNC_CHAT_INPUT_FIELD,),
                chat_draft_empty=False,
                chat_draft_text="existing",
            ),
        )

        self.assertEqual(executor.session.key_events[0], "KEYCODE_MOVE_END")
        self.assertTrue(all(key_code == "KEYCODE_DEL" for key_code in executor.session.key_events[1:]))
        self.assertGreaterEqual(len(executor.session.key_events), 25)
