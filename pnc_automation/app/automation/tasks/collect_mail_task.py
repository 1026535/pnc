"""Canonical task that collects and archives visible mail threads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.app.automation.engine.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.automation.tasks.active_castle_resolution import (
    plan_active_castle_resolution,
    remember_active_castle_name,
    require_active_castle_name,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, KeyEventAction, SwipeAction, TapPointAction, WaitAction
from pnc_automation.app.pnc.domain.mail import (
    CollectMailParams,
    MailArchiveRecord,
    MailboxType,
    compute_mail_thread_fingerprint,
    normalize_mail_text,
    normalize_mail_thread_text,
    parse_collect_mail_params,
)
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest


class CollectMailTask(BaseAutomationTask):
    """Collects visible mail threads from one or more mailboxes and archives them deterministically."""

    id = TaskId.COLLECT_MAIL
    castle_target_policy = CastleTargetPolicy.OPTIONAL

    def parse_params(self, params: Mapping[str, Any]) -> CollectMailParams:
        """Builds the validated canonical collect-mail payload."""

        return parse_collect_mail_params(task_label=self.id, params=params)

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Rejects only login-owned states that cannot host in-game mail collection."""

        del context
        return observation.screen_type not in {ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH}

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans the next canonical collect-mail increment."""

        _remember_active_castle(context, observation)
        if observation.screen_type in {ScreenType.PNC_LOADING, ScreenType.UNKNOWN}:
            return [WaitAction(milliseconds=1000, reason="wait_for_mail_collection_settle", observe_after=True)]
        if _requires_active_castle_resolution(context):
            return plan_active_castle_resolution(
                context,
                observation,
                task_label="collect_mail",
                purpose="archiving",
                require_exact_identity=False,
            )
        mailbox = _current_mailbox(context)
        if observation.screen_type == ScreenType.PNC_MAIL_THREAD:
            return [
                KeyEventAction(
                    key_code="KEYCODE_BACK",
                    reason="return_to_mailbox_after_archive",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mailbox_observation(mailbox),
                )
            ]
        if observation.screen_type != ScreenType.PNC_MAILBOX_LIST or observation.mailbox_type != mailbox:
            return context.flows.open_mailbox(observation, mailbox)
        if observation.mailbox_empty:
            return []
        entry = _current_visible_thread_entry(context, observation)
        if entry is not None:
            target = entry.action_point if entry.action_point is not None else entry.bounds.center()
            context.runtime_state["collect_mail_pending_sender"] = entry.title_text
            context.runtime_state["collect_mail_pending_row_key"] = _mailbox_row_key(entry)
            return [
                TapPointAction(
                    x=target[0],
                    y=target[1],
                    reason="open_visible_mail_thread",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_thread_observation(),
                )
            ]
        if _mailbox_collection_limit_reached(context) or not observation.entries(ListEntryKind.MAIL_THREAD):
            return []
        return [
            SwipeAction(
                direction="up",
                distance_ratio=0.58,
                duration_ms=450,
                reason="scroll_mailbox_threads",
                observe_after=True,
                follow_up_request=ObservationRequest.mailbox_observation(mailbox),
            )
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies mailbox iteration, thread archiving, and mailbox-to-mailbox progression."""

        _remember_active_castle(context, before)
        _remember_active_castle(context, after)
        if after.blocking_popup or after.screen_type == ScreenType.PNC_POPUP:
            return TaskResult.replan("Mail collection reached a blocking popup and needs centralized recovery.")
        if after.screen_type in {ScreenType.PNC_LOADING, ScreenType.UNKNOWN}:
            return TaskResult.replan("Mail collection is still settling after the previous increment.")
        if _requires_active_castle_resolution(context):
            return TaskResult.replan("Mail collection is resolving the active castle before archiving.")
        if after.screen_type == ScreenType.PNC_MAIL_THREAD:
            return _archive_open_thread(context, after)
        mailbox = _current_mailbox(context)
        if after.screen_type == ScreenType.PNC_MAILBOX_LIST and after.mailbox_type == mailbox:
            if after.mailbox_empty:
                _advance_mailbox(context)
                return _collection_progress_result(context, empty_mailbox=True)
            if _mailbox_collection_limit_reached(context):
                _advance_mailbox(context)
                return _collection_progress_result(context, empty_mailbox=False)
            next_entry = _current_visible_thread_entry(context, after)
            if next_entry is None:
                if _mailbox_scroll_stalled(context, before=before, after=after):
                    _advance_mailbox(context)
                    return _collection_progress_result(context, empty_mailbox=False)
                return TaskResult.replan("Mail collection is scrolling to more mailbox threads.")
            if before.screen_type != ScreenType.PNC_MAILBOX_LIST or before.mailbox_type != mailbox:
                return TaskResult.replan("Mail collection opened the requested mailbox and can inspect visible rows.")
            return TaskResult.replan("Mail collection is opening the next visible thread.")
        return TaskResult.replan("Mail collection is still navigating toward the requested mailbox.")


