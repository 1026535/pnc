"""Task that performs a deterministic full-scan refresh of the castle roster cache."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import TaskVerificationError
from pnc_automation.pnc.action_requests import ActionRequest, SwipeAction, WaitAction
from pnc_automation.pnc.observation import ListEntryKind, Observation, castle_identity_from_entry
from pnc_automation.pnc.screen_type import ScreenType


class _RefreshPhase(StrEnum):
    """Tracks the canonical high-level phase of one roster-refresh execution."""

    SEEK_TOP = "seek_top"
    SCAN_FORWARD = "scan_forward"
    RETURN_HOME = "return_home"


class RefreshCastleRosterTask(BaseAutomationTask):
    """Refreshes the full ordered castle roster and persists it as `full_scan`."""

    id = TaskId.REFRESH_CASTLE_ROSTER
    castle_target_policy = CastleTargetPolicy.DISALLOWED

    def parse_params(self, params: Mapping[str, Any]) -> None:
        """Rejects unsupported parameters for roster refresh."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Allows refresh only from home-adjacent or roster-owned screens."""

        del context
        return observation.screen_type in {
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_LORD_INFO,
            ScreenType.PNC_VIP,
            ScreenType.PNC_IMPROVE_MIGHT,
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.UNKNOWN,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans one deterministic roster-refresh increment."""

        phase = _resolve_phase(context)
        if observation.screen_type == ScreenType.UNKNOWN:
            return [WaitAction(milliseconds=1000, reason="wait_for_roster_refresh_settle", observe_after=True)]
        if phase == _RefreshPhase.RETURN_HOME:
            return context.flows.ensure_home_city(observation)
        if observation.screen_type in {ScreenType.PNC_VIP, ScreenType.PNC_IMPROVE_MIGHT}:
            return context.flows.return_to_safe_root_screen(observation)
        if observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            return context.flows.open_castle_selection(observation)
        if phase == _RefreshPhase.SEEK_TOP:
            return [
                SwipeAction(
                    direction="down",
                    distance_ratio=0.55,
                    duration_ms=350,
                    reason="scroll_castle_roster_to_top",
                    observe_after=True,
                )
            ]
        if phase == _RefreshPhase.SCAN_FORWARD:
            return [
                SwipeAction(
                    direction="up",
                    distance_ratio=0.55,
                    duration_ms=350,
                    reason="scan_castle_roster_forward",
                    observe_after=True,
                )
            ]
        raise TaskVerificationError(
            f"Unsupported roster refresh phase '{phase}'.",
            account_id=context.account.id,
            task_id=self.id,
            phase=phase,
        )

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies navigation, top seeking, ordered scanning, and return to home city."""

        if after.blocking_popup or after.screen_type == ScreenType.PNC_POPUP:
            return TaskResult.replan("Roster refresh reached a blocking popup and needs centralized recovery.")
        if after.screen_type == ScreenType.UNKNOWN:
            return TaskResult.replan("Roster refresh is still settling after the previous increment.")

        phase = _resolve_phase(context)
        if phase == _RefreshPhase.RETURN_HOME:
            return _verify_return_home(after)
        if before.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            return _verify_navigation_to_roster(after)
        if phase == _RefreshPhase.SEEK_TOP:
            return _verify_seek_top(context, before=before, after=after)
        if phase == _RefreshPhase.SCAN_FORWARD:
            return _verify_scan_forward(context, before=before, after=after)
        raise TaskVerificationError(
            f"Unsupported roster refresh phase '{phase}'.",
            account_id=context.account.id,
            task_id=self.id,
            phase=phase,
        )


def _resolve_phase(context: TaskContext) -> _RefreshPhase:
    """Returns the current refresh phase, initializing the step-local state when needed."""

    raw_phase = context.runtime_state.setdefault("refresh_phase", _RefreshPhase.SEEK_TOP.value)
    try:
        return _RefreshPhase(raw_phase)
    except ValueError as error:
        raise TaskVerificationError(
            f"Unsupported roster refresh phase '{raw_phase}'.",
            account_id=context.account.id,
            task_id=context.step.task,
            phase=raw_phase,
        ) from error


def _verify_navigation_to_roster(after: Observation) -> TaskResult:
    """Verifies the navigation path into the Manage Char roster before scanning begins."""

    if after.screen_type == ScreenType.PNC_CASTLE_SELECTION:
        return TaskResult.replan("Roster refresh opened Manage Char and can now begin scanning.")
    if after.screen_type in {
        ScreenType.PNC_HOME_CITY,
        ScreenType.PNC_MORE_MENU,
        ScreenType.PNC_LORD_INFO,
        ScreenType.PNC_VIP,
        ScreenType.PNC_IMPROVE_MIGHT,
    }:
        return TaskResult.replan("Roster refresh is still navigating toward Manage Char.")
    return TaskResult.failure("Roster refresh could not reach the Manage Char roster.", retryable=True)


def _verify_seek_top(context: TaskContext, *, before: Observation, after: Observation) -> TaskResult:
    """Verifies one upward seek toward the first roster page."""

    if after.screen_type != ScreenType.PNC_CASTLE_SELECTION:
        return TaskResult.failure("Roster refresh lost the Manage Char roster while seeking the first page.", retryable=True)
    before_signature = _castle_window_signature(before)
    after_signature = _castle_window_signature(after)
    if before_signature == after_signature:
        _record_seen_window(context, after_signature)
        context.runtime_state["refresh_phase"] = _RefreshPhase.SCAN_FORWARD.value
        return TaskResult.replan("Roster refresh reached the first roster page and can now scan forward.")
    return TaskResult.replan("Roster refresh moved closer to the first roster page.")


def _verify_scan_forward(context: TaskContext, *, before: Observation, after: Observation) -> TaskResult:
    """Verifies one forward scan step and finalizes the ordered roster when the last page is reached."""

    if after.screen_type != ScreenType.PNC_CASTLE_SELECTION:
        return TaskResult.failure("Roster refresh lost the Manage Char roster during the full scan.", retryable=True)
    before_signature = _castle_window_signature(before)
    after_signature = _castle_window_signature(after)
    if before_signature == after_signature:
        return _finalize_full_scan(context)
    if _window_already_seen(context, after_signature):
        return TaskResult.failure("Roster refresh repeated a previously scanned roster window.", retryable=False)
    _record_seen_window(context, after_signature)
    return TaskResult.replan("Roster refresh captured another ordered roster window.")


def _finalize_full_scan(context: TaskContext) -> TaskResult:
    """Persists the observed ordered roster as a full scan and starts the return-home phase."""

    store = context.require_castle_roster_store()
    roster = context.castle_roster
    if roster is None or not roster.castles:
        raise TaskVerificationError(
            "Roster refresh cannot finalize because no scanned roster state is available to persist.",
            account_id=context.account.id,
            pnc_account_id=context.account.pnc_account_id,
        )
    store.replace_full_scan(context.account.pnc_account_id, roster.castles)
    context.runtime_state["refresh_phase"] = _RefreshPhase.RETURN_HOME.value
    return TaskResult.replan("Roster refresh persisted full-scan ordering and is returning to home city.")


def _verify_return_home(after: Observation) -> TaskResult:
    """Verifies the final return path back to the home-city root screen."""

    if after.screen_type == ScreenType.PNC_HOME_CITY:
        return TaskResult.success("Castle roster refresh completed and returned to home city.")
    return TaskResult.replan("Castle roster refresh is returning to home city.")


def _castle_window_signature(observation: Observation) -> tuple[tuple[str, str], ...]:
    """Returns the stable visible roster window identity for one Manage Char observation."""

    visible_castles = observation.entries(ListEntryKind.CASTLE)
    if not visible_castles:
        raise TaskVerificationError(
            "Castle roster refresh requires at least one visible castle entry on Manage Char.",
            screen_type=observation.screen_type,
        )
    return tuple(
        (castle.kingdom, castle.castle_name)
        for castle in (castle_identity_from_entry(entry) for entry in visible_castles)
    )


def _record_seen_window(
    context: TaskContext,
    window_signature: tuple[tuple[str, str], ...],
) -> None:
    """Records one successfully scanned roster window in the step-local refresh state."""

    seen_windows = context.runtime_state.setdefault("seen_windows", set())
    if not isinstance(seen_windows, set):
        raise TaskVerificationError(
            "Castle roster refresh step state is corrupt: expected a set of seen windows.",
            account_id=context.account.id,
            task_id=context.step.task,
        )
    seen_windows.add(window_signature)


def _window_already_seen(
    context: TaskContext,
    window_signature: tuple[tuple[str, str], ...],
) -> bool:
    """Returns whether the current roster window has already been scanned earlier in the run."""

    seen_windows = context.runtime_state.get("seen_windows", set())
    if not isinstance(seen_windows, set):
        raise TaskVerificationError(
            "Castle roster refresh step state is corrupt: expected a set of seen windows.",
            account_id=context.account.id,
            task_id=context.step.task,
        )
    return window_signature in seen_windows
