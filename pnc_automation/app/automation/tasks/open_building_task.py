"""Task that opens one exact home-city building screen without mutating it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.app.automation.engine.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.automation.tasks.open_building_support import (
    find_visible_target_home_city_object,
    plan_focus_requested_home_city_object,
    requested_home_city_object_observation_matches,
)
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, WaitAction
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId, home_city_object_definition
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.policy_models import OpenBuildingPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType

_OPEN_BUILDING_FOCUS_PENDING_STATE_KEY = "open_building_focus_pending"
_OPEN_BUILDING_SETTLE_WAIT_MS = 1500
_OPEN_BUILDING_REPLAN_BUDGET_OVERHEAD = 4


class OpenBuildingTask(BaseAutomationTask):
    """Opens one requested home-city building and succeeds once its owned or build-menu screen is visible."""

    id = TaskId.OPEN_BUILDING
    castle_target_policy = CastleTargetPolicy.OPTIONAL

    def max_replans_per_step(self, context: TaskContext) -> int | None:
        """Grants enough bounded replan budget for the shared home-city search path plus settle overhead."""

        return context.flows.home_city_navigator.focus_step_budget() + _OPEN_BUILDING_REPLAN_BUDGET_OVERHEAD

    def parse_params(self, params: Mapping[str, Any]) -> OpenBuildingPolicy:
        """Builds the typed open-building policy."""

        return OpenBuildingPolicy.from_params(params)

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Rejects unsupported bootstrap and login states."""

        del context
        return observation.screen_type not in {
            ScreenType.ANDROID_HOME,
            ScreenType.PNC_LOGIN,
            ScreenType.PNC_ACCOUNT_SWITCH,
            ScreenType.PNC_CASTLE_SELECTION,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans one increment that either reaches home city, searches, or taps the requested building."""
        target = context.params.building
        if _open_building_success_matches(observation, target):
            _clear_focus_pending(context.runtime_state)
            return []
        if observation.screen_type == ScreenType.UNKNOWN:
            return [
                WaitAction(
                    milliseconds=_OPEN_BUILDING_SETTLE_WAIT_MS,
                    reason="wait_for_open_building_unknown_settle",
                    observe_after=True,
                )
            ]
        visible_target = find_visible_target_home_city_object(observation, target=target)
        if visible_target is not None:
            _clear_focus_pending(context.runtime_state)
            return context.flows.open_visible_home_city_object(
                observation,
                visible_target,
                reason="open_requested_building",
                runtime_state=context.runtime_state,
            )
        _set_focus_pending(context.runtime_state)
        return plan_focus_requested_home_city_object(
            flows=context.flows,
            observation=observation,
            target=target,
            runtime_state=context.runtime_state,
            reason="focus_requested_building",
        )

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies home-city navigation and completes once the requested building screen is open."""
        target = context.params.building
        if _open_building_success_matches(after, target):
            _clear_focus_pending(context.runtime_state)
            return TaskResult.success(f"Opened '{home_city_object_definition(target).display_name}'.")
        if before.screen_type == ScreenType.UNKNOWN:
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Building open is waiting for the transient screen to settle.")
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                return TaskResult.replan("Reached home city for continued building opening.")
            return TaskResult.failure("Building open could not recover from the transient screen state.", retryable=True)
        if before.screen_type != ScreenType.PNC_HOME_CITY:
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                return TaskResult.replan("Reached home city for requested building opening.")
            return TaskResult.failure("Building open could not reach home city.", retryable=True)
        if after.screen_type == ScreenType.UNKNOWN:
            return TaskResult.replan("Building open is still settling after the latest home-city interaction.")
        if after.screen_type == ScreenType.PNC_HOME_CITY and _has_focus_pending(context.runtime_state):
            _clear_focus_pending(context.runtime_state)
            return TaskResult.replan("Adjusted the home-city view while searching for the requested building.")
        return TaskResult.failure("Building open did not produce the requested building screen.", retryable=True)


def _set_focus_pending(runtime_state: dict[str, Any]) -> None:
    """Records that the last planned increment was a home-city search or guided building-open move."""

    runtime_state[_OPEN_BUILDING_FOCUS_PENDING_STATE_KEY] = True


def _clear_focus_pending(runtime_state: dict[str, Any]) -> None:
    """Clears any remembered building-open search increment state."""

    runtime_state.pop(_OPEN_BUILDING_FOCUS_PENDING_STATE_KEY, None)


def _has_focus_pending(runtime_state: dict[str, Any]) -> bool:
    """Returns whether the task is waiting for one planned building-open search step to settle."""

    return bool(runtime_state.get(_OPEN_BUILDING_FOCUS_PENDING_STATE_KEY))


def _open_building_success_matches(observation: Observation, target: HomeCityObjectId) -> bool:
    """Returns whether the current observation proves the requested building or build slot is open."""

    return requested_home_city_object_observation_matches(observation, target)
