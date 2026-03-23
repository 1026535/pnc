"""Task that upgrades the highest-priority eligible building."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import (
    BaseAutomationTask,
    CastleTargetPolicy,
    TaskId,
    TaskResult,
    choose_priority_candidate,
)
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.pnc.action_requests import ActionRequest, TapAction
from pnc_automation.pnc.observation import (
    DetectedSpatialObject,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.pnc.policy_models import BuildingPriority, BuildingUpgradePolicy
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId


class BuildingUpgradeTask(BaseAutomationTask):
    """Upgrades one eligible building using the configured priority policy."""

    id = TaskId.BUILDING_UPGRADE
    castle_target_policy = CastleTargetPolicy.OPTIONAL

    def parse_params(self, params: Mapping[str, Any]) -> BuildingUpgradePolicy:
        """Builds the typed building-upgrade policy."""

        return BuildingUpgradePolicy.from_params(params)

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Rejects unsupported bootstrap and login states."""

        return observation.screen_type not in {
            ScreenType.UNKNOWN,
            ScreenType.ANDROID_HOME,
            ScreenType.PNC_LOGIN,
            ScreenType.PNC_ACCOUNT_SWITCH,
            ScreenType.PNC_CASTLE_SELECTION,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans one building-upgrade increment from the current screen."""

        if observation.screen_type != ScreenType.PNC_HOME_CITY:
            return context.flows.ensure_home_city(observation)
        candidates = _visible_building_candidates(observation)
        target = choose_priority_candidate(
            candidates,
            context.params.priority,
            key_selector=_require_building_priority,
        )
        if target is None:
            for priority in context.params.priority:
                return context.flows.focus_home_city_object(
                    observation,
                    SpatialObjectQuery(
                        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                        kind=SpatialObjectKind.HOME_BUILDING,
                        metadata_key="category",
                        metadata_value=priority.value,
                    ),
                    runtime_state=context.runtime_state,
                )
            return []
        return [
            *context.flows.open_home_city_object(
                observation,
                _query_for_building(target),
                reason="open_building_candidate",
                runtime_state=context.runtime_state,
            ),
            TapAction(
                selector_id=UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                reason="start_building_upgrade",
                observe_after=True,
            ),
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies either navigation to home city or a completed building upgrade."""

        if before.screen_type != ScreenType.PNC_HOME_CITY:
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                return TaskResult.replan("Reached home city for building upgrade planning.")
            return TaskResult.failure("Building upgrade could not reach home city.", retryable=True)
        if not _visible_building_candidates(before):
            return TaskResult.skipped("No eligible building upgrades were visible.")
        if after.screen_type == ScreenType.PNC_BUILDING_DETAILS and not after.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
            return TaskResult.success("Building upgrade started from the building details screen.")
        if after.screen_type == ScreenType.PNC_HOME_CITY and len(_visible_building_candidates(after)) < len(_visible_building_candidates(before)):
            return TaskResult.success("Building upgrade consumed one visible upgrade candidate.")
        return TaskResult.failure("Building upgrade did not produce a verified state change.", retryable=True)


def _visible_building_candidates(observation: Observation) -> tuple[DetectedSpatialObject, ...]:
    """Returns visible home-city buildings that map cleanly to the configured upgrade priorities."""

    return tuple(
        object_
        for object_ in observation.spatial_objects(SpatialObjectKind.HOME_BUILDING)
        if _building_priority_from_object(object_) is not None
    )


def _building_priority_from_object(object_: DetectedSpatialObject) -> BuildingPriority | None:
    """Returns the typed building priority category for one home-city spatial object when supported."""

    category = getattr(object_, "metadata", {}).get("category")
    if not isinstance(category, str):
        return None
    try:
        return BuildingPriority(category)
    except ValueError:
        return None


def _require_building_priority(object_: DetectedSpatialObject) -> BuildingPriority:
    """Returns the typed building priority for one visible home-city building or fails fast."""

    priority = _building_priority_from_object(object_)
    if priority is not None:
        return priority
    raise ValueError("Unsupported home-city building priority.")


def _query_for_building(object_: DetectedSpatialObject) -> SpatialObjectQuery:
    """Builds the canonical semantic query used to retarget one visible home-city building."""

    return SpatialObjectQuery(
        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
        kind=SpatialObjectKind.HOME_BUILDING,
        name_text=getattr(object_, "name_text", None),
        metadata_key="category",
        metadata_value=getattr(object_, "metadata", {}).get("category"),
    )
