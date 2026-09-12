"""Chat send flow."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import (
    ActionTimingProfile,
    InputTextAction,
    SelectChatChannelAction,
    TapAction,
)
from pnc_automation.app.pnc.navigation.screen_flows import ChatChannel
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class ChatSendFlowTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves chat send flow."""

    def test_send_chat_message_from_home_city_opens_chat_selects_channel_and_sends(self) -> None:
        """Uses one chat-opening increment from home so the chat origin is observed before sending."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )

        actions = self.flows.send_chat_message(
            observation,
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_SHORTCUT)
        self.assertTrue(actions[0].observe_after)

    def test_send_chat_message_maps_world_channel_to_kingdom_tab(self) -> None:
        """Maps the public world-channel enum to the in-game Kingdom chat tab."""

        observation = make_observation(ScreenType.PNC_CHAT)

        actions = self.flows.send_chat_message(
            observation,
            message="ping",
            channel=ChatChannel.WORLD,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SelectChatChannelAction)
        self.assertEqual(actions[0].channel, ChatChannel.WORLD)
        self.assertTrue(actions[0].observe_after)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT))

    def test_send_chat_message_uses_narrow_chat_open_follow_up_request(self) -> None:
        """Uses the shared chat-specific navigation follow-up instead of a broad default observation."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )

        actions = self.flows.send_chat_message(
            observation,
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.navigation_follow_up((self.flows._chat_navigation_outcome(),)),
        )

    def test_send_chat_message_preserves_runtime_channel_skip_when_chat_is_already_active(self) -> None:
        """Skips channel selection once chat is already on the requested tab and goes straight to send actions."""

        observation = make_observation(
            ScreenType.PNC_CHAT,
            active_chat_channel=ChatChannel.ALLIANCE,
            chat_draft_empty=True,
        )

        actions = self.flows.send_chat_message(
            observation,
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], InputTextAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_INPUT_FIELD)
        self.assertEqual(actions[0].text, "hello")
        self.assertTrue(actions[0].replace_existing)
        self.assertEqual(actions[0].timing_profile, ActionTimingProfile.CHAT)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_CHAT_SEND_BUTTON)
        self.assertEqual(actions[1].follow_up_request, ObservationRequest.chat_send_follow_up())
        self.assertEqual(actions[1].timing_profile, ActionTimingProfile.CHAT)
