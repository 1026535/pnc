"""Synthetic HomeCityPreflightTask fixture."""

from __future__ import annotations

from pnc_automation.app.automation.engine.task import (
    BaseAutomationTask,
    TaskId,
    TaskPreflight,
    TaskResult,
)
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType



class _HomeCityPreflightTask(BaseAutomationTask):
    """Synthetic task that proves runner-owned home-city preflight before task-body planning."""

    id = TaskId.ENSURE_GAME_RUNNING
    preflight = TaskPreflight.HOME_CITY

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Requires the runner to hand the task a proven home-city observation."""

        del context
        return observation.screen_type == ScreenType.PNC_HOME_CITY

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Does not emit actions because this test only validates preflight ownership."""

        del context, observation
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds only when the runner already proved home city before entering the task body."""

        del context, after
        if before.screen_type == ScreenType.PNC_HOME_CITY:
            return TaskResult.success("Runner proved home city before task-body execution.")
        return TaskResult.failure("Runner did not prove home city before task-body execution.")
