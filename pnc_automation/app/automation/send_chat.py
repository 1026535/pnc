"""Typed chat message workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import (
    ChatChannel,
    ChatMessageTaskParams,
    count_matching_player_chat_entries,
)
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType


_SUPPORTED_SEND_CHANNELS = frozenset({ChatChannel.WORLD, ChatChannel.ALLIANCE})
_WORKFLOW_NAMES = {
    ChatChannel.WORLD: "send_kingdom_chat",
    ChatChannel.ALLIANCE: "send_alliance_chat",
}


@dataclass(frozen=True, slots=True)
class SendChatResult:
    """Reports one sent chat message with typed visible receipt proof."""

    channel: ChatChannel
    message: str
    captured_at: datetime
    artifact_path: str | None
    receipt_count: int
    sent_proof: bool

    def __post_init__(self) -> None:
        """Reject malformed channel, message, timestamp, or receipt metadata."""

        if not isinstance(self.channel, ChatChannel) or self.channel not in _SUPPORTED_SEND_CHANNELS:
            raise ValueError("SendChatResult.channel must be a supported ChatChannel.")
        if not isinstance(self.message, str) or self.message.strip() == "":
            raise ValueError("SendChatResult.message must be non-empty.")
        if "\n" in self.message or "\r" in self.message:
            raise ValueError("SendChatResult.message must be single-line.")
        if not isinstance(self.captured_at, datetime):
            raise TypeError("SendChatResult.captured_at must be a datetime.")
        if self.artifact_path is not None and not isinstance(self.artifact_path, str):
            raise TypeError("SendChatResult.artifact_path must be a string or None.")
        if type(self.receipt_count) is not int or self.receipt_count <= 0:
            raise ValueError("SendChatResult.receipt_count must be positive.")
        if self.sent_proof is not True:
            raise ValueError("SendChatResult requires positive sent proof.")


@dataclass(frozen=True, slots=True)
class SendChatWorkflow(CoreWorkflow[SendChatResult]):
    """Sends one supported chat message through constrained fresh-control navigation."""

    params: ChatMessageTaskParams
    active_castle: CastleIdentity
    channel: ChatChannel

    def __post_init__(self) -> None:
        """Reject missing typed input, identity, or unsupported channel before runtime entry."""

        if not isinstance(self.params, ChatMessageTaskParams):
            raise TypeError("SendChatWorkflow.params must be ChatMessageTaskParams.")
        if not isinstance(self.active_castle, CastleIdentity):
            raise TypeError("SendChatWorkflow.active_castle must be a CastleIdentity.")
        if not isinstance(self.channel, ChatChannel) or self.channel not in _SUPPORTED_SEND_CHANNELS:
            raise ValueError("SendChatWorkflow.channel must be a supported ChatChannel.")

    @property
    def spec(self) -> WorkflowSpec:
        """Return the channel-specific non-spending Home-to-Home contract."""

        return WorkflowSpec(
            name=_WORKFLOW_NAMES[self.channel],
            entry_screen=ScreenType.PNC_HOME_CITY,
            exit_screen=ScreenType.PNC_HOME_CITY,
            effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
        )

    def execute(self, context: WorkflowContext) -> SendChatResult:
        """Navigate to Chat, send once, and let the runner confirm Home exit."""

        context.navigate(ScreenType.PNC_CHAT)
        observation = context.send_chat_message(
            self.channel,
            self.params.message,
            self.active_castle,
        )
        receipt_count = count_matching_player_chat_entries(
            observation.entries(ListEntryKind.CHAT_MESSAGE),
            message=self.params.message,
            castle=self.active_castle,
        )
        return SendChatResult(
            channel=self.channel,
            message=self.params.message,
            captured_at=observation.captured_at,
            artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
            receipt_count=receipt_count,
            sent_proof=receipt_count > 0,
        )
