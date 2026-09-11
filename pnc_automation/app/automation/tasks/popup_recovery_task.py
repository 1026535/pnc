"""Task that clears blocking popups."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.app.automation.engine.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import Observation


class PopupRecoveryTask(BaseAutomationTask):
    """Dismisses one blocking popup using the centralized popup flow."""

    id = TaskId.POPUP_RECOVERY
    castle_target_policy = CastleTargetPolicy.DISALLOWED

    def parse_params(self, params: Mapping[str, Any]) -> None:
        """Rejects unsupported parameters for popup recovery."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Allows recovery retries even when the popup has already disappeared."""

        del context, observation
        return True

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Returns no task-owned action; the observed executor recovers interruptions before planning."""

        del context, observation
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Retains the authored compatibility task while recovery remains executor-owned."""

        if not after.blocking_popup:
            return TaskResult.success("Blocking popup dismissed.")
        return TaskResult.failure("Popup recovery did not clear the blocking popup.", retryable=True)
