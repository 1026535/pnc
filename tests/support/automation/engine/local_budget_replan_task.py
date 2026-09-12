"""Synthetic LocalBudgetReplanTask fixture."""

from __future__ import annotations

from pnc_automation.app.automation.engine.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId



class _LocalBudgetReplanTask(BaseAutomationTask):
    """Synthetic task used to prove task-local replan budgets without changing the runner default."""

    id = TaskId.ENSURE_GAME_RUNNING

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Runs only when the shared synthetic selector is visible."""

        del context
        return observation.has(UiElementId.PNC_HOME_BUILD_BUTTON)

    def max_replans_per_step(self, context: TaskContext) -> int | None:
        """Allows exactly six replans for this one synthetic task."""

        del context
        return 6

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Does not emit actions because this test only exercises runner-side replan budgeting."""

        del context, observation
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Replans six times and then succeeds without requiring new observations."""

        del before, after
        attempts = context.runtime_state.get("replan_attempts", 0)
        if not isinstance(attempts, int):
            raise AssertionError("Expected integer replan_attempts test state.")
        context.runtime_state["replan_attempts"] = attempts + 1
        if attempts >= 6:
            return TaskResult.success("Synthetic local-budget task exhausted its bounded replans cleanly.")
        return TaskResult.replan("Synthetic local-budget task is still exercising its private replan budget.")
