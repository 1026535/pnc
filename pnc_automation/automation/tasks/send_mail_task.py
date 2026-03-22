"""Canonical task that sends mail through the shared mail workflow."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.action_requests import ActionRequest, InputTextAction, TapPointAction, WaitAction
from pnc_automation.pnc.mail import (
    MailRecipientKind,
    MailboxType,
    PlayerProfileRouteKind,
    SendMailParams,
    compose_target_label_for_alliance,
    mailbox_for_recipient_kind,
    normalize_mail_text,
    parse_send_mail_params,
)
from pnc_automation.pnc.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_request import ObservationRequest


class SendMailTask(BaseAutomationTask):
    """Sends one player or alliance mail through the shared compose and verification flow."""

    id = TaskId.SEND_MAIL
    castle_target_policy = CastleTargetPolicy.OPTIONAL

    def max_replans_per_step(self, context: TaskContext) -> int | None:
        """Grants extra bounded replan budget only to list-backed profile-route send flows."""

        route = context.params.profile_route
        if route is not None and route.kind in {PlayerProfileRouteKind.ALLIANCE_MEMBER, PlayerProfileRouteKind.MIGHT_RANK}:
            return 20
        return None

    def parse_params(self, params: Mapping[str, Any]) -> SendMailParams:
        """Builds the validated canonical send-mail payload."""

        return parse_send_mail_params(task_label=self.id, params=params)

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Rejects only login-owned states that cannot host in-game mail navigation."""

        del context
        return observation.screen_type not in {ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH}

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans the next canonical send-mail increment for the current phase."""

        phase = _resolve_send_phase(context)
        if observation.screen_type == ScreenType.UNKNOWN:
            return context.flows.recover_unknown_game_screen(
                observation,
                reason="recover_unknown_mail_screen",
            )
        if observation.screen_type == ScreenType.PNC_LOADING:
            return [WaitAction(milliseconds=1000, reason="wait_for_mail_workflow_settle", observe_after=True)]
        if phase == "compose":
            compose_target_repair = _plan_compose_target_repair(context, observation)
            if compose_target_repair:
                return compose_target_repair
            return context.flows.open_mail_compose(observation, context.params, runtime_state=context.runtime_state)
        if phase == "send":
            if observation.screen_type != ScreenType.PNC_MAIL_COMPOSE_POPUP:
                return context.flows.open_mail_compose(observation, context.params, runtime_state=context.runtime_state)
            return context.flows.send_mail(observation, context.params)
        if phase == "verify_mailbox":
            return _plan_mailbox_verification(context, observation)
        if phase == "verify_thread":
            return _plan_thread_verification(context, observation)
        raise SelectorResolutionError("Unsupported send_mail phase.", phase=phase)

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies the current send-mail phase and advances the shared task state."""

        phase = _resolve_send_phase(context)
        _refresh_expected_profile_target(context, before)
        _refresh_expected_profile_target(context, after)
        alliance_compose_block = _verify_alliance_compose_entry(context, before=before, after=after)
        if alliance_compose_block is not None:
            return alliance_compose_block
        direct_player_compose_block = _verify_direct_player_compose_entry(context, before=before, after=after)
        if direct_player_compose_block is not None:
            return direct_player_compose_block
        if after.blocking_popup or after.screen_type == ScreenType.PNC_POPUP:
            return TaskResult.replan("Mail workflow reached a blocking popup and needs centralized recovery.")
        if after.screen_type in {ScreenType.PNC_LOADING, ScreenType.UNKNOWN}:
            return TaskResult.replan("Mail workflow is still settling after the previous increment.")
        if phase == "compose":
            if _hit_invalid_alliance_route_source(context, before=before, after=after):
                return TaskResult.failure(
                    "Alliance profile-route acquisition opened Mail instead of Alliance from the home-city source screen.",
                )
            if after.screen_type != ScreenType.PNC_MAIL_COMPOSE_POPUP:
                return TaskResult.replan("Mail workflow is still navigating toward the compose popup.")
            if _compose_target_matches(context, after):
                _set_send_phase(context, "send")
                return TaskResult.replan("Mail compose popup is ready for subject and body entry.")
            if _compose_target_requires_manual_entry(context):
                return TaskResult.replan("Mail compose popup is open and still needs the requested player target typed.")
            return TaskResult.failure(
                "Mail compose popup opened with an unexpected target recipient.",
                retryable=True,
            )
        if phase == "send":
            if after.screen_type == ScreenType.PNC_MAIL_COMPOSE_POPUP:
                return TaskResult.failure(
                    "Mail send did not close the compose popup cleanly.",
                    retryable=True,
                )
            _set_send_phase(context, "verify_mailbox")
            return TaskResult.replan("Mail compose closed; reopening the mailbox to verify the sent mail.")
        if phase == "verify_mailbox":
            return _verify_mailbox_verification(context, before=before, after=after)
        if phase == "verify_thread":
            return _verify_thread_verification(context, before=before, after=after)
        raise SelectorResolutionError("Unsupported send_mail phase.", phase=phase)


