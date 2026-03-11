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
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_LOADING,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Delegates castle navigation to the canonical screen flow."""

        if observation.screen_type == ScreenType.PNC_LOADING:
            return [WaitAction(milliseconds=1500, reason="wait_for_castle_switch_loading", observe_after=True)]
        return context.flows.ensure_correct_castle_selected(
            observation,
            context.account.selected_castle,
            context.castle_roster,
        )

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the selected castle matches the configured target."""

        expected_castle = context.account.selected_castle
        if after.matches_current_castle(expected_castle):
            return TaskResult.success(f"Configured castle '{expected_castle.castle_name}' is selected.")
        matching_entry = after.find_castle_entry(expected_castle)
        if matching_entry is not None and matching_entry.selected:
            return TaskResult.success(f"Configured castle '{expected_castle.castle_name}' is selected.")
        if after.screen_type == ScreenType.PNC_LOADING:
            return TaskResult.replan("Castle switch is still loading.")
        if before.screen_type in {ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_LOADING} and after.screen_type == ScreenType.UNKNOWN:
            return TaskResult.replan("Castle switch transition is still settling.")
        if after.screen_type == ScreenType.PNC_HOME_CITY and after.current_castle is None:
            return TaskResult.replan("Home city is visible but the active castle still needs explicit verification.")
        if before.screen_type == ScreenType.PNC_CASTLE_SELECTION and after.screen_type == ScreenType.PNC_HOME_CITY:
            return TaskResult.replan("Castle selection returned to home city before the active castle could be verified.")
        return TaskResult.failure(
            f"Configured castle '{expected_castle.castle_name}' is not selected yet.",
            retryable=True,
        )
