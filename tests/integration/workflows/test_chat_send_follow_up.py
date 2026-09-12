"""Chat send follow up: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)


class ChatSendFollowUpTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves chat send follow up."""

    def test_send_chat_message_stops_when_the_chat_tab_follow_up_stays_on_the_wrong_channel(self) -> None:
        """Refuses to type or send when the observed post-tap chat state still shows the previous channel."""

        fake_session = FakeSession()
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_CHAT,
                    visible_ids=(
                        UiElementId.PNC_CHAT_TAB_KINGDOM,
                        UiElementId.PNC_CHAT_TAB_ALLIANCE,
                        UiElementId.PNC_CHAT_INPUT_FIELD,
                        UiElementId.PNC_CHAT_SEND_BUTTON,
                    ),
                    active_chat_channel=ChatChannel.WORLD,
                    chat_draft_empty=True,
                )
            ]
        )
        executor = ActionExecutor(
            session=fake_session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        actions = ScreenFlowPlanner().send_chat_message(
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        result = executor.execute_actions(
            actions,
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.active_chat_channel, ChatChannel.WORLD)
        self.assertEqual(fake_observer.requests, [ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT)])
        self.assertEqual(fake_session.texts, [])

    def test_send_chat_message_stops_when_the_chat_tab_follow_up_is_still_loading(self) -> None:
        """Stops before typing when the post-switch observation is still in a transient settling state."""

        fake_session = FakeSession()
        fake_observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_LOADING)])
        executor = ActionExecutor(
            session=fake_session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        actions = ScreenFlowPlanner().send_chat_message(
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        result = executor.execute_actions(
            actions,
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_LOADING)
        self.assertEqual(fake_observer.requests, [ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT)])
        self.assertEqual(fake_session.texts, [])

    def test_send_chat_message_uses_the_post_switch_channel_draft_state_before_typing(self) -> None:
        """Refreshes chat state after a tab change and only types on the next chat-ready increment."""

        fake_session = FakeSession()
        executor = ActionExecutor(
            session=fake_session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        first_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_CHAT,
                    visible_ids=(
                        UiElementId.PNC_CHAT_TAB_KINGDOM,
                        UiElementId.PNC_CHAT_TAB_ALLIANCE,
                        UiElementId.PNC_CHAT_INPUT_FIELD,
                        UiElementId.PNC_CHAT_SEND_BUTTON,
                    ),
                    active_chat_channel=ChatChannel.ALLIANCE,
                    chat_draft_empty=False,
                    chat_draft_text="ally draft text here",
                )
            ]
        )
        first_actions = ScreenFlowPlanner().send_chat_message(
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=False,
                chat_draft_text="world draft text that should not be reused after switching tabs",
            ),
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        first_result = executor.execute_actions(
            first_actions,
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(
                    UiElementId.PNC_CHAT_TAB_KINGDOM,
                    UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    UiElementId.PNC_CHAT_SEND_BUTTON,
                ),
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=False,
                chat_draft_text="world draft text that should not be reused after switching tabs",
            ),
            observe=first_observer.observe,
        )
        second_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_CHAT,
                    visible_ids=(
                        UiElementId.PNC_CHAT_TAB_KINGDOM,
                        UiElementId.PNC_CHAT_TAB_ALLIANCE,
                        UiElementId.PNC_CHAT_INPUT_FIELD,
                        UiElementId.PNC_CHAT_SEND_BUTTON,
                    ),
                    active_chat_channel=ChatChannel.ALLIANCE,
                    chat_draft_empty=True,
                )
            ]
        )
        second_actions = ScreenFlowPlanner().send_chat_message(
            first_result,
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        executor.execute_actions(
            second_actions,
            first_result,
            observe=second_observer.observe,
        )

        self.assertEqual(first_observer.requests, [ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT)])
        self.assertEqual(second_observer.requests, [ObservationRequest.chat_send_follow_up()])
        self.assertEqual(fake_session.key_events[0], "KEYCODE_MOVE_END")
        self.assertEqual(fake_session.key_events.count("KEYCODE_DEL"), 28)
        self.assertEqual(fake_session.texts, ["hello"])
