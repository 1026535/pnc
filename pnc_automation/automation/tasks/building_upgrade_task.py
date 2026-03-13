"""Task that upgrades the highest-priority eligible building."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId, TaskResult, choose_priority_entry
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import TaskVerificationError
from pnc_automation.pnc.action_requests import ActionRequest, TapAction, TapListEntryAction
from pnc_automation.pnc.observation import ListEntryKind, Observation
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
        candidates = observation.entries(ListEntryKind.BUILDING)
        target = choose_priority_entry(
            candidates,
            context.params.priority,
            key_selector=lambda entry: BuildingPriority(str(entry.require_metadata("category"))),
        )
        if target is None:
            return []
        return [
            _tap_entry(target, kind=ListEntryKind.BUILDING, reason="open_building_candidate"),
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
        if not before.entries(ListEntryKind.BUILDING):
            return TaskResult.skipped("No eligible building upgrades were visible.")
        if after.screen_type == ScreenType.PNC_BUILDING_DETAILS and not after.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
            return TaskResult.success("Building upgrade started from the building details screen.")
        if after.screen_type == ScreenType.PNC_HOME_CITY and len(after.entries(ListEntryKind.BUILDING)) < len(before.entries(ListEntryKind.BUILDING)):
            return TaskResult.success("Building upgrade consumed one visible upgrade candidate.")
        return TaskResult.failure("Building upgrade did not produce a verified state change.", retryable=True)


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
