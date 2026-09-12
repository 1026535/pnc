"""Send chat message."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.tasks.send_chat_message_task import SendAllianceChatMessageTask
from pnc_automation.core.errors import ScriptValidationError
from pnc_automation.app.pnc.domain.chat import ChatChannel, ChatMessageTaskParams, parse_chat_message_params
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

    def test_chat_message_parser_rejects_crlf_before_transport(self) -> None:
        """Rejects multiline payloads before the ADB text transport can receive them."""

        for message in ("hello\nworld", "hello\rworld"):
            with self.subTest(message=repr(message)):
                with self.assertRaisesRegex(ScriptValidationError, "multiline"):
                    parse_chat_message_params(
                        {"message": message},
                        task_label="send_alliance_chat_message",
                    )

    def test_chat_message_parser_preserves_exact_public_message_key(self) -> None:
        """Rejects channel or other task parameters because the channel is task-owned."""

        with self.assertRaisesRegex(ScriptValidationError, "only the 'message' parameter"):
            parse_chat_message_params(
                {"message": "hello", "channel": "alliance"},
                task_label="send_alliance_chat_message",
            )

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
