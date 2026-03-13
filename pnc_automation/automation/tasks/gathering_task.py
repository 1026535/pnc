"""Task that dispatches one gathering march."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult, choose_priority_entry
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import TaskVerificationError
from pnc_automation.pnc.action_requests import ActionRequest, TapAction, TapListEntryAction
from pnc_automation.pnc.observation import ListEntryKind, Observation
from pnc_automation.pnc.policy_models import GatheringPolicy, ResourceType
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId


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
            return context.flows.open_world_map(observation)

        candidates = observation.entries(ListEntryKind.GATHER_NODE)
        target = choose_priority_entry(
            candidates,
            context.params.preferred_resources,
            key_selector=lambda entry: ResourceType(str(entry.require_metadata("resource_type"))),
        )
        if target is None:
            return []
        return [
            _tap_entry(target, kind=ListEntryKind.GATHER_NODE, reason="open_gather_node"),
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
        if not before.entries(ListEntryKind.GATHER_NODE):
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


def _tap_entry(entry: object, *, kind: ListEntryKind, reason: str) -> TapListEntryAction:
    """Builds a list-entry tap action using the most stable available key."""

    if entry.title_text is None:
        raise TaskVerificationError("Dynamic entry is missing a title and cannot be reselected safely.", entry_kind=kind)
    return TapListEntryAction(
        entry_kind=kind,
        title_text=entry.title_text,
        use_action_point=True,
        reason=reason,
        observe_after=True,
    )