def _resolve_send_phase(context: TaskContext) -> str:
    """Returns the current send-mail phase, initializing the task-local phase when needed."""

    raw_phase = context.runtime_state.setdefault("send_mail_phase", "compose")
    if raw_phase in {"compose", "send", "verify_mailbox", "verify_thread"}:
        return raw_phase
    raise SelectorResolutionError("Unsupported send_mail runtime phase.", phase=raw_phase)


def _set_send_phase(context: TaskContext, phase: str) -> None:
    """Stores the active send-mail phase after validating the canonical phase names."""

    if phase not in {"compose", "send", "verify_mailbox", "verify_thread"}:
        raise SelectorResolutionError("Unsupported send_mail runtime phase.", phase=phase)
    context.runtime_state["send_mail_phase"] = phase


def _hit_invalid_alliance_route_source(context: TaskContext, *, before: Observation, after: Observation) -> bool:
    """Returns whether an alliance-backed profile route misfired into Mail from the home source screen."""

    route = context.params.profile_route
    if route is None or route.kind not in {PlayerProfileRouteKind.ALLIANCE_MEMBER, PlayerProfileRouteKind.MIGHT_RANK}:
        return False
    return before.screen_type == ScreenType.PNC_HOME_CITY and after.screen_type == ScreenType.PNC_MAIL_HUB


def _verify_alliance_compose_entry(context: TaskContext, *, before: Observation, after: Observation) -> TaskResult | None:
    """Returns one compose-phase result when alliance mail is blocked or repeatedly fails to open."""

    if context.params.recipient_kind != MailRecipientKind.ALLIANCE:
        context.runtime_state.pop("alliance_compose_open_attempts", None)
        return None
    if before.screen_type != ScreenType.PNC_ALLIANCE_HOME:
        context.runtime_state.pop("alliance_compose_open_attempts", None)
        return None
    status_banner = after.get(UiElementId.PNC_STATUS_BANNER)
    if status_banner is not None:
        return TaskResult.failure(_alliance_mail_block_message(status_banner.extracted_text))
    if after.screen_type != ScreenType.PNC_ALLIANCE_HOME:
        context.runtime_state.pop("alliance_compose_open_attempts", None)
        return None
    attempts = int(context.runtime_state.get("alliance_compose_open_attempts", 0)) + 1
    context.runtime_state["alliance_compose_open_attempts"] = attempts
    if attempts >= 2:
        return TaskResult.failure(
            "Alliance Mail did not open from Alliance home after two compose-entry attempts.",
            retryable=True,
        )
    return TaskResult.replan("Alliance Mail stayed on Alliance home after one tap; retrying once.")


def _alliance_mail_block_message(banner_text: str | None) -> str:
    """Returns the canonical failure message for one alliance-mail gameplay gate banner."""

    normalized_banner = normalize_mail_text("" if banner_text is None else banner_text)
    if normalized_banner == "PLEASECLEARCAMPAIGNCH3FIRST":
        return "Alliance Mail is unavailable from Alliance home until Campaign Ch.3 is cleared."
    cleaned_banner = "" if banner_text is None else banner_text.strip()
    if cleaned_banner != "":
        return f"Alliance Mail is unavailable from Alliance home: {cleaned_banner}"
    return "Alliance Mail is unavailable from Alliance home due to an in-game status banner."


