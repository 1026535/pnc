"""Send chat message."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.tasks.send_chat_message_task import (
    ChatMessageTaskParams,
    SendAllianceChatMessageTask,
    SendWorldChatMessageTask,
)
from pnc_automation.core.errors import ScriptValidationError
from pnc_automation.app.pnc.domain.action_requests import WaitAction
from pnc_automation.app.pnc.navigation.screen_flows import ChatChannel
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class SendChatMessageTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves send chat message."""

    def test_send_alliance_chat_message_task_parses_one_required_message(self) -> None:
        """Accepts only the single script-facing message parameter for alliance chat sends."""

        task = SendAllianceChatMessageTask()

        params = task.parse_params({"message": "bot shall invade"})

        self.assertEqual(params, ChatMessageTaskParams(message="bot shall invade"))
        with self.assertRaises(ScriptValidationError):
            task.parse_params({})
        with self.assertRaises(ScriptValidationError):
            task.parse_params({"message": " ", "channel": "alliance"})

    def test_send_alliance_chat_message_task_delegates_to_the_canonical_chat_flow(self) -> None:
        """Plans the existing alliance chat flow without reimplementing any chat actions."""

        task = SendAllianceChatMessageTask()
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )
        context = self._make_context(params=ChatMessageTaskParams(message="hello alliance"))

        actions = task.plan(context, observation)

        self.assertEqual(
            actions,
            self.flows.send_chat_message(
                observation,
                message="hello alliance",
                channel=ChatChannel.ALLIANCE,
            ),
        )

    def test_send_world_chat_message_task_returns_one_recovery_increment_until_chat_ready(self) -> None:
        """Uses the canonical root-return flow before attempting the fixed world-chat send."""

        task = SendWorldChatMessageTask()
        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_SETTINGS, UiElementId.PNC_BOTTOM_NAV_MORE),
        )
        context = self._make_context(params=ChatMessageTaskParams(message="hello world"))

        actions = task.plan(context, observation)

        self.assertEqual(actions, self.flows.ensure_home_city(observation))

    def test_send_world_chat_message_task_waits_through_loading(self) -> None:
        """Waits for loading to settle before attempting the reusable chat workflow."""

        task = SendWorldChatMessageTask()
        context = self._make_context(params=ChatMessageTaskParams(message="hello world"))

        actions = task.plan(context, make_observation(ScreenType.PNC_LOADING))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertTrue(actions[0].observe_after)

    def test_send_alliance_chat_message_task_uses_shared_unknown_recovery_increment(self) -> None:
        """Recovers unknown in-game states with the shared back action before chat navigation resumes."""

        task = SendAllianceChatMessageTask()
        context = self._make_context(params=ChatMessageTaskParams(message="hello alliance"))

        actions = task.plan(context, make_observation(ScreenType.UNKNOWN))

        self.assertEqual(
            actions,
            self.flows.recover_unknown_game_screen(
                make_observation(ScreenType.UNKNOWN),
                reason="recover_unknown_alliance_chat_screen",
            ),
        )

    def test_send_alliance_chat_message_task_verifies_a_successful_send(self) -> None:
        """Succeeds only when the final observation proves the expected alliance chat state."""

        task = SendAllianceChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello alliance")),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=False,
                chat_draft_text="hello alliance",
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=True,
            ),
        )

        self.assertTrue(result.succeeded)

    def test_send_world_chat_message_task_replans_while_returning_to_a_chat_ready_screen(self) -> None:
        """Replans between recovery increments instead of trying to send from unsupported screens."""

        task = SendWorldChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello world")),
            make_observation(ScreenType.PNC_VIP),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(result.status.value, "replan")

    def test_send_world_chat_message_task_replans_after_reaching_the_requested_channel(self) -> None:
        """Keeps replanning after channel selection because reaching the right chat tab is not the same as sending."""

        task = SendWorldChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello world")),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=True,
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
        )

        self.assertEqual(result.status.value, "replan")
        self.assertIn("can now send", result.message)

    def test_send_world_chat_message_task_does_not_report_success_during_recovery(self) -> None:
        """Keeps replanning when recovery lands on an already-open chat instead of claiming the message was sent."""

        task = SendWorldChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello world")),
            make_observation(ScreenType.PNC_DAILY_TO_DO),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
        )

        self.assertEqual(result.status.value, "replan")

    def test_send_world_chat_message_task_fails_when_the_final_chat_state_is_not_cleared(self) -> None:
        """Fails fast when the reusable send flow does not leave the shared chat draft empty."""

        task = SendWorldChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello world")),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=False,
                chat_draft_text="hello world",
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=False,
                chat_draft_text="hello world",
            ),
        )

        self.assertFalse(result.succeeded)
        self.assertTrue(result.retryable)
