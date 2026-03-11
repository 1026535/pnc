"""Task that selects the configured castle for the current account."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.pnc.action_requests import ActionRequest, WaitAction
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_type import ScreenType


class SelectCastleTask(BaseAutomationTask):
    """Ensures the configured castle is selected for the active account."""

    id = TaskId.SELECT_CASTLE

    def parse_params(self, params: Mapping[str, Any]) -> None:
        """Rejects unsupported parameters for castle selection."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Allows castle selection from home city or the castle roster."""

        return observation.screen_type in {
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_LORD_INFO,
            ScreenType.PNC_VIP,
            ScreenType.PNC_IMPROVE_MIGHT,
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_LOADING,
            ScreenType.UNKNOWN,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Delegates castle navigation to the canonical screen flow."""

        expected_castle = context.account.selected_castle
        if observation.screen_type == ScreenType.PNC_LOADING:
            return [WaitAction(milliseconds=1500, reason="wait_for_castle_switch_loading", observe_after=True)]
        if observation.screen_type == ScreenType.UNKNOWN:
            return [WaitAction(milliseconds=1000, reason="wait_for_castle_switch_settle", observe_after=True)]
        if observation.screen_type in {ScreenType.PNC_VIP, ScreenType.PNC_IMPROVE_MIGHT}:
            return context.flows.return_to_safe_root_screen(observation)
        if observation.matches_current_castle(expected_castle):
            if observation.screen_type in {ScreenType.PNC_MORE_MENU, ScreenType.PNC_CASTLE_SELECTION}:
                return context.flows.return_to_safe_root_screen(observation)
            return []
        if observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU} and observation.current_castle is None:
            return context.flows.open_lord_info(observation)
        if observation.screen_type == ScreenType.PNC_LORD_INFO:
            return context.flows.open_castle_selection(observation)
        return context.flows.ensure_correct_castle_selected(
            observation,
            expected_castle,
            context.castle_roster,
        )

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the selected castle is revalidated from home city."""

        expected_castle = context.account.selected_castle
        if after.screen_type == ScreenType.PNC_HOME_CITY and after.matches_current_castle(expected_castle):
            return TaskResult.success(f"Configured castle '{expected_castle.castle_name}' is selected.")
        if after.screen_type == ScreenType.PNC_LORD_INFO and after.matches_current_castle(expected_castle):
            return TaskResult.success(f"Configured castle '{expected_castle.castle_name}' is selected.")
        if after.screen_type == ScreenType.PNC_MORE_MENU:
            if after.current_castle is not None and after.matches_current_castle(expected_castle):
                return TaskResult.replan("Castle validation is back at the More menu and still needs to return to home city.")
            return TaskResult.replan("Castle navigation is at the More menu and still needs the next validation or Manage Char action.")
        if after.screen_type == ScreenType.PNC_LORD_INFO:
            return TaskResult.replan("Castle validation is reading the displayed Lord Info name.")
        if after.screen_type == ScreenType.PNC_CASTLE_SELECTION:
            matching_entry = after.find_castle_entry(expected_castle)
            if matching_entry is not None and matching_entry.selected:
                return TaskResult.replan("Configured castle is selected in Manage Char and now needs home-city validation.")
            return TaskResult.replan("Castle selection is open and still needs to reach the configured castle.")
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
                return TaskResult.replan("Home city is visible but the active castle still needs explicit Lord Info validation.")
            return TaskResult.replan(
                f"Home city is visible but active castle '{after.current_castle.castle_name}' does not match configured castle '{expected_castle.castle_name}'."
            )
        return TaskResult.failure(
            f"Configured castle '{expected_castle.castle_name}' is not selected yet.",
        )