def _verify_direct_player_compose_entry(
    context: TaskContext,
    *,
    before: Observation,
    after: Observation,
) -> TaskResult | None:
    """Returns one compose-entry result when direct player-mail compose stays on its source screen."""

    if context.params.recipient_kind != MailRecipientKind.PLAYER or context.params.player_name is None:
        context.runtime_state.pop("direct_player_compose_open_attempts", None)
        return None
    source_screen = before.screen_type
    if source_screen not in {ScreenType.PNC_MAIL_HUB, ScreenType.PNC_MAILBOX_LIST}:
        context.runtime_state.pop("direct_player_compose_open_attempts", None)
        return None
    if source_screen == ScreenType.PNC_MAILBOX_LIST and before.mailbox_type != MailboxType.PLAYER:
        context.runtime_state.pop("direct_player_compose_open_attempts", None)
        return None
    if after.screen_type == ScreenType.PNC_MAIL_COMPOSE_POPUP:
        context.runtime_state.pop("direct_player_compose_open_attempts", None)
        return None
    if after.screen_type != source_screen:
        context.runtime_state.pop("direct_player_compose_open_attempts", None)
        return None
    attempts = int(context.runtime_state.get("direct_player_compose_open_attempts", 0)) + 1
    context.runtime_state["direct_player_compose_open_attempts"] = attempts
    if attempts >= 2:
        location_label = "the Mail hub" if source_screen == ScreenType.PNC_MAIL_HUB else "the Player mailbox"
        return TaskResult.failure(
            f"Player mail compose did not open from {location_label} after two compose-entry attempts.",
            retryable=True,
        )
    location_label = "Mail hub" if source_screen == ScreenType.PNC_MAIL_HUB else "Player mailbox"
    return TaskResult.replan(f"Player mail compose stayed on {location_label} after one tap; retrying once.")


def _plan_compose_target_repair(context: TaskContext, observation: Observation) -> list[ActionRequest]:
    """Returns one target-field repair action when direct player mail opens the wrong compose target."""

    params = context.params
    if observation.screen_type != ScreenType.PNC_MAIL_COMPOSE_POPUP:
        return []
    if params.recipient_kind != MailRecipientKind.PLAYER or params.player_name is None:
        return []
    if _compose_target_matches(context, observation):
        return []
    return [
        InputTextAction(
            selector_id=UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD,
            text=params.player_name,
            replace_existing=True,
            reason="repair_mail_target_player",
            observe_after=True,
            follow_up_request=ObservationRequest.mail_compose_follow_up(),
        )
    ]


@dataclass(frozen=True, slots=True)
class _SentMailMailboxMatch:
    """Describes one visible mailbox row plus whether mailbox-only evidence is already sufficient."""

    entry: DetectedListEntry
    mailbox_only_confident: bool


def _plan_mailbox_verification(context: TaskContext, observation: Observation) -> list[ActionRequest]:
    """Returns the next mailbox-level verification increment after a send."""

    mailbox = mailbox_for_recipient_kind(context.params.recipient_kind)
    if observation.screen_type == ScreenType.PNC_MAILBOX_LIST and observation.mailbox_type == mailbox:
        match = _find_matching_sent_thread(context, observation)
        if match is None or match.mailbox_only_confident:
            return []
        _set_send_phase(context, "verify_thread")
        return [_open_mail_thread_action(match.entry, reason="verify_sent_mail_thread")]
    _set_send_phase(context, "verify_mailbox")
    return context.flows.open_mailbox(observation, mailbox)


def _plan_thread_verification(context: TaskContext, observation: Observation) -> list[ActionRequest]:
    """Returns the next thread-confirmation increment when mailbox evidence alone is insufficient."""

    mailbox = mailbox_for_recipient_kind(context.params.recipient_kind)
    if observation.screen_type == ScreenType.PNC_MAIL_THREAD:
        return []
    if observation.screen_type == ScreenType.PNC_MAILBOX_LIST and observation.mailbox_type == mailbox:
        match = _find_matching_sent_thread(context, observation)
        if match is None:
            return []
        return [_open_mail_thread_action(match.entry, reason="verify_sent_mail_thread")]
    _set_send_phase(context, "verify_mailbox")
    return context.flows.open_mailbox(observation, mailbox)


