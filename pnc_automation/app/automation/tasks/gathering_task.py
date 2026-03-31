"""Task that dispatches one gathering march."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.app.automation.engine.task import (
    BaseAutomationTask,
    CastleTargetPolicy,
    TaskId,
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


class GatheringTask(BaseAutomationTask):
    """Dispatches one march to a preferred resource node."""

    id = TaskId.GATHERING
    castle_target_policy = CastleTargetPolicy.OPTIONAL

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

        if observation.available_march_slots is not None and observation.available_march_slots <= 0:
            return []
        if observation.screen_type != ScreenType.PNC_WORLD_MAP:
            return context.flows.ensure_world_map_ready(observation)
        context.flows.ensure_world_map_ready(observation)
        candidates = _visible_resource_nodes(observation)
        target = choose_priority_candidate(
            candidates,
            context.params.preferred_resources,
            key_selector=_require_resource_type,
        )
        if target is None:
            return []
        return [
            *context.flows.open_visible_world_object(
                observation,
                target,
                reason="open_gather_node",
            ),
            TapAction(selector_id=UiElementId.PNC_GATHER_BUTTON, reason="open_gather_march", observe_after=True),
            TapAction(
                selector_id=UiElementId.PNC_MARCH_CONFIRM_BUTTON,
                reason="confirm_gather_march",
                observe_after=True,
            ),
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies either navigation to world map or a dispatched gathering march."""

        if before.available_march_slots is not None and before.available_march_slots <= 0:
            return TaskResult.skipped("No march slots are available for gathering.")
        if before.screen_type != ScreenType.PNC_WORLD_MAP:
            if after.screen_type == ScreenType.PNC_WORLD_MAP:
                return TaskResult.replan("Reached world map for gathering planning.")
            return TaskResult.failure("Gathering task could not reach the world map.", retryable=True)
        if not _visible_resource_nodes(before):
            return TaskResult.skipped("No gatherable resource nodes were visible.")
        if (
            before.available_march_slots is not None
            and after.available_march_slots is not None
            and after.available_march_slots < before.available_march_slots
        ):
            return TaskResult.success("Gathering march dispatched and march slots decreased.")
        if after.screen_type == ScreenType.PNC_WORLD_MAP and before.available_march_slots is None:
            return TaskResult.success("Gathering flow returned to the world map.")
        return TaskResult.failure("Gathering did not produce a verified state change.", retryable=True)


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
