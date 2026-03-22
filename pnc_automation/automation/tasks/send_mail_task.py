"""Canonical task that sends mail through the shared mail workflow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.action_requests import ActionRequest, InputTextAction, SwipeAction, WaitAction
from pnc_automation.pnc.mail import (
    MailRecipientKind,
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
            profile_route_search = _plan_profile_route_search(context, observation)
            if profile_route_search:
                return profile_route_search
            compose_target_repair = _plan_compose_target_repair(context, observation)
            if compose_target_repair:
                return compose_target_repair
            return context.flows.open_mail_compose(observation, context.params)
        if phase == "send":
            if observation.screen_type != ScreenType.PNC_MAIL_COMPOSE_POPUP:
                return context.flows.open_mail_compose(observation, context.params)
            return context.flows.send_mail(observation, context.params)
        if phase == "verify_mail":
            return _plan_send_verification(context, observation)
        raise SelectorResolutionError("Unsupported send_mail phase.", phase=phase)

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies the current send-mail phase and advances the shared task state."""

        phase = _resolve_send_phase(context)
        if before.screen_type == ScreenType.PNC_PLAYER_PROFILE and before.profile_player_name is not None:
            context.runtime_state.setdefault("expected_profile_target", before.profile_player_name.strip())
        alliance_compose_block = _verify_alliance_compose_entry(context, before=before, after=after)
        if alliance_compose_block is not None:
            return alliance_compose_block
        if after.blocking_popup or after.screen_type == ScreenType.PNC_POPUP:
            return TaskResult.replan("Mail workflow reached a blocking popup and needs centralized recovery.")
        if after.screen_type in {ScreenType.PNC_LOADING, ScreenType.UNKNOWN}:
            return TaskResult.replan("Mail workflow is still settling after the previous increment.")
        if phase == "compose":
            if _hit_invalid_alliance_route_source(context, before=before, after=after):
                return TaskResult.failure(
                    "Alliance profile-route acquisition opened Mail instead of Alliance from the home-city source screen.",
                )
            if (
                context.params.player_name is not None
                and before.screen_type == ScreenType.PNC_MAIL_HUB
                and after.screen_type == ScreenType.PNC_MAIL_HUB
            ):
                return TaskResult.failure(
                    "Player Mail did not open from the Mail hub; this client leaves empty direct-mail mailboxes inert. Use a profile_route.",
                )
            if after.screen_type != ScreenType.PNC_MAIL_COMPOSE_POPUP:
                return TaskResult.replan("Mail workflow is still navigating toward the compose popup.")
            if _compose_target_matches(context, after):
                context.runtime_state["send_mail_phase"] = "send"
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
            context.runtime_state["send_mail_phase"] = "verify_mail"
            return TaskResult.replan("Mail compose closed; reopening the mailbox to verify the sent mail.")
        if phase == "verify_mail":
            return _verify_send_verification(context, before=before, after=after)
        raise SelectorResolutionError("Unsupported send_mail phase.", phase=phase)


def _resolve_send_phase(context: TaskContext) -> str:
    """Returns the current send-mail phase, initializing the task-local phase when needed."""

    raw_phase = context.runtime_state.setdefault("send_mail_phase", "compose")
    if raw_phase in {"compose", "send", "verify_mail"}:
        return raw_phase
    raise SelectorResolutionError("Unsupported send_mail runtime phase.", phase=raw_phase)


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


def _plan_profile_route_search(context: TaskContext, observation: Observation) -> list[ActionRequest]:
    """Returns bounded list-search swipes for list-backed profile routes when the target is not visible yet."""

    params = context.params
    route = params.profile_route
    if params.recipient_kind != MailRecipientKind.PLAYER or route is None or route.player_name is None:
        _clear_profile_route_search_state(context)
        return []
    entry_kind = _searchable_route_entry_kind(route.kind)
    if entry_kind is None:
        _clear_profile_route_search_state(context)
        return []
    expected_screen = _searchable_route_screen(route.kind)
    if observation.screen_type != expected_screen:
        if observation.screen_type != ScreenType.PNC_PLAYER_PROFILE:
            _clear_profile_route_search_state(context)
        return []
    if _has_named_entry(observation, kind=entry_kind, title_text=route.player_name):
        _clear_profile_route_search_state(context)
        return []
    search_state = _require_profile_route_search_state(context, route_kind=route.kind, player_name=route.player_name)
    phase = search_state["phase"]
    batches_completed = search_state["batches_completed"]
    if phase == "reset_to_top" and batches_completed >= 5:
        search_state["phase"] = "scan_forward"
        search_state["batches_completed"] = 0
        phase = "scan_forward"
        batches_completed = 0
    if phase == "scan_forward" and batches_completed >= 8:
        raise SelectorResolutionError(
            "The requested target row could not be found after searching the selected profile-route list.",
            route_kind=route.kind.value,
            player_name=route.player_name,
            screen_type=observation.screen_type,
        )
    search_state["batches_completed"] = batches_completed + 1
    return _plan_profile_route_search_swipes(observation, route_kind=route.kind, phase=phase)


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


def _plan_send_verification(context: TaskContext, observation: Observation) -> list[ActionRequest]:
    """Returns the next mailbox-opening increment for sent-mail verification."""

    mailbox = mailbox_for_recipient_kind(context.params.recipient_kind)
    if observation.screen_type == ScreenType.PNC_MAILBOX_LIST and observation.mailbox_type == mailbox:
        return []
    return context.flows.open_mailbox(observation, mailbox)


