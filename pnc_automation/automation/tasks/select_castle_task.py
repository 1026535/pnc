"""Task that selects the configured castle for the current account."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.pnc.action_requests import ActionRequest
from pnc_automation.pnc.observation import ListEntryKind, Observation
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

        return observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_CASTLE_SELECTION}

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Delegates castle navigation to the canonical screen flow."""

        return context.flows.ensure_correct_castle_selected(observation, context.account.selected_castle)

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the selected castle matches the configured target."""

        expected_castle = context.account.selected_castle.castle_name
        if after.current_castle_name == expected_castle:
            return TaskResult.success(f"Configured castle '{expected_castle}' is selected.")
        for entry in after.entries(ListEntryKind.CASTLE):
            if entry.title_text == expected_castle and entry.selected:
                return TaskResult.success(f"Configured castle '{expected_castle}' is selected.")
        return TaskResult.failure(f"Configured castle '{expected_castle}' is not selected yet.", retryable=True)
