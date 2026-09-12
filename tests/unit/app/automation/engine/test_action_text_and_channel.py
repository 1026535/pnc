"""Action text and channel."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import (
    InputTextAction,
    SelectChatChannelAction,
    TapAction,
)
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation, make_visible
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


class ActionTextAndChannelTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves action text and channel."""

    def test_input_text_actions_use_selector_action_points_for_focus(self) -> None:
        """Focuses selector-backed text entry through the canonical action point instead of the bounds center."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_CHAT,
            visible_ids=(UiElementId.PNC_CHAT_INPUT_FIELD,),
            chat_draft_empty=True,
        )
        observation = Observation(
            screen_type=observation.screen_type,
            visible_elements={
                UiElementId.PNC_CHAT_INPUT_FIELD: make_visible(
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    x=20,
                    y=40,
                    width=90,
                    height=22,
                    action_point=(81, 55),
                )
            },
            image_size=observation.image_size,
            active_chat_channel=observation.active_chat_channel,
            chat_draft_empty=observation.chat_draft_empty,
            chat_draft_text=observation.chat_draft_text,
        )

        executor.execute_action(
            InputTextAction(
                selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                text="hello",
                replace_existing=True,
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(81, 55)])
        self.assertEqual(executor.session.texts, ["hello"])

    def test_observed_action_executor_uses_action_scoped_follow_up_requests_for_non_navigation_actions(self) -> None:
        """Uses the action-provided follow-up request for observe-after actions that stay on the same screen."""

        fake_observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_CHAT)])
        fake_session = FakeSession()
        executor = _make_observed_action_executor(fake_session)

        execution = executor.execute_actions(
            (
                TapAction(
                    selector_id=UiElementId.PNC_CHAT_SEND_BUTTON,
                    reason="send_chat_message",
                    observe_after=True,
                    follow_up_request=ObservationRequest.chat_send_follow_up(),
                ),
            ),
            make_observation(ScreenType.PNC_CHAT, visible_ids=(UiElementId.PNC_CHAT_SEND_BUTTON,)),
            observe=fake_observer.observe,
        )

        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(fake_observer.requests, [ObservationRequest.chat_send_follow_up()])

    def test_select_chat_channel_action_skips_the_tap_when_the_requested_tab_is_already_active(self) -> None:
        """Avoids redundant chat-tab taps when the current observation already proves the active channel."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        action_executed = executor.execute_action(
            SelectChatChannelAction(channel=ChatChannel.ALLIANCE),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(UiElementId.PNC_CHAT_TAB_ALLIANCE,),
                active_chat_channel=ChatChannel.ALLIANCE,
            ),
        )

        self.assertFalse(action_executed)
        self.assertEqual(executor.session.taps, [])

    def test_action_executor_skips_chat_channel_follow_up_when_the_requested_tab_is_already_active(self) -> None:
        """Skips both the tap and the observe-after follow-up when chat is already on the requested channel."""

        fake_observer = FakeObservationService(observations=[])
        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        result = executor.execute_actions(
            (
                SelectChatChannelAction(
                    channel=ChatChannel.ALLIANCE,
                    observe_after=True,
                    follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
                ),
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(UiElementId.PNC_CHAT_TAB_ALLIANCE,),
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=True,
            ),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertEqual(fake_observer.requests, [])