def _verify_send_verification(context: TaskContext, *, before: Observation, after: Observation) -> TaskResult:
    """Verifies mailbox reopening and, when available, thread-level sent-mail confirmation."""

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
        if matching_entry is not None:
            return TaskResult.success("Sent mail was located in the reopened mailbox.")
        if after.mailbox_empty:
            return TaskResult.failure("Sent-mail verification reopened an empty mailbox after sending.", retryable=True)
        if before.screen_type == ScreenType.PNC_MAILBOX_LIST and before.mailbox_type == mailbox:
            return TaskResult.failure(
                "Sent mail could not be located in the requested mailbox.",
                retryable=True,
            )
        return TaskResult.replan("Sent-mail verification reached the requested mailbox and is inspecting visible rows.")
    return TaskResult.replan("Sent-mail verification is still returning to the requested mailbox.")


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
    if params.profile_route is not None and params.profile_route.player_name is not None:
        return params.profile_route.player_name
    expected_profile_target = context.runtime_state.get("expected_profile_target")
    if isinstance(expected_profile_target, str) and expected_profile_target.strip() != "":
        return expected_profile_target.strip()
    return None


def _find_matching_sent_thread(context: TaskContext, observation: Observation) -> DetectedListEntry | None:
    """Returns the visible mailbox row that best matches the sent mail request."""

    expected_target = _expected_target_name(context)
    subject_text = normalize_mail_text(context.params.subject)
    body_text = normalize_mail_text(context.params.body)
    body_first_line = normalize_mail_text(context.params.body.splitlines()[0]) if context.params.body.splitlines() else body_text
    for entry in observation.entries(ListEntryKind.MAIL_THREAD):
        title_text = normalize_mail_text(entry.title_text or "")
        preview_text = normalize_mail_text(entry.subtitle_text or "")
        if context.params.recipient_kind == MailRecipientKind.PLAYER and expected_target is not None and title_text == normalize_mail_text(expected_target):
            return entry
        if subject_text != "" and (subject_text in title_text or subject_text in preview_text):
            return entry
        if body_first_line != "" and body_first_line in preview_text:
            return entry
        if body_text != "" and body_text in preview_text:
            return entry
    return None


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


def _searchable_route_entry_kind(route_kind: PlayerProfileRouteKind) -> ListEntryKind | None:
    """Returns the list-entry kind used by routes whose targets can be located through bounded scrolling."""

    if route_kind == PlayerProfileRouteKind.ALLIANCE_MEMBER:
        return ListEntryKind.ALLIANCE_MEMBER
    if route_kind == PlayerProfileRouteKind.MIGHT_RANK:
        return ListEntryKind.RANKED_PLAYER
    return None


def _searchable_route_screen(route_kind: PlayerProfileRouteKind) -> ScreenType:
    """Returns the route screen searched for one list-backed profile route."""

    if route_kind == PlayerProfileRouteKind.ALLIANCE_MEMBER:
        return ScreenType.PNC_ALLIANCE_MEMBER_LIST
    if route_kind == PlayerProfileRouteKind.MIGHT_RANK:
        return ScreenType.PNC_MIGHT_RANK
    raise SelectorResolutionError("Unsupported searchable profile-route kind.", route_kind=route_kind.value)


def _has_named_entry(observation: Observation, *, kind: ListEntryKind, title_text: str) -> bool:
    """Returns whether the requested named entry is currently visible in the observed list."""

    return any(entry.title_text == title_text for entry in observation.entries(kind))


def _require_profile_route_search_state(
    context: TaskContext,
    *,
    route_kind: PlayerProfileRouteKind,
    player_name: str,
) -> dict[str, object]:
    """Returns the active route-search state, resetting it when the route target changed."""

    state = context.runtime_state.get("profile_route_search")
    if (
        isinstance(state, dict)
        and state.get("route_kind") == route_kind.value
        and state.get("player_name") == player_name
        and state.get("phase") in {"reset_to_top", "scan_forward"}
        and isinstance(state.get("batches_completed"), int)
    ):
        return state
    new_state: dict[str, object] = {
        "route_kind": route_kind.value,
        "player_name": player_name,
        "phase": "reset_to_top",
        "batches_completed": 0,
    }
    context.runtime_state["profile_route_search"] = new_state
    return new_state


def _clear_profile_route_search_state(context: TaskContext) -> None:
    """Clears any in-progress profile-route list-search state when it no longer applies."""

    context.runtime_state.pop("profile_route_search", None)


def _plan_profile_route_search_swipes(
    observation: Observation,
    *,
    route_kind: PlayerProfileRouteKind,
    phase: str,
) -> list[ActionRequest]:
    """Builds the calibrated swipe batch used to recover or scan one list-backed profile route."""

    reason = f"search_{route_kind.value}_{phase}"
    if phase == "reset_to_top":
        return [
            _make_profile_route_search_swipe(
                observation,
                reason=reason,
                direction="down",
                start_y_ratio=0.40625,
                end_y_ratio=0.78125,
            )
            for _ in range(2)
        ]
    if phase == "scan_forward":
        return [
            _make_profile_route_search_swipe(
                observation,
                reason=reason,
                direction="up",
                start_y_ratio=0.78125,
                end_y_ratio=0.28125,
            )
        ]
    raise SelectorResolutionError("Unsupported profile-route search phase.", phase=phase, screen_type=observation.screen_type)


def _make_profile_route_search_swipe(
    observation: Observation,
    *,
    reason: str,
    direction: str,
    start_y_ratio: float,
    end_y_ratio: float,
) -> SwipeAction:
    """Returns one list-local swipe action tuned for the alliance member and rank route screens."""

    return SwipeAction(
        direction=direction,
        distance_ratio=0.72,
        reason=reason,
        observe_after=True,
        follow_up_request=ObservationRequest.source_screen_retry(observation.screen_type),
        start_x_ratio=0.5,
        start_y_ratio=start_y_ratio,
        end_x_ratio=0.5,
        end_y_ratio=end_y_ratio,
        duration_ms=500,
    )
