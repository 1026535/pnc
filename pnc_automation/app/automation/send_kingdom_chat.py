"""Typed Kingdom Chat message workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

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


@dataclass(frozen=True, slots=True)
class SendKingdomChatResult:
    """Reports one sent message with the typed visible receipt proof."""

    channel: ChatChannel
    message: str
    captured_at: datetime
    artifact_path: str | None
    receipt_count: int
    sent_proof: bool

    def __post_init__(self) -> None:
        """Reject malformed channel, message, timestamp, or receipt metadata."""

        if self.channel != ChatChannel.WORLD:
            raise ValueError("SendKingdomChatResult.channel must be Kingdom Chat.")
        if not isinstance(self.message, str) or self.message.strip() == "":
            raise ValueError("SendKingdomChatResult.message must be non-empty.")
        if "\n" in self.message or "\r" in self.message:
            raise ValueError("SendKingdomChatResult.message must be single-line.")
        if not isinstance(self.captured_at, datetime):
            raise TypeError("SendKingdomChatResult.captured_at must be a datetime.")
        if self.artifact_path is not None and not isinstance(self.artifact_path, str):
            raise TypeError("SendKingdomChatResult.artifact_path must be a string or None.")
        if type(self.receipt_count) is not int or self.receipt_count <= 0:
            raise ValueError("SendKingdomChatResult.receipt_count must be positive.")
        if self.sent_proof is not True:
            raise ValueError("SendKingdomChatResult requires positive sent proof.")


@dataclass(frozen=True, slots=True)
class SendKingdomChatWorkflow(CoreWorkflow[SendKingdomChatResult]):
    """Sends one Kingdom Chat message through constrained fresh-control navigation."""

    params: ChatMessageTaskParams
    active_castle: CastleIdentity

    _spec: ClassVar[WorkflowSpec] = WorkflowSpec(
        name="send_kingdom_chat",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
    )

    def __post_init__(self) -> None:
        """Reject missing typed input or active identity before entering the runtime."""

        if not isinstance(self.params, ChatMessageTaskParams):
            raise TypeError("SendKingdomChatWorkflow.params must be ChatMessageTaskParams.")
        if not isinstance(self.active_castle, CastleIdentity):
            raise TypeError("SendKingdomChatWorkflow.active_castle must be a CastleIdentity.")

    @property
    def spec(self) -> WorkflowSpec:
        """Return the non-spending Home-to-Home workflow contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> SendKingdomChatResult:
        """Navigate to Kingdom Chat, send once, and let the runner confirm Home exit."""

        context.navigate(ScreenType.PNC_CHAT)
        observation = context.send_chat_message(
            ChatChannel.WORLD,
            self.params.message,
            self.active_castle,
        )
        receipt_count = count_matching_player_chat_entries(
            observation.entries(ListEntryKind.CHAT_MESSAGE),
            message=self.params.message,
            castle=self.active_castle,
        )
        return SendKingdomChatResult(
            channel=ChatChannel.WORLD,
            message=self.params.message,
            captured_at=observation.captured_at,
            artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
            receipt_count=receipt_count,
            sent_proof=receipt_count > 0,
        )
