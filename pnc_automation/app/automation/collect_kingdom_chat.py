"""Typed Kingdom Chat archival workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.chat import (
    ChatChannel,
    visible_player_chat_entries,
    visible_unsupported_chat_entries,
)
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.core.errors import TaskVerificationError


@dataclass(frozen=True, slots=True)
class CollectKingdomChatResult:
    """Reports one bounded Kingdom Chat heartbeat archive decision."""

    channel: ChatChannel
    captured_at: datetime
    visible_player_count: int
    appended_count: int
    gap_detected: bool
    snapshot_fingerprint: str
    screenshot_archived: bool

    def __post_init__(self) -> None:
        """Rejects malformed channel identity and archive counters."""

        if self.channel != ChatChannel.WORLD:
            raise ValueError("CollectKingdomChatResult.channel must be Kingdom Chat.")
        if not isinstance(self.captured_at, datetime):
            raise TypeError("CollectKingdomChatResult.captured_at must be a datetime.")
        for field_name in ("visible_player_count", "appended_count"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"CollectKingdomChatResult.{field_name} must be a non-negative integer.")
        if self.appended_count > self.visible_player_count:
            raise ValueError("Appended chat rows cannot exceed the visible player-row count.")
        if type(self.gap_detected) is not bool or type(self.screenshot_archived) is not bool:
            raise TypeError("Kingdom Chat result flags must be booleans.")
        if not isinstance(self.snapshot_fingerprint, str) or not self.snapshot_fingerprint.strip():
            raise ValueError("CollectKingdomChatResult.snapshot_fingerprint cannot be empty.")
        if self.screenshot_archived != (self.appended_count > 0):
            raise ValueError("A Kingdom Chat screenshot is archived exactly when rows are appended.")

    @property
    def changed(self) -> bool:
        """Returns whether the heartbeat appended transcript rows."""

        return self.appended_count > 0


@dataclass(frozen=True, slots=True)
class CollectKingdomChatWorkflow(CoreWorkflow[CollectKingdomChatResult]):
    """Archives one fresh, exact Kingdom Chat viewport through constrained core operations."""

    account_id: str
    active_castle: CastleIdentity
    archive_store: ChatArchiveStore

    _spec: ClassVar[WorkflowSpec] = WorkflowSpec(
        name="collect_kingdom_chat",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
    )

    def __post_init__(self) -> None:
        """Rejects missing identity or persistence dependencies before navigation."""

        if not isinstance(self.account_id, str) or not self.account_id.strip():
            raise ValueError("CollectKingdomChatWorkflow.account_id cannot be empty.")
        if not isinstance(self.active_castle, CastleIdentity):
            raise TypeError("CollectKingdomChatWorkflow.active_castle must be a CastleIdentity.")
        if not isinstance(self.archive_store, ChatArchiveStore):
            raise TypeError("CollectKingdomChatWorkflow.archive_store must be a ChatArchiveStore.")

    @property
    def spec(self) -> WorkflowSpec:
        """Returns the non-spending Home-to-Home workflow contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> CollectKingdomChatResult:
        """Aligns Kingdom Chat, validates its transcript, and persists one heartbeat."""

        context.navigate(ScreenType.PNC_CHAT)
        observation = context.observe_content(expected_screen=ScreenType.PNC_CHAT)
        if observation.active_chat_channel != ChatChannel.WORLD:
            observation = context.select_chat_channel(ChatChannel.WORLD)
        self._require_kingdom_transcript(observation)
        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)
        if not chat_entries:
            raise TaskVerificationError(
                "Kingdom Chat transcript contained no typed chat rows; no archive write was attempted.",
                artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
            )
        unsupported_entries = visible_unsupported_chat_entries(chat_entries)
        if unsupported_entries:
            raise TaskVerificationError(
                "Kingdom Chat contained unsupported transcript rows; no archive write was attempted.",
                unsupported_count=len(unsupported_entries),
                artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
            )
        player_entries = visible_player_chat_entries(chat_entries)
        snapshot = self.archive_store.build_snapshot(player_entries)
        update = self.archive_store.persist_heartbeat(
            account_id=self.account_id,
            castle=self.active_castle,
            channel=ChatChannel.WORLD,
            captured_at=observation.captured_at,
            snapshot=snapshot,
            screenshot_source_path=observation.artifact_path,
        )
        return CollectKingdomChatResult(
            channel=ChatChannel.WORLD,
            captured_at=observation.captured_at,
            visible_player_count=len(player_entries),
            appended_count=len(update.appended_entries),
            gap_detected=update.gap_detected,
            snapshot_fingerprint=snapshot.fingerprint,
            screenshot_archived=update.screenshot_path is not None,
        )

    @staticmethod
    def _require_kingdom_transcript(observation: Observation) -> None:
        """Requires exact channel identity and a persisted source frame."""

        if observation.screen_type != ScreenType.PNC_CHAT or observation.active_chat_channel != ChatChannel.WORLD:
            raise TaskVerificationError(
                "Kingdom Chat content did not confirm the requested channel.",
                observed_screen=observation.screen_type.value,
                observed_channel=None
                if observation.active_chat_channel is None
                else observation.active_chat_channel.value,
            )
        if observation.artifact_path is None or not observation.artifact_path.is_file():
            raise TaskVerificationError(
                "Kingdom Chat archival requires an existing persisted source screenshot.",
                artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
            )
