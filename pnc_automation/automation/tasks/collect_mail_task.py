"""Canonical task that collects and archives visible mail threads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.action_requests import ActionRequest, KeyEventAction, TapPointAction, WaitAction
from pnc_automation.pnc.mail import (
    CollectMailParams,
    MailArchiveRecord,
    MailboxType,
    compute_mail_thread_fingerprint,
    normalize_mail_thread_text,
    parse_collect_mail_params,
)
from pnc_automation.pnc.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.vision.observation_request import ObservationRequest


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
            return _plan_active_castle_resolution(context, observation)
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
        if entry is None:
            return []
        target = entry.action_point if entry.action_point is not None else entry.bounds.center()
        context.runtime_state["collect_mail_pending_sender"] = entry.title_text
        return [
            TapPointAction(
                x=target[0],
                y=target[1],
                reason="open_visible_mail_thread",
                observe_after=True,
                follow_up_request=ObservationRequest.mail_thread_observation(),
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
            if _current_visible_thread_entry(context, after) is None:
                _advance_mailbox(context)
                return _collection_progress_result(context, empty_mailbox=False)
            if before.screen_type != ScreenType.PNC_MAILBOX_LIST or before.mailbox_type != mailbox:
                return TaskResult.replan("Mail collection opened the requested mailbox and can inspect visible rows.")
            return TaskResult.replan("Mail collection is opening the next visible thread.")
        return TaskResult.replan("Mail collection is still navigating toward the requested mailbox.")


def _current_mailbox(context: TaskContext) -> MailboxType:
    """Returns the current mailbox target, initializing the remaining-mailboxes queue when needed."""

    if "collect_mail_remaining_mailboxes" not in context.runtime_state:
        context.runtime_state["collect_mail_remaining_mailboxes"] = [mailbox.value for mailbox in context.params.mailboxes]
        context.runtime_state["collect_mail_row_index"] = 0
        context.runtime_state["collect_mail_seen_fingerprints"] = set()
    remaining_raw = context.runtime_state["collect_mail_remaining_mailboxes"]
    if not isinstance(remaining_raw, list) or not remaining_raw:
        raise SelectorResolutionError("collect_mail runtime state is missing the remaining mailbox queue.")
    return MailboxType(remaining_raw[0])


def _remember_active_castle(context: TaskContext, observation: Observation) -> str | None:
    """Caches the active castle label once it becomes trustworthy for archive persistence."""

    cached_label = context.runtime_state.get("collect_mail_active_castle")
    if isinstance(cached_label, str) and cached_label.strip() != "":
        return cached_label
    if observation.current_castle_name is not None and observation.current_castle_name.strip() != "":
        context.runtime_state["collect_mail_active_castle"] = observation.current_castle_name.strip()
        return observation.current_castle_name.strip()
    if context.target_castle is not None and context.target_castle.castle_name.strip() != "":
        context.runtime_state["collect_mail_active_castle"] = context.target_castle.castle_name.strip()
        return context.target_castle.castle_name.strip()
    roster = context.castle_roster
    if roster is not None and len(roster.castles) == 1 and roster.castles[0].castle_name.strip() != "":
        context.runtime_state["collect_mail_active_castle"] = roster.castles[0].castle_name.strip()
        return roster.castles[0].castle_name.strip()
    return None


def _requires_active_castle_resolution(context: TaskContext) -> bool:
    """Returns whether mail archiving still lacks the active-castle label required by the archive layout."""

    active_castle = context.runtime_state.get("collect_mail_active_castle")
    return not isinstance(active_castle, str) or active_castle.strip() == ""


def _plan_active_castle_resolution(context: TaskContext, observation: Observation) -> list[ActionRequest]:
    """Plans the shared active-castle validation needed before archive persistence can begin."""

    if observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}:
        return context.flows.open_lord_info(observation)
    if observation.screen_type == ScreenType.PNC_LORD_INFO:
        if observation.current_castle_name is None or observation.current_castle_name.strip() == "":
            raise SelectorResolutionError(
                "collect_mail reached Lord Info but could not resolve the active castle name.",
                screen_type=observation.screen_type,
            )
        return context.flows.ensure_home_city(observation)
    raise SelectorResolutionError(
        "collect_mail requires an explicit castle target, a single-castle roster, or a home-adjacent screen so it can validate the active castle before archiving.",
        screen_type=observation.screen_type,
    )


def _current_visible_thread_entry(context: TaskContext, observation: Observation) -> DetectedListEntry | None:
    """Returns the currently indexed visible mailbox thread entry within the configured limit."""

    visible_entries = observation.entries(ListEntryKind.MAIL_THREAD)
    if not visible_entries:
        return None
    limit = min(context.params.limit_per_mailbox, len(visible_entries))
    row_index = context.runtime_state.get("collect_mail_row_index", 0)
    if not isinstance(row_index, int) or row_index < 0:
        raise SelectorResolutionError("collect_mail runtime state contains an invalid row index.", row_index=row_index)
    if row_index >= limit:
        return None
    return visible_entries[row_index]


def _archive_open_thread(context: TaskContext, observation: Observation) -> TaskResult:
    """Archives the currently opened thread and advances the visible-row index."""

    mailbox = _current_mailbox(context)
    sender_name = context.runtime_state.get("collect_mail_pending_sender")
    if not isinstance(sender_name, str) or sender_name.strip() == "":
        raise SelectorResolutionError("collect_mail is missing the sender name for the opened thread archive.")
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
    context.runtime_state["collect_mail_row_index"] = context.runtime_state.get("collect_mail_row_index", 0) + 1
    context.runtime_state.pop("collect_mail_pending_sender", None)
    return TaskResult.replan("Mail collection archived the opened thread and is returning to the mailbox list.")


def _advance_mailbox(context: TaskContext) -> None:
    """Advances the remaining-mailboxes queue and resets visible-row iteration state."""

    remaining_raw = context.runtime_state.get("collect_mail_remaining_mailboxes")
    if not isinstance(remaining_raw, list) or not remaining_raw:
        raise SelectorResolutionError("collect_mail runtime state is missing the remaining mailbox queue.")
    remaining_raw.pop(0)
    context.runtime_state["collect_mail_row_index"] = 0
    context.runtime_state.pop("collect_mail_pending_sender", None)


def _collection_progress_result(context: TaskContext, *, empty_mailbox: bool) -> TaskResult:
    """Returns either the next-mailbox replan or the terminal collection success result."""

    remaining_raw = context.runtime_state.get("collect_mail_remaining_mailboxes")
    if not isinstance(remaining_raw, list):
        raise SelectorResolutionError("collect_mail runtime state is missing the remaining mailbox queue.")
    if not remaining_raw:
        return TaskResult.success("Mail collection archived the requested visible threads from all requested mailboxes.")
    if empty_mailbox:
        return TaskResult.replan("Mail collection finished an empty mailbox and is advancing to the next mailbox.")
    return TaskResult.replan("Mail collection finished the visible thread window for one mailbox and is advancing.")


def _active_castle_label(context: TaskContext, observation: Observation) -> str:
    """Returns the canonical active-castle label used for mail archive paths."""

    remembered = _remember_active_castle(context, observation)
    if remembered is not None:
        return remembered
    raise SelectorResolutionError(
        "collect_mail could not resolve the active castle required for archive persistence.",
        screen_type=observation.screen_type,
    )
