"""Task that ensures Puzzles & Conquest is foregrounded."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.pnc.action_requests import ActionRequest, WaitAction
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_type import ScreenType

_MAX_LAUNCH_WAIT_ATTEMPTS = 12


class EnsureGameRunningTask(BaseAutomationTask):
    """Ensures the target device is in a P&C-owned state."""

    id = TaskId.ENSURE_GAME_RUNNING
    castle_target_policy = CastleTargetPolicy.DISALLOWED

    def parse_params(self, params: Mapping[str, Any]) -> None:
        """Rejects unsupported parameters for this bootstrap task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Allows bootstrap from any screen because it owns app foregrounding."""

        return True

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Foregrounds P&C only when the observation is not already inside the game."""

        if observation.screen_type == ScreenType.UNKNOWN and _launch_in_progress(context):
            return [WaitAction(milliseconds=1500, reason="wait_for_pnc_launch", observe_after=True)]
        if observation.screen_type not in {ScreenType.ANDROID_HOME, ScreenType.UNKNOWN}:
            return []
        return context.flows.ensure_pnc_foreground(observation)

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the run is no longer on Android home or unknown state."""

        if after.screen_type not in {ScreenType.ANDROID_HOME, ScreenType.UNKNOWN}:
            _clear_launch_state(context)
            return TaskResult.success("Puzzles & Conquest is foregrounded.")
        if after.screen_type == ScreenType.UNKNOWN:
            if not _launch_in_progress(context):
                _mark_launch_started(context)
                return TaskResult.replan("Puzzles & Conquest launch is in progress.")
            wait_attempts = _increment_launch_wait_attempts(context)
            if wait_attempts <= _MAX_LAUNCH_WAIT_ATTEMPTS:
                return TaskResult.replan("Puzzles & Conquest launch is still in progress.")
            _clear_launch_state(context)
            return TaskResult.failure(
                "Puzzles & Conquest did not leave the launch or loading screen.",
                retryable=True,
            )
        _clear_launch_state(context)
        return TaskResult.failure("Puzzles & Conquest is not foregrounded yet.", retryable=True)


def _launch_in_progress(context: TaskContext) -> bool:
    """Returns whether the current task has already launched P&C and is waiting for a real in-game screen."""

    return bool(context.runtime_state.get("ensure_game_running_launch_started"))


def _mark_launch_started(context: TaskContext) -> None:
    """Marks that app launch has started and resets the bounded splash-wait counter."""

    context.runtime_state["ensure_game_running_launch_started"] = True
    context.runtime_state["ensure_game_running_launch_wait_attempts"] = 0


def _increment_launch_wait_attempts(context: TaskContext) -> int:
    """Advances and returns the bounded count of consecutive splash/loading observations."""

    wait_attempts = int(context.runtime_state.get("ensure_game_running_launch_wait_attempts", 0)) + 1
    context.runtime_state["ensure_game_running_launch_wait_attempts"] = wait_attempts
    return wait_attempts


def _clear_launch_state(context: TaskContext) -> None:
    """Clears the task-local launch-progress bookkeeping after success or a hard failure."""

    context.runtime_state.pop("ensure_game_running_launch_started", None)
    context.runtime_state.pop("ensure_game_running_launch_wait_attempts", None)
