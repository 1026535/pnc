"""Task that dispatches one gathering march."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.app.automation.engine.task import (
    BaseAutomationTask,
    CastleTargetPolicy,
    TaskId,
    TaskPreflight,
    TaskResult,
    choose_priority_candidate,
)
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, TapAction
from pnc_automation.app.pnc.domain.observation import (
    DetectedSpatialObject,
    Observation,
    SpatialObjectKind,
)
from pnc_automation.app.pnc.domain.policy_models import GatheringPolicy, ResourceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest


class GatheringTask(BaseAutomationTask):
    """Dispatches one march to a preferred resource node."""

    id = TaskId.GATHERING
    castle_target_policy = CastleTargetPolicy.OPTIONAL
    preflight = TaskPreflight.WORLD_MAP

    def parse_params(self, params: Mapping[str, Any]) -> GatheringPolicy:
        """Builds the typed gathering policy."""

        return GatheringPolicy.from_params(params)

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
        """Plans one gathering increment from the current screen."""

        if observation.screen_type == ScreenType.PNC_WORLD_MAP and (
            observation.available_march_slots is not None and observation.available_march_slots <= 0
        ):
            return []
        if observation.screen_type == ScreenType.PNC_GATHER_NODE:
            return [
                TapAction(
                    selector_id=UiElementId.PNC_GATHER_BUTTON,
                    reason="open_gather_march",
                    observe_after=True,
                    follow_up_request=ObservationRequest.march_confirm_follow_up(),
                )
            ]
        if observation.screen_type == ScreenType.PNC_MARCH_CONFIRM:
            return [
                TapAction(
                    selector_id=UiElementId.PNC_MARCH_CONFIRM_BUTTON,
                    reason="confirm_gather_march",
                    observe_after=True,
                    follow_up_request=ObservationRequest.post_march_dispatch_follow_up(),
                )
            ]
        if observation.screen_type != ScreenType.PNC_WORLD_MAP:
            return context.flows.ensure_world_map(observation)
        candidates = _visible_resource_nodes(observation)
        target = choose_priority_candidate(
            candidates,
            context.params.preferred_resources,
            key_selector=_require_resource_type,
        )
        if target is None:
            return []
        return [
            *context.flows.world_map_navigator.tap_visible_object(
                observation,
                target,
                reason="open_gather_node",
                follow_up_request=ObservationRequest.gather_node_follow_up(),
            ),
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies the currently active gathering phase without inferring skipped phases."""

        if before.screen_type != ScreenType.PNC_WORLD_MAP:
            if before.screen_type == ScreenType.PNC_GATHER_NODE:
                if after.screen_type == ScreenType.PNC_MARCH_CONFIRM:
                    return TaskResult.replan("Opened gathering march confirmation.")
                return TaskResult.failure("Gathering node did not open march confirmation.", retryable=True)
            if before.screen_type == ScreenType.PNC_MARCH_CONFIRM:
                if (
                    before.available_march_slots is not None
                    and after.available_march_slots is not None
                    and after.available_march_slots < before.available_march_slots
                ):
                    return TaskResult.success("Gathering march dispatched and march slots decreased.")
                if after.screen_type == ScreenType.PNC_WORLD_MAP:
                    return TaskResult.success("Gathering march dispatched and returned to the world map.")
                return TaskResult.failure("Gathering march confirmation did not dispatch.", retryable=True)
            if after.screen_type == ScreenType.PNC_WORLD_MAP:
                return TaskResult.replan("Reached world map for gathering planning.")
            return TaskResult.failure("Gathering task could not reach the world map.", retryable=True)
        if before.available_march_slots is not None and before.available_march_slots <= 0:
            return TaskResult.skipped("No march slots are available for gathering.")
        if not _visible_resource_nodes(before):
            return TaskResult.skipped("No gatherable resource nodes were visible.")
        if after.screen_type == ScreenType.PNC_GATHER_NODE:
            return TaskResult.replan("Opened gathering resource node.")
        return TaskResult.failure("Gathering resource-node tap did not open the node detail.", retryable=True)


def _visible_resource_nodes(observation: Observation) -> tuple[DetectedSpatialObject, ...]:
    """Returns visible world-map resource nodes that expose one supported resource type."""

    return tuple(
        object_
        for object_ in observation.spatial_objects(SpatialObjectKind.RESOURCE_NODE)
        if _resource_type_from_object(object_) is not None
    )


def _resource_type_from_object(object_: DetectedSpatialObject) -> ResourceType | None:
    """Returns the typed resource kind for one visible resource node when supported."""

    resource_type = getattr(object_, "metadata", {}).get("resource_type")
    if not isinstance(resource_type, str):
        return None
    try:
        return ResourceType(resource_type)
    except ValueError:
        return None


def _require_resource_type(object_: DetectedSpatialObject) -> ResourceType:
    """Returns the typed resource kind for one visible resource node or fails fast."""

    resource_type = _resource_type_from_object(object_)
    if resource_type is not None:
        return resource_type
    raise ValueError("Unsupported resource-node type.")
