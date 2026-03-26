"""Canonical task that polls Kingdom Chat and archives newly visible player rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.automation.tasks.active_castle_resolution import (
    plan_active_castle_resolution,
    remember_active_castle_identity,
    require_active_castle_identity,
)
from pnc_automation.pnc.action_requests import ActionRequest, WaitAction
from pnc_automation.pnc.chat import ChatChannel, ChatEntryKind, visible_player_chat_entries
from pnc_automation.pnc.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.vision.observation_request import ObservationRequest


class CollectKingdomChatTask(BaseAutomationTask):
    """Polls the visible Kingdom Chat window once and archives only newly visible player messages."""

    id = TaskId.COLLECT_KINGDOM_CHAT
    castle_target_policy = CastleTargetPolicy.OPTIONAL

    def parse_params(self, params: Mapping[str, Any]) -> None:
        """Rejects unsupported script parameters for the heartbeat poll task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Rejects only login-owned screens that cannot host in-game chat monitoring."""

        del context
        return observation.screen_type not in {ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH}

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans the next recovery, castle-resolution, or chat-alignment increment."""

        if observation.screen_type == ScreenType.UNKNOWN:
            return context.flows.recover_unknown_game_screen(observation, reason="recover_unknown_kingdom_chat_screen")
        if observation.screen_type == ScreenType.PNC_LOADING:
            return [WaitAction(milliseconds=1000, reason="wait_for_kingdom_chat_settle", observe_after=True)]
        if remember_active_castle_identity(context, observation) is None:
            if observation.screen_type not in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU, ScreenType.PNC_LORD_INFO}:
                return context.flows.ensure_home_city(observation)
            return plan_active_castle_resolution(
                context,
                observation,
                task_label="collect_kingdom_chat",
                purpose="archiving",
                require_exact_identity=True,
            )
        if observation.screen_type not in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP, ScreenType.PNC_CHAT}:
            return context.flows.ensure_home_city(observation)
        return context.flows.ensure_chat_channel(observation, ChatChannel.WORLD)

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies navigation completion, performs one transcript observation, and archives the visible delta."""

        del before
        if after.blocking_popup or after.screen_type == ScreenType.PNC_POPUP:
            return TaskResult.replan("Kingdom chat polling reached a blocking popup and needs centralized recovery.")
        if after.screen_type in {ScreenType.PNC_LOADING, ScreenType.UNKNOWN}:
            return TaskResult.replan("Kingdom chat polling is still settling after the previous increment.")
        if remember_active_castle_identity(context, after) is None:
            return TaskResult.replan("Kingdom chat polling is still resolving the active castle before archiving.")
        if after.screen_type != ScreenType.PNC_CHAT:
            return TaskResult.replan("Kingdom chat polling is still navigating toward the shared chat overlay.")
        if after.active_chat_channel != ChatChannel.WORLD:
            return TaskResult.replan("Kingdom chat polling is still aligning the Kingdom chat tab.")
        return self._archive_visible_kingdom_chat(context)

    def _archive_visible_kingdom_chat(self, context: TaskContext) -> TaskResult:
        """Captures one transcript-grade chat observation and persists the visible player delta."""

        capture = context.require_observation_service().capture_observation(
            f"{self.id.value}_transcript",
            request=ObservationRequest.chat_transcript_observation(),
        )
        observation = capture.observation
        if observation.blocking_popup or observation.screen_type == ScreenType.PNC_POPUP:
            return TaskResult.replan("Kingdom chat polling reached a blocking popup during transcript capture.")
        if observation.screen_type != ScreenType.PNC_CHAT or observation.active_chat_channel != ChatChannel.WORLD:
            return TaskResult.replan("Kingdom chat polling is refreshing the final Kingdom transcript state.")
        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)
        unsupported_entries = tuple(
            entry
            for entry in chat_entries
            if entry.metadata.get("chat_entry_kind") == ChatEntryKind.UNSUPPORTED.value
        )
        if unsupported_entries:
            unsupported_diagnostics = tuple(_describe_unsupported_chat_row(entry) for entry in unsupported_entries)
            context.logger.warning(
                "Kingdom chat transcript contained unsupported rows.",
                extra={"unsupported_rows": unsupported_diagnostics},
            )
            return TaskResult.failure(
                "Kingdom chat observation contained unsupported rows that could not be archived safely: "
                + "; ".join(unsupported_diagnostics)
            )
        player_entries = visible_player_chat_entries(chat_entries)
        castle = require_active_castle_identity(context, observation, task_label="collect_kingdom_chat")
        try:
            archive_store = context.require_chat_archive_store()
            update = archive_store.persist_heartbeat(
                account_id=context.account.id,
                castle=castle,
                channel=ChatChannel.WORLD,
                captured_at=observation.captured_at,
                snapshot=archive_store.build_snapshot(player_entries),
                screenshot_payload=capture.screenshot.payload,
                screenshot_source_path=capture.screenshot.artifact_path,
                screenshot_extension=_screenshot_extension(capture.screenshot.image_format),
            )
        except Exception as error:
            context.logger.exception("Kingdom chat archive persistence failed.")
            return TaskResult.failure(f"Kingdom chat archive persistence failed: {error}")
        if not update.changed:
            return TaskResult.success("No new Kingdom chat player messages were visible.")
        if update.gap_detected:
            return TaskResult.success(
                f"Archived {len(update.appended_entries)} new Kingdom chat player message(s) after a visible gap was detected."
            )
        return TaskResult.success(f"Archived {len(update.appended_entries)} new Kingdom chat player message(s).")


def _screenshot_extension(image_format: str) -> str:
    """Returns the canonical durable screenshot extension for one captured image format label."""

    normalized = image_format.strip().lower()
    if normalized in {"png", "jpeg", "jpg", "webp"}:
        return normalized
    return "png"


def _describe_unsupported_chat_row(entry: DetectedListEntry) -> str:
    """Returns one compact diagnostic string describing why a chat row remained unsupported."""

    reason = entry.metadata.get("unsupported_reason")
    sender_evidence = entry.metadata.get("sender_evidence")
    message_evidence = entry.metadata.get("message_evidence")
    preview = entry.metadata.get("message_text")
    if reason == "sender_only":
        return f"sender_only:{_truncate_chat_preview(sender_evidence or preview)}"
    if reason == "message_only":
        return f"message_only:{_truncate_chat_preview(message_evidence or preview)}"
    if isinstance(sender_evidence, str) and sender_evidence.strip() != "" and isinstance(message_evidence, str) and message_evidence.strip() != "":
        return f"ambiguous:{_truncate_chat_preview(sender_evidence)} -> {_truncate_chat_preview(message_evidence)}"
    return f"ambiguous:{_truncate_chat_preview(preview)}"


def _truncate_chat_preview(value: object, *, limit: int = 72) -> str:
    """Returns one normalized preview snippet suitable for failure and log diagnostics."""

    if not isinstance(value, str):
        return "<?>"
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."