def _verify_mailbox_verification(context: TaskContext, *, before: Observation, after: Observation) -> TaskResult:
    """Verifies mailbox reopening and promotes ambiguous matches to explicit thread confirmation."""

    mailbox = mailbox_for_recipient_kind(context.params.recipient_kind)
    if after.screen_type == ScreenType.PNC_MAIL_THREAD:
        _set_send_phase(context, "verify_thread")
        if _thread_matches_sent_mail(context, after):
            return TaskResult.success("Sent mail was confirmed in the reopened mailbox thread.")
        return TaskResult.failure(
            "Opened mail thread did not contain the expected sent subject or body.",
            retryable=True,
        )
    if after.screen_type == ScreenType.PNC_MAILBOX_LIST and after.mailbox_type == mailbox:
        matching_entry = _find_matching_sent_thread(context, after)
        if matching_entry is not None and matching_entry.mailbox_only_confident:
            return TaskResult.success("Sent mail was located in the reopened mailbox.")
        if matching_entry is not None:
            _set_send_phase(context, "verify_thread")
            return TaskResult.replan("Sent-mail verification found a plausible mailbox row and is opening the thread.")
        if after.mailbox_empty:
            return TaskResult.failure("Sent-mail verification reopened an empty mailbox after sending.", retryable=True)
        if before.screen_type == ScreenType.PNC_MAILBOX_LIST and before.mailbox_type == mailbox:
            return TaskResult.failure(
                "Sent mail could not be located in the requested mailbox.",
                retryable=True,
            )
        return TaskResult.replan("Sent-mail verification reached the requested mailbox and is inspecting visible rows.")
    return TaskResult.replan("Sent-mail verification is still returning to the requested mailbox.")


def _verify_thread_verification(context: TaskContext, *, before: Observation, after: Observation) -> TaskResult:
    """Verifies that an opened candidate thread actually contains the mail that was just sent."""

    mailbox = mailbox_for_recipient_kind(context.params.recipient_kind)
    if after.screen_type == ScreenType.PNC_MAIL_THREAD:
        if _thread_matches_sent_mail(context, after):
            return TaskResult.success("Sent mail was confirmed in the reopened mailbox thread.")
        return TaskResult.failure(
            "Opened mail thread did not contain the expected sent subject or body.",
            retryable=True,
        )
    if after.screen_type == ScreenType.PNC_MAILBOX_LIST and after.mailbox_type == mailbox:
        matching_entry = _find_matching_sent_thread(context, after)
        if matching_entry is None:
            _set_send_phase(context, "verify_mailbox")
            if after.mailbox_empty:
                return TaskResult.failure("Sent-mail verification reopened an empty mailbox after sending.", retryable=True)
            if before.screen_type == ScreenType.PNC_MAILBOX_LIST and before.mailbox_type == mailbox:
                return TaskResult.failure(
                    "Sent mail could not be located in the requested mailbox.",
                    retryable=True,
                )
            return TaskResult.replan("Sent-mail verification is returning to the mailbox to locate a candidate thread.")
        return TaskResult.replan("Sent-mail verification is opening the matching thread for confirmation.")
    _set_send_phase(context, "verify_mailbox")
    return TaskResult.replan("Sent-mail verification is returning to the requested mailbox.")


def _compose_target_matches(context: TaskContext, observation: Observation) -> bool:
    """Returns whether the compose popup target field matches the intended recipient."""

    expected_target = _expected_target_name(context)
    if observation.screen_type != ScreenType.PNC_MAIL_COMPOSE_POPUP or expected_target is None:
        return False
    state = observation.text_field_state(UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD)
    if state is None or state.text is None:
        return False
    return normalize_mail_text(state.text) == normalize_mail_text(expected_target)


