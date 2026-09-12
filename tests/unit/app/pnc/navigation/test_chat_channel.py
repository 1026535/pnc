"""Chat channel."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import SelectChatChannelAction
from pnc_automation.app.pnc.navigation.screen_flows import ChatChannel
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class ChatChannelTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves chat channel."""

    def test_ensure_chat_channel_reuses_open_chat_until_chat_is_visible(self) -> None:
        """Uses the shared open-chat flow before attempting any channel-specific chat action."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )

        actions = self.flows.ensure_chat_channel(observation, ChatChannel.WORLD)

        self.assertEqual(actions, self.flows.open_chat(observation))

    def test_ensure_chat_channel_selects_requested_tab_from_shared_chat_overlay(self) -> None:
        """Uses one canonical channel-selection action once the shared chat overlay is already open."""

        observation = make_observation(
            ScreenType.PNC_CHAT,
            active_chat_channel=ChatChannel.ALLIANCE,
        )

        actions = self.flows.ensure_chat_channel(observation, ChatChannel.WORLD)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SelectChatChannelAction)
        self.assertEqual(actions[0].channel, ChatChannel.WORLD)
