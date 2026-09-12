"""Synthetic OptionalCastleTask fixture."""

from __future__ import annotations

from pnc_automation.app.automation.engine.task import (
    BaseAutomationTask,
    CastleTargetPolicy,
    TaskId,
    TaskResult,
)
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import Observation



class _OptionalCastleTask(BaseAutomationTask):
    """Minimal optional-target task used to isolate runner pre-step castle alignment."""

    id = TaskId.BUILDING_UPGRADE
    castle_target_policy = CastleTargetPolicy.OPTIONAL

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic optional task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Accepts the settled observation passed through from the runner."""

        del context, observation
        return True

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Runs without additional actions so only the runner pre-step is exercised."""

        del context, observation
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds immediately once the runner hands control to the actual optional task."""

        del context, before, after
        return TaskResult.success("Optional task executed.")