def _compose_target_requires_manual_entry(context: TaskContext) -> bool:
    """Returns whether the current request expects a manually typed compose target after the popup opens."""

    return context.params.recipient_kind == MailRecipientKind.PLAYER and context.params.player_name is not None


def _expected_target_name(context: TaskContext) -> str | None:
    """Returns the intended compose target name for the current send-mail request."""

    params = context.params
    if params.recipient_kind == MailRecipientKind.ALLIANCE:
        return compose_target_label_for_alliance()
    if params.player_name is not None:
        return params.player_name
    expected_profile_target = context.runtime_state.get("expected_profile_target")
    if isinstance(expected_profile_target, str) and expected_profile_target.strip() != "":
        return expected_profile_target.strip()
    if params.profile_route is not None and params.profile_route.player_name is not None:
        return params.profile_route.player_name
    return None


def _refresh_expected_profile_target(context: TaskContext, observation: Observation) -> None:
    """Refreshes the authoritative profile-route recipient name from the currently observed remote profile."""

    if observation.screen_type != ScreenType.PNC_PLAYER_PROFILE or observation.profile_player_name is None:
        return
    observed_name = observation.profile_player_name.strip()
    if observed_name != "":
        context.runtime_state["expected_profile_target"] = observed_name


def _find_matching_sent_thread(context: TaskContext, observation: Observation) -> _SentMailMailboxMatch | None:
    """Returns the best visible mailbox row that matches the sent mail and whether mailbox-only proof is sufficient."""

    expected_target = _expected_target_name(context)
    normalized_target = None if expected_target is None else normalize_mail_text(expected_target)
    subject_text = normalize_mail_text(context.params.subject)
    body_text = normalize_mail_text(context.params.body)
    body_first_line = normalize_mail_text(context.params.body.splitlines()[0]) if context.params.body.splitlines() else body_text
    ambiguous_match: _SentMailMailboxMatch | None = None
    for entry in observation.entries(ListEntryKind.MAIL_THREAD):
        title_text = normalize_mail_text(entry.title_text or "")
        preview_text = normalize_mail_text(entry.subtitle_text or "")
        if subject_text != "" and (subject_text in title_text or subject_text in preview_text):
            return _SentMailMailboxMatch(entry=entry, mailbox_only_confident=True)
        if body_first_line != "" and body_first_line in preview_text:
            return _SentMailMailboxMatch(entry=entry, mailbox_only_confident=True)
        if body_text != "" and body_text in preview_text:
            return _SentMailMailboxMatch(entry=entry, mailbox_only_confident=True)
        if (
            ambiguous_match is None
            and context.params.recipient_kind == MailRecipientKind.PLAYER
            and normalized_target is not None
            and title_text == normalized_target
        ):
            ambiguous_match = _SentMailMailboxMatch(entry=entry, mailbox_only_confident=False)
    return ambiguous_match


def _thread_matches_sent_mail(context: TaskContext, observation: Observation) -> bool:
    """Returns whether the opened thread visibly contains the sent subject or body content."""

    visible_text = "\n".join(entry.title_text or "" for entry in observation.entries(ListEntryKind.MAIL_MESSAGE))
    normalized_visible_text = normalize_mail_text(visible_text)
    if normalized_visible_text == "":
        return False
    subject_text = normalize_mail_text(context.params.subject)
    body_text = normalize_mail_text(context.params.body)
    body_first_line = normalize_mail_text(context.params.body.splitlines()[0]) if context.params.body.splitlines() else body_text
    return any(
        candidate != "" and candidate in normalized_visible_text
        for candidate in (subject_text, body_first_line, body_text)
    )


def _open_mail_thread_action(entry: DetectedListEntry, *, reason: str) -> TapPointAction:
    """Builds the canonical thread-opening tap used by sent-mail verification."""

    target = entry.action_point if entry.action_point is not None else entry.bounds.center()
    return TapPointAction(
        x=target[0],
        y=target[1],
        reason=reason,
        observe_after=True,
        follow_up_request=ObservationRequest.mail_navigation_follow_up(
            ScreenType.PNC_MAIL_THREAD,
            ScreenType.PNC_MAILBOX_LIST,
        ),
    )
