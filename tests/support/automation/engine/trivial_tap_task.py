"""Synthetic TrivialTapTask fixture."""

from __future__ import annotations

from pnc_automation.app.automation.engine.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, TapAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId



class _TrivialTapTask(BaseAutomationTask):
    """Synthetic task used to prove the framework loop independently of game logic."""

    id = TaskId.ENSURE_GAME_RUNNING

    def parse_params(self, params: dict[str, object]) -> None:
        """Rejects unsupported parameters for the synthetic task."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Runs only when the synthetic target selector is visible."""

        del context
        return observation.has(UiElementId.PNC_HOME_BUILD_BUTTON)

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Requests one selector-backed tap followed by re-observation."""

        del context, observation
        return [
            TapAction(
                selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                reason="tap_synthetic_target",
                observe_after=True,
            )
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the follow-up observation reaches the synthetic destination screen."""

        del context, before
        if after.screen_type == ScreenType.PNC_BUILDING_DETAILS:
            return TaskResult.success("Synthetic tap reached the destination screen.")
        return TaskResult.failure("Synthetic tap did not reach the destination screen.", retryable=True)
