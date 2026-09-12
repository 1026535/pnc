"""Synthetic WorldMapPreflightTask fixture."""

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



class _WorldMapPreflightTask(BaseAutomationTask):
    """Synthetic task that proves runner-owned exact world-map preflight before task-body planning."""

    id = TaskId.ENSURE_GAME_RUNNING
    preflight = TaskPreflight.WORLD_MAP

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Requires the runner to hand the task a proven world-map surface."""

        del context
        return observation.screen_type == ScreenType.PNC_WORLD_MAP and observation.spatial_surface is not None

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Does not emit actions because this test only validates preflight ownership."""

        del context, observation
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds only when the runner already proved world map before entering the task body."""

        del context, after
        if before.screen_type == ScreenType.PNC_WORLD_MAP and before.spatial_surface is not None:
            return TaskResult.success("Runner proved world map before task-body execution.")
        return TaskResult.failure("Runner did not prove world map before task-body execution.")
