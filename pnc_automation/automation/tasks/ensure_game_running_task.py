"""Task that ensures Puzzles & Conquest is foregrounded."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.pnc.action_requests import ActionRequest
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_type import ScreenType


class EnsureGameRunningTask(BaseAutomationTask):
    """Ensures the target device is in a P&C-owned state."""

    id = TaskId.ENSURE_GAME_RUNNING

    def parse_params(self, params: Mapping[str, Any]) -> None:
        """Rejects unsupported parameters for this bootstrap task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Allows bootstrap from any screen because it owns app foregrounding."""

        return True

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Foregrounds P&C only when the observation is not already inside the game."""

        if observation.screen_type not in {ScreenType.ANDROID_HOME, ScreenType.UNKNOWN}:
            return []
        return context.flows.ensure_pnc_foreground(observation)

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the run is no longer on Android home or unknown state."""

        if after.screen_type not in {ScreenType.ANDROID_HOME, ScreenType.UNKNOWN}:
            return TaskResult.success("Puzzles & Conquest is foregrounded.")
        return TaskResult.failure("Puzzles & Conquest is not foregrounded yet.", retryable=True)