def _current_mailbox(context: TaskContext) -> MailboxType:
    """Returns the current mailbox target, initializing the remaining-mailboxes queue when needed."""

    if "collect_mail_remaining_mailboxes" not in context.runtime_state:
        context.runtime_state["collect_mail_remaining_mailboxes"] = [mailbox.value for mailbox in context.params.mailboxes]
        context.runtime_state["collect_mail_seen_fingerprints"] = set()
        _reset_mailbox_iteration_state(context)
    remaining_raw = context.runtime_state["collect_mail_remaining_mailboxes"]
    if not isinstance(remaining_raw, list) or not remaining_raw:
        raise SelectorResolutionError("collect_mail runtime state is missing the remaining mailbox queue.")
    return MailboxType(remaining_raw[0])


def _reset_mailbox_iteration_state(context: TaskContext) -> None:
    """Resets the current-mailbox traversal state before processing a fresh mailbox window sequence."""

    context.runtime_state["collect_mail_seen_row_keys"] = set()
    context.runtime_state["collect_mail_collected_count"] = 0
    context.runtime_state["collect_mail_scroll_stalls"] = 0
    context.runtime_state.pop("collect_mail_pending_sender", None)
    context.runtime_state.pop("collect_mail_pending_row_key", None)


def _remember_active_castle(context: TaskContext, observation: Observation) -> str | None:
    """Caches the active castle label once it becomes trustworthy for archive persistence."""

    remembered = remember_active_castle_name(context, observation)
    if remembered is None:
        return None
    context.runtime_state["collect_mail_active_castle"] = remembered
    return remembered


def _requires_active_castle_resolution(context: TaskContext) -> bool:
    """Returns whether mail archiving still lacks the active-castle label required by the archive layout."""

    active_castle = context.runtime_state.get("collect_mail_active_castle")
    return not isinstance(active_castle, str) or active_castle.strip() == ""


def _plan_active_castle_resolution(context: TaskContext, observation: Observation) -> list[ActionRequest]:
    """Plans the shared active-castle validation needed before archive persistence can begin."""

    return plan_active_castle_resolution(
        context,
        observation,
        task_label="collect_mail",
        purpose="archiving",
        require_exact_identity=False,
    )


def _current_visible_thread_entry(context: TaskContext, observation: Observation) -> DetectedListEntry | None:
    """Returns the next unseen visible mailbox thread entry while the requested mailbox limit remains open."""

    if _mailbox_collection_limit_reached(context):
        return None
    seen_row_keys = _mailbox_seen_row_keys(context)
    for entry in observation.entries(ListEntryKind.MAIL_THREAD):
        if _mailbox_row_key(entry) not in seen_row_keys:
            return entry
    return None


def _archive_open_thread(context: TaskContext, observation: Observation) -> TaskResult:
    """Archives the currently opened thread and advances the multi-window mailbox traversal state."""

    mailbox = _current_mailbox(context)
    sender_name = context.runtime_state.get("collect_mail_pending_sender")
    if not isinstance(sender_name, str) or sender_name.strip() == "":
        raise SelectorResolutionError("collect_mail is missing the sender name for the opened thread archive.")
    pending_row_key = context.runtime_state.get("collect_mail_pending_row_key")
    if not isinstance(pending_row_key, str) or pending_row_key == "":
        raise SelectorResolutionError("collect_mail is missing the mailbox row identity for the opened thread archive.")
    message_entries = observation.entries(ListEntryKind.MAIL_MESSAGE)
    if not message_entries:
        return TaskResult.failure("Opened mail thread did not expose any visible message text.", retryable=True)
    normalized_thread_text = normalize_mail_thread_text(
        tuple(entry.title_text or "" for entry in message_entries)
    )
    timestamp_text = next(
        (
            metadata_timestamp
            for entry in message_entries
            if isinstance((metadata_timestamp := entry.metadata.get("timestamp_text")), str) and metadata_timestamp.strip() != ""
        ),
        None,
    )
    fingerprint = compute_mail_thread_fingerprint(
        mailbox_type=mailbox,
        sender_name=sender_name,
        timestamp_text=timestamp_text,
        normalized_thread_text=normalized_thread_text,
    )
    collected_fingerprints = context.runtime_state.setdefault("collect_mail_seen_fingerprints", set())
    if not isinstance(collected_fingerprints, set):
        raise SelectorResolutionError("collect_mail runtime state contains an invalid fingerprint cache.")
    archive_store = context.require_mail_archive_store()
    already_seen = fingerprint.value in collected_fingerprints
    already_archived = context.params.only_new and archive_store.has_fingerprint(
        active_castle=_active_castle_label(context, observation),
        mailbox_type=mailbox.value,
        fingerprint=fingerprint.value,
    )
    if not already_seen and not already_archived:
        archive_store.persist(
            record=MailArchiveRecord(
                account_id=context.account.id,
                pnc_account_id=context.account.pnc_account_id,
                active_castle=_active_castle_label(context, observation),
                mailbox_type=mailbox,
                sender_name=sender_name,
                thread_timestamp_text=timestamp_text,
                fingerprint=fingerprint,
                captured_at=observation.captured_at,
                normalized_thread_text=normalized_thread_text,
                source_artifact_paths=() if observation.artifact_path is None else (observation.artifact_path,),
            ),
            archive_mode=context.params.archive_mode,
            screenshot_source_path=observation.artifact_path,
            skip_existing=context.params.only_new,
        )
    collected_fingerprints.add(fingerprint.value)
    _mailbox_seen_row_keys(context).add(pending_row_key)
    context.runtime_state["collect_mail_collected_count"] = _mailbox_collected_count(context) + 1
    context.runtime_state["collect_mail_scroll_stalls"] = 0
    context.runtime_state.pop("collect_mail_pending_sender", None)
    context.runtime_state.pop("collect_mail_pending_row_key", None)
    return TaskResult.replan("Mail collection archived the opened thread and is returning to the mailbox list.")


