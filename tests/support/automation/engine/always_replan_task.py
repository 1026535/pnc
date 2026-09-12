"""Synthetic AlwaysReplanTask fixture."""

from __future__ import annotations

from pnc_automation.app.automation.engine.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId



class _AlwaysReplanTask(BaseAutomationTask):
    """Synthetic task used to prove replan-limit failures route through shared runner diagnostics."""

    id = TaskId.ENSURE_GAME_RUNNING

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Runs only when the shared synthetic selector is visible."""

        del context
        return observation.has(UiElementId.PNC_HOME_BUILD_BUTTON)

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Does not emit actions because this test exercises runner-side replan failure handling only."""

        del context, observation
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Always requests another replan so the runner eventually hits its configured limit."""

        del context, before, after
        return TaskResult.replan("Synthetic replan-only task is still waiting for progress.")
