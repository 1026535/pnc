"""Tasks that send one message to a fixed P&C chat channel."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import ScriptValidationError
from pnc_automation.pnc.action_requests import ActionRequest, WaitAction
from pnc_automation.pnc.chat import ChatChannel
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_type import ScreenType

_CHAT_SEND_READY_SCREENS = frozenset(
    {
        ScreenType.PNC_HOME_CITY,
        ScreenType.PNC_WORLD_MAP,
        ScreenType.PNC_CHAT,
    }
)


@dataclass(frozen=True, slots=True)
class ChatMessageTaskParams:
    """Carries the script-facing message payload for one fixed-channel chat task."""

    message: str


class _BaseSendChatMessageTask(BaseAutomationTask):
    """Shares parsing and verification for fixed-channel chat-message tasks."""

    channel: ChatChannel

    def parse_params(self, params: Mapping[str, Any]) -> ChatMessageTaskParams:
        """Builds one validated single-message payload for the fixed chat channel."""

        message = params.get("message")
        extra_keys = sorted(key for key in params.keys() if key != "message")
        if extra_keys:
            raise ScriptValidationError(
                f"Task '{self.id}' accepts only the 'message' parameter.",
                task_id=self.id,
                extra_keys=extra_keys,
            )
        if not isinstance(message, str) or message.strip() == "":
            raise ScriptValidationError(
                f"Task '{self.id}' requires a non-empty string 'message' parameter.",
                task_id=self.id,
            )
        return ChatMessageTaskParams(message=message)

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Rejects login-owned states that must be resolved before in-game chat can be used."""

        del context
        return observation.screen_type not in {
            ScreenType.PNC_LOGIN,
            ScreenType.PNC_ACCOUNT_SWITCH,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Returns either one recovery increment or the canonical fixed-channel chat-send flow."""

        if observation.screen_type == ScreenType.PNC_LOADING:
            return [
                WaitAction(
                    milliseconds=1000,
                    reason=f"wait_for_{self.channel.value}_chat_loading",
                    observe_after=True,
                )
            ]
        if observation.screen_type not in _CHAT_SEND_READY_SCREENS:
            return context.flows.ensure_home_city(observation)
        return context.flows.send_chat_message(
            observation,
            message=context.params.message,
            channel=self.channel,
        )

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies either recovery toward a chat-ready screen or one successful fixed-channel send."""

        del context
        if self._send_succeeded(after):
            return TaskResult.success(f"Sent the requested message to {self.channel.value} chat.")
        if before.screen_type not in _CHAT_SEND_READY_SCREENS:
            return self._verify_recovery_increment(after)
        if after.blocking_popup or after.screen_type == ScreenType.PNC_POPUP:
            return TaskResult.replan("Chat send reached a blocking popup and needs centralized recovery.")
        if after.screen_type in {ScreenType.PNC_LOADING, ScreenType.UNKNOWN}:
            return TaskResult.replan("Chat send is still settling after a transition.")
        if after.screen_type == ScreenType.PNC_CHAT and after.active_chat_channel != self.channel:
            return TaskResult.failure(
                f"Chat send did not finish on the expected {self.channel.value} channel.",
                retryable=True,
            )
        if after.screen_type == ScreenType.PNC_CHAT and after.chat_draft_empty is not True:
            return TaskResult.failure(
                "Chat send did not leave the shared draft input empty after sending.",
                retryable=True,
            )
        return TaskResult.failure(
            f"Chat send did not reach a verified {self.channel.value} chat result.",
            retryable=True,
        )

    def _send_succeeded(self, observation: Observation) -> bool:
        """Returns whether the final observation proves one successful fixed-channel chat send."""

        return (
            observation.screen_type == ScreenType.PNC_CHAT
            and observation.active_chat_channel == self.channel
            and observation.chat_draft_empty is True
        )

    def _verify_recovery_increment(self, after: Observation) -> TaskResult:
        """Returns a replan result while the task is still navigating toward a chat-ready screen."""

        if after.blocking_popup or after.screen_type == ScreenType.PNC_POPUP:
            return TaskResult.replan("Chat send reached a blocking popup and needs centralized recovery.")
        if after.screen_type in {ScreenType.PNC_LOADING, ScreenType.UNKNOWN}:
            return TaskResult.replan("Chat send is still settling before message entry.")
        if after.screen_type in _CHAT_SEND_READY_SCREENS:
            return TaskResult.replan(f"Reached {after.screen_type.value} and can now execute the chat send flow.")
        return TaskResult.replan("Chat send is still returning to a chat-ready screen.")


class SendAllianceChatMessageTask(_BaseSendChatMessageTask):
    """Sends one message to alliance chat using the canonical reusable chat flow."""

    id = TaskId.SEND_ALLIANCE_CHAT_MESSAGE
    channel = ChatChannel.ALLIANCE


class SendWorldChatMessageTask(_BaseSendChatMessageTask):
    """Sends one message to world chat using the canonical reusable chat flow."""

    id = TaskId.SEND_WORLD_CHAT_MESSAGE
    channel = ChatChannel.WORLD