def _advance_mailbox(context: TaskContext) -> None:
    """Advances the remaining-mailboxes queue and resets traversal state for the next mailbox."""

    remaining_raw = context.runtime_state.get("collect_mail_remaining_mailboxes")
    if not isinstance(remaining_raw, list) or not remaining_raw:
        raise SelectorResolutionError("collect_mail runtime state is missing the remaining mailbox queue.")
    remaining_raw.pop(0)
    _reset_mailbox_iteration_state(context)


def _collection_progress_result(context: TaskContext, *, empty_mailbox: bool) -> TaskResult:
    """Returns either the next-mailbox replan or the terminal collection success result."""

    remaining_raw = context.runtime_state.get("collect_mail_remaining_mailboxes")
    if not isinstance(remaining_raw, list):
        raise SelectorResolutionError("collect_mail runtime state is missing the remaining mailbox queue.")
    if not remaining_raw:
        return TaskResult.success("Mail collection archived the requested mailbox threads from all requested mailboxes.")
    if empty_mailbox:
        return TaskResult.replan("Mail collection finished an empty mailbox and is advancing to the next mailbox.")
    return TaskResult.replan("Mail collection finished the requested mailbox threads for one mailbox and is advancing.")


def _mailbox_collection_limit_reached(context: TaskContext) -> bool:
    """Returns whether the current mailbox already processed the requested number of thread rows."""

    return _mailbox_collected_count(context) >= context.params.limit_per_mailbox


def _mailbox_collected_count(context: TaskContext) -> int:
    """Returns how many rows the current mailbox already processed across all visited windows."""

    collected_count = context.runtime_state.get("collect_mail_collected_count", 0)
    if not isinstance(collected_count, int) or collected_count < 0:
        raise SelectorResolutionError(
            "collect_mail runtime state contains an invalid collected-row count.",
            collected_count=collected_count,
        )
    return collected_count


def _mailbox_seen_row_keys(context: TaskContext) -> set[str]:
    """Returns the set of mailbox row identities already processed for the current mailbox."""

    seen_row_keys = context.runtime_state.setdefault("collect_mail_seen_row_keys", set())
    if not isinstance(seen_row_keys, set):
        raise SelectorResolutionError("collect_mail runtime state contains an invalid seen-row cache.")
    return seen_row_keys


def _mailbox_row_key(entry: DetectedListEntry) -> str:
    """Builds a stable mailbox-row identity from the visible sender, preview, and date chrome."""

    date_text = entry.metadata.get("date_text")
    normalized_date = normalize_mail_text(date_text) if isinstance(date_text, str) else ""
    return "|".join(
        (
            normalize_mail_text(entry.title_text or ""),
            normalize_mail_text(entry.subtitle_text or ""),
            normalized_date,
        )
    )


def _mailbox_scroll_stalled(context: TaskContext, *, before: Observation, after: Observation) -> bool:
    """Returns whether a mailbox-list swipe failed to reveal any new row identities."""

    after_signature = tuple(_mailbox_row_key(entry) for entry in after.entries(ListEntryKind.MAIL_THREAD))
    if not after_signature:
        return True
    before_signature = (
        tuple(_mailbox_row_key(entry) for entry in before.entries(ListEntryKind.MAIL_THREAD))
        if before.screen_type == ScreenType.PNC_MAILBOX_LIST and before.mailbox_type == after.mailbox_type
        else ()
    )
    if after_signature != before_signature:
        context.runtime_state["collect_mail_scroll_stalls"] = 0
        return False
    stall_count = context.runtime_state.get("collect_mail_scroll_stalls", 0)
    if not isinstance(stall_count, int) or stall_count < 0:
        raise SelectorResolutionError("collect_mail runtime state contains an invalid mailbox-scroll stall count.")
    context.runtime_state["collect_mail_scroll_stalls"] = stall_count + 1
    return True


def _active_castle_label(context: TaskContext, observation: Observation) -> str:
    """Returns the canonical active-castle label used for mail archive paths."""

    label = require_active_castle_name(context, observation, task_label="collect_mail")
    context.runtime_state["collect_mail_active_castle"] = label
    return label
