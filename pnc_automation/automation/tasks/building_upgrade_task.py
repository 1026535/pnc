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
from pnc_automation.pnc.action_requests import ActionRequest, KeyEventAction, TapAction
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

_BUILDING_UPGRADE_PENDING_TARGET_STATE_KEY = "building_upgrade_pending_target"
_BUILDING_UPGRADE_INELIGIBLE_TARGETS_STATE_KEY = "building_upgrade_ineligible_targets"


class BuildingUpgradeTask(BaseAutomationTask):
    """Upgrades one building only after the building-details screen proves the upgrade action is available."""

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

        if observation.screen_type not in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_BUILDING_DETAILS}:
            return context.flows.ensure_home_city(observation)
        if observation.screen_type == ScreenType.PNC_BUILDING_DETAILS:
            if observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                        reason="start_building_upgrade",
                        observe_after=True,
                    )
                ]
            return [
                KeyEventAction(
                    key_code="KEYCODE_BACK",
                    reason="leave_ineligible_building_details",
                    observe_after=True,
                )
            ]
        candidates = _visible_supported_buildings(observation, context.runtime_state)
        target = choose_priority_candidate(candidates, context.params.priority, key_selector=_require_building_priority)
        if target is not None:
            _set_pending_target(context.runtime_state, target)
            return context.flows.open_visible_home_city_object(
                observation,
                target,
                reason="inspect_building_upgrade_candidate",
                runtime_state=context.runtime_state,
            )
        if _all_visible_supported_buildings_are_ineligible(observation, context.runtime_state):
            return []
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

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies navigation, eligibility inspection, and the eventual upgrade start."""

        if before.screen_type not in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_BUILDING_DETAILS}:
            if after.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_BUILDING_DETAILS}:
                return TaskResult.replan("Reached home city for building upgrade planning.")
            return TaskResult.failure("Building upgrade could not reach home city.", retryable=True)
        if before.screen_type == ScreenType.PNC_HOME_CITY:
            if _all_visible_supported_buildings_are_ineligible(before, context.runtime_state):
                return TaskResult.skipped("No eligible building upgrades were verified from the visible home-city buildings.")
            if after.screen_type == ScreenType.PNC_BUILDING_DETAILS:
                if after.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
                    return TaskResult.replan("Opened building details and confirmed the upgrade button is available.")
                _mark_pending_target_ineligible(context.runtime_state)
                return TaskResult.replan("Opened building details but the selected building is not upgradeable.")
            if not _visible_supported_buildings(before, context.runtime_state):
                if after.screen_type == ScreenType.PNC_HOME_CITY:
                    return TaskResult.replan("Adjusted the home-city view while searching for a supported building.")
                return TaskResult.failure("Building upgrade could not continue the home-city search.", retryable=True)
            return TaskResult.failure("Building upgrade did not produce a verified state change.", retryable=True)
        if before.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
            _clear_pending_target(context.runtime_state)
            if after.screen_type == ScreenType.PNC_BUILDING_DETAILS and not after.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
                return TaskResult.success("Building upgrade started from the building details screen.")
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                return TaskResult.success("Building upgrade started and the flow returned to home city.")
            return TaskResult.failure("Building upgrade did not consume the verified upgrade action.", retryable=True)
        if after.screen_type == ScreenType.PNC_HOME_CITY:
            return TaskResult.replan("Returned to home city after verifying the selected building is not upgradeable.")
        return TaskResult.failure("Building upgrade did not produce a verified state change.", retryable=True)


def _visible_supported_buildings(
    observation: Observation,
    runtime_state: dict[str, Any],
) -> tuple[DetectedSpatialObject, ...]:
    """Returns visible supported home-city buildings that have not already been proven ineligible."""

    return tuple(
        object_
        for object_ in observation.spatial_objects(SpatialObjectKind.HOME_BUILDING)
        if _building_priority_from_object(object_) is not None
        and _building_target_signature(object_) not in _ineligible_target_signatures(runtime_state)
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


def _building_target_signature(object_: DetectedSpatialObject) -> tuple[object, ...]:
    """Builds one duplicate-safe signature for a visible home-city building candidate."""

    return (
        _building_priority_from_object(object_),
        object_.name_text,
        object_.action_point if object_.action_point is not None else object_.bounds.center(),
    )


def _set_pending_target(runtime_state: dict[str, Any], object_: DetectedSpatialObject) -> None:
    """Stores the currently inspected building target so failed eligibility checks can be remembered."""

    runtime_state[_BUILDING_UPGRADE_PENDING_TARGET_STATE_KEY] = _building_target_signature(object_)


def _clear_pending_target(runtime_state: dict[str, Any]) -> None:
    """Clears the currently inspected building target after the task changes state."""

    runtime_state.pop(_BUILDING_UPGRADE_PENDING_TARGET_STATE_KEY, None)


def _mark_pending_target_ineligible(runtime_state: dict[str, Any]) -> None:
    """Records the currently inspected building target as not upgradeable and clears the pending slot."""

    pending = runtime_state.pop(_BUILDING_UPGRADE_PENDING_TARGET_STATE_KEY, None)
    if pending is None:
        return
    signatures = _ineligible_target_signatures(runtime_state)
    signatures.add(pending)
    runtime_state[_BUILDING_UPGRADE_INELIGIBLE_TARGETS_STATE_KEY] = signatures


def _ineligible_target_signatures(runtime_state: dict[str, Any]) -> set[tuple[object, ...]]:
    """Returns the mutable set of visible building targets already proven ineligible for this step."""

    value = runtime_state.get(_BUILDING_UPGRADE_INELIGIBLE_TARGETS_STATE_KEY)
    if isinstance(value, set):
        return value
    signatures: set[tuple[object, ...]] = set()
    runtime_state[_BUILDING_UPGRADE_INELIGIBLE_TARGETS_STATE_KEY] = signatures
    return signatures


def _all_visible_supported_buildings_are_ineligible(observation: Observation, runtime_state: dict[str, Any]) -> bool:
    """Returns whether every currently visible supported building has already been inspected and rejected."""

    visible_supported = tuple(
        object_
        for object_ in observation.spatial_objects(SpatialObjectKind.HOME_BUILDING)
        if _building_priority_from_object(object_) is not None
    )
    return bool(visible_supported) and not _visible_supported_buildings(observation, runtime_state)
