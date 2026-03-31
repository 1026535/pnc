"""Task that selects one explicit runtime castle target for the current account."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.pnc.action_requests import ActionRequest, WaitAction
from pnc_automation.pnc.observation import CurrentCastleMatch, CurrentCastleMatchStatus, Observation
from pnc_automation.pnc.screen_type import ScreenType


class SelectCastleTask(BaseAutomationTask):
    """Ensures the explicit step-level castle target is selected for the active account."""

    id = TaskId.SELECT_CASTLE
    castle_target_policy = CastleTargetPolicy.REQUIRED

    def parse_params(self, params: Mapping[str, Any]) -> None:
        """Rejects unsupported parameters for castle selection."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Allows explicit castle switching from any in-game screen that can safely return to root."""

        del context
        return observation.screen_type not in {
            ScreenType.ANDROID_HOME,
            ScreenType.PNC_LOGIN,
            ScreenType.PNC_ACCOUNT_SWITCH,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Delegates explicit castle switching to the canonical Manage Char flow."""

        target_castle = context.require_target_castle()
        current_match = observation.current_castle_match(target_castle, roster=context.castle_roster)
        if observation.screen_type == ScreenType.PNC_LOADING:
            return [WaitAction(milliseconds=1500, reason="wait_for_castle_switch_loading", observe_after=True)]
        if observation.screen_type == ScreenType.UNKNOWN:
            return [WaitAction(milliseconds=1000, reason="wait_for_castle_switch_settle", observe_after=True)]
        if observation.screen_type in {ScreenType.PNC_VIP, ScreenType.PNC_IMPROVE_MIGHT}:
            return context.flows.return_to_safe_root_screen(observation)
        if not _is_castle_selection_root_screen(observation.screen_type):
            return context.flows.ensure_home_city(observation)
        if current_match.matches:
            if observation.screen_type in {ScreenType.PNC_MORE_MENU, ScreenType.PNC_CASTLE_SELECTION}:
                return context.flows.return_to_safe_root_screen(observation)
            return []
        if observation.screen_type == ScreenType.PNC_LORD_INFO:
            return context.flows.open_castle_selection(observation)
        return context.flows.ensure_correct_castle_selected(
            observation,
            target_castle,
            context.castle_roster,
        )

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the explicit target castle is revalidated from home city."""

        target_castle = context.require_target_castle()
        current_match = after.current_castle_match(target_castle, roster=context.castle_roster)
        if not _is_castle_selection_root_screen(before.screen_type):
            if after.screen_type == ScreenType.PNC_POPUP or after.blocking_popup:
                return TaskResult.replan("Castle switching reached a blocking popup and needs centralized recovery.")
            if _is_castle_selection_root_screen(after.screen_type) or after.screen_type in {
                ScreenType.PNC_LOADING,
                ScreenType.UNKNOWN,
            }:
                return TaskResult.replan("Castle navigation returned to a root-adjacent screen for explicit switching.")
            return TaskResult.failure("Castle navigation could not return to a root-adjacent switching screen.", retryable=True)
        if after.screen_type == ScreenType.PNC_HOME_CITY and current_match.matches:
            return TaskResult.success(f"Target castle '{target_castle.castle_name}' is selected.")
        if after.screen_type == ScreenType.PNC_LORD_INFO and current_match.matches:
            return TaskResult.success(f"Target castle '{target_castle.castle_name}' is selected.")
        if after.screen_type == ScreenType.PNC_MORE_MENU:
            if after.current_castle is not None and current_match.matches:
                return TaskResult.replan("Castle validation is back at the More menu and still needs to return to home city.")
            if current_match.ambiguous:
                return TaskResult.replan(_ambiguous_current_castle_message(screen_type=after.screen_type))
            return TaskResult.replan("Castle navigation is at the More menu and still needs the next validation or Manage Char action.")
        if after.screen_type == ScreenType.PNC_LORD_INFO:
            if current_match.ambiguous:
                return TaskResult.replan(_ambiguous_current_castle_message(screen_type=after.screen_type))
            return TaskResult.replan("Castle validation is reading the displayed Lord Info name.")
        if after.screen_type == ScreenType.PNC_CASTLE_SELECTION:
            matching_entry = after.find_castle_entry(target_castle)
            if matching_entry is not None and matching_entry.selected:
                return TaskResult.replan("Target castle is selected in Manage Char and now needs home-city validation.")
            return TaskResult.replan("Castle selection is open and still needs to reach the requested target castle.")
        if after.screen_type in {ScreenType.PNC_VIP, ScreenType.PNC_IMPROVE_MIGHT}:
            return TaskResult.replan("Castle navigation opened another More-menu screen and is returning to home city.")
        if after.screen_type == ScreenType.PNC_POPUP or after.blocking_popup:
            return TaskResult.replan("Castle switching reached a blocking popup and needs centralized recovery.")
        if after.screen_type == ScreenType.PNC_LOADING:
            return TaskResult.replan("Castle switch is still loading.")
        if after.screen_type == ScreenType.UNKNOWN and before.screen_type in {
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_LOADING,
            ScreenType.UNKNOWN,
        }:
            return TaskResult.replan("Castle switch transition is still settling.")
        if after.screen_type == ScreenType.PNC_HOME_CITY:
            if after.current_castle is None:
                return TaskResult.replan("Home city is visible but the active castle still needs exact Manage Char validation.")
            if current_match.ambiguous:
                return TaskResult.replan(_ambiguous_current_castle_message(screen_type=after.screen_type))
            if current_match.status == CurrentCastleMatchStatus.INSUFFICIENT_EVIDENCE:
                return TaskResult.replan(_insufficient_current_castle_message(match=current_match))
            return TaskResult.replan(
                f"Home city is visible but active castle '{after.current_castle.castle_name}' does not match target castle '{target_castle.castle_name}'."
            )
        return TaskResult.failure(
            f"Target castle '{target_castle.castle_name}' is not selected yet.",
        )


def _ambiguous_current_castle_message(*, screen_type: ScreenType) -> str:
    """Returns the shared replan message for ambiguous name-only current-castle evidence."""

    return (
        f"Current castle evidence on '{screen_type.value}' is name-only and ambiguous in the cached roster; "
        "Manage Char verification is still required."
    )


def _insufficient_current_castle_message(*, match: CurrentCastleMatch) -> str:
    """Returns the shared replan message for current-castle evidence that cannot yet prove the target."""

    if match.status == CurrentCastleMatchStatus.INSUFFICIENT_EVIDENCE:
        return "Home city is visible but the active castle still needs exact Manage Char verification."
    return "Home city is visible but the active castle still needs exact Manage Char verification."


def _is_castle_selection_root_screen(screen_type: ScreenType) -> bool:
    """Returns whether the screen already belongs to the explicit castle-switching root flow."""

    return screen_type in {
        ScreenType.PNC_HOME_CITY,
        ScreenType.PNC_MORE_MENU,
        ScreenType.PNC_LORD_INFO,
        ScreenType.PNC_VIP,
        ScreenType.PNC_IMPROVE_MIGHT,
        ScreenType.PNC_CASTLE_SELECTION,
    }
