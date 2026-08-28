"""Task that upgrades the highest-priority eligible building."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from pnc_automation.app.automation.engine.task import (
    BaseAutomationTask,
    CastleTargetPolicy,
    TaskId,
    TaskResult,
    choose_priority_candidate,
)
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.automation.tasks.open_building_support import (
    home_city_object_id_from_object,
    plan_focus_requested_home_city_object,
)
from pnc_automation.app.automation.tasks.building_workflow_support import (
    build_queue_active_timer_text as _build_queue_active_timer_text,
    building_requirement_is_visible as _building_requirement_is_visible,
    building_requirement_text as _building_requirement_text,
    can_open_build_queue as _can_open_build_queue,
    home_build_help_is_available as _home_build_help_is_available,
    home_city_active_build_is_visible as _home_city_active_build_is_visible,
    home_city_active_build_timer_text as _home_city_active_build_timer_text,
)
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, KeyEventAction, TapAction, WaitAction
from pnc_automation.app.pnc.domain.building_catalog import (
    BuildingAction,
    HomeCityObjectId,
    home_city_object_definition_for_label,
    home_city_object_id_for_screen,
    home_city_object_supports_action,
    is_repeatable_home_city_object,
    is_upgradeable_primary_screen,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedSpatialObject,
    ListEntryKind,
    Observation,
    SpatialObjectKind,
)
from pnc_automation.app.pnc.domain.policy_models import (
    BuildingPrerequisiteMode,
    BuildingPriority,
    BuildingUpgradePolicy,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

_BUILDING_UPGRADE_PENDING_TARGET_STATE_KEY = "building_upgrade_pending_target"
_BUILDING_UPGRADE_INELIGIBLE_TARGETS_STATE_KEY = "building_upgrade_ineligible_targets"
_BUILDING_UPGRADE_INELIGIBLE_OBJECT_IDS_STATE_KEY = "building_upgrade_ineligible_object_ids"
_BUILDING_UPGRADE_CONFIRMATION_PENDING_STATE_KEY = "building_upgrade_confirmation_pending"
_BUILDING_UPGRADE_POST_START_HELP_PENDING_STATE_KEY = "building_upgrade_post_start_help_pending"
_BUILDING_UPGRADE_FOCUS_PENDING_STATE_KEY = "building_upgrade_focus_pending"
_BUILDING_UPGRADE_LAST_UNMET_REQUIREMENT_STATE_KEY = "building_upgrade_last_unmet_requirement"
_BUILDING_UPGRADE_SUCCESS_VERIFICATION_STAGE_STATE_KEY = "building_upgrade_success_verification_stage"
_BUILDING_UPGRADE_QUEUED_PREREQUISITE_STATE_KEY = "building_upgrade_queued_prerequisite"
_BUILDING_UPGRADE_SPEEDUP_COMPLETION_PENDING_STATE_KEY = "building_upgrade_speedup_completion_pending"
_BUILDING_UPGRADE_SETTLE_WAIT_MS = 1500
_BUILDING_UPGRADE_REPLAN_BUDGET_TARGET_CAP = 3
_BUILDING_UPGRADE_REPLAN_BUDGET_OVERHEAD = 10
_SUCCESS_VERIFICATION_STAGE_RETURN_HOME = "return_home"
_SUCCESS_VERIFICATION_STAGE_OPEN_BUILD_QUEUE = "open_build_queue"
_SUCCESS_VERIFICATION_STAGE_RETURN_HOME_FOR_LEVEL = "return_home_for_level"
_BUILDING_REQUIREMENT_PATTERN = re.compile(
    r"^(?P<building>.+?)\s*:\s*Lv\.?\s*(?P<level>\d+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _PendingBuildingTarget:
    """Stores one currently inspected home-city building so ineligible results remain canonical."""

    signature: tuple[object, ...]
    priority: BuildingPriority | None
    starting_level: int | None


@dataclass(frozen=True, slots=True)
class _QueuedBuildingPrerequisite:
    """Stores one prerequisite selected on behalf of the originally requested building."""

    root_target: BuildingPriority
    prerequisite: BuildingPriority
    required_level: int


class BuildingUpgradeTask(BaseAutomationTask):
    """Upgrades one building only after the building-details screen proves the upgrade action is available."""

    id = TaskId.BUILDING_UPGRADE
    castle_target_policy = CastleTargetPolicy.OPTIONAL

    def max_replans_per_step(self, context: TaskContext) -> int | None:
        """Grants enough bounded replan budget for the canonical home-city sweep plus verification stages."""

        requested_target_count = max(1, min(len(context.params.priority), _BUILDING_UPGRADE_REPLAN_BUDGET_TARGET_CAP))
        return (context.flows.home_city_navigator.focus_step_budget() * requested_target_count) + _BUILDING_UPGRADE_REPLAN_BUDGET_OVERHEAD

    def parse_params(self, params: Mapping[str, Any]) -> BuildingUpgradePolicy:
        """Builds the typed building-upgrade policy."""

        return BuildingUpgradePolicy.from_params(params)

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
        """Plans one building-upgrade increment from the current screen."""

        remaining_priorities = _active_requested_priorities(context.params, context.runtime_state)
        verification_stage = _success_verification_stage(context.runtime_state)
        if observation.screen_type == ScreenType.UNKNOWN:
            return [
                WaitAction(
                    milliseconds=_BUILDING_UPGRADE_SETTLE_WAIT_MS,
                    reason="wait_for_building_upgrade_unknown_settle",
                    observe_after=True,
                )
            ]
        if _speedup_completion_pending(context.runtime_state):
            if observation.screen_type == ScreenType.PNC_HOME_CITY:
                return []
            return context.flows.ensure_home_city(observation)
        if observation.screen_type == ScreenType.PNC_BUILD_SPEEDUP:
            if not context.params.allow_speedups:
                return [
                    KeyEventAction(
                        key_code="KEYCODE_BACK",
                        reason="leave_build_speedup_without_permission",
                        observe_after=True,
                    )
                ]
            return [
                TapAction(
                    selector_id=UiElementId.PNC_BUILD_SPEEDUP_AUTO_BUTTON,
                    reason="use_inventory_auto_build_speedup",
                    observe_after=True,
                )
            ]
        if observation.screen_type == ScreenType.PNC_BUILD_SPEEDUP_CONFIRM:
            if not context.params.allow_speedups:
                return []
            return [
                TapAction(
                    selector_id=UiElementId.PNC_BUILD_SPEEDUP_CONFIRM_BUTTON,
                    reason="confirm_inventory_auto_build_speedup",
                    observe_after=True,
                )
            ]
        if observation.screen_type == ScreenType.PNC_HOME_CITY and _has_post_start_help_pending(context.runtime_state):
            if _home_build_help_is_available(observation):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                        reason="request_post_upgrade_help",
                        observe_after=True,
                    )
                ]
            return []
        if observation.screen_type == ScreenType.PNC_HOME_CITY and verification_stage == _SUCCESS_VERIFICATION_STAGE_OPEN_BUILD_QUEUE:
            if _can_open_build_queue(observation):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                        reason="open_build_queue_for_upgrade_verification",
                        observe_after=True,
                        follow_up_request=ObservationRequest.build_queue_follow_up(),
                    )
                ]
            return []
        if (
            observation.screen_type == ScreenType.PNC_HOME_CITY
            and _home_build_help_is_available(observation)
            and _pending_target(context.runtime_state) is None
            and verification_stage is None
            and not context.params.allow_speedups
        ):
            return [
                TapAction(
                    selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                    reason="request_active_build_help",
                    observe_after=True,
                )
            ]
        if (
            observation.screen_type == ScreenType.PNC_HOME_CITY
            and _home_city_active_build_is_visible(observation)
            and _pending_target(context.runtime_state) is None
            and verification_stage is None
            and not context.params.allow_speedups
        ):
            return []
        if not _is_upgrade_context_screen(observation.screen_type) and observation.screen_type != ScreenType.PNC_HOME_CITY:
            return context.flows.ensure_home_city(observation)
        if _is_upgrade_context_screen(observation.screen_type):
            if verification_stage == _SUCCESS_VERIFICATION_STAGE_RETURN_HOME:
                return [
                    KeyEventAction(
                        key_code="KEYCODE_BACK",
                        reason="return_home_for_upgrade_verification",
                        observe_after=True,
                    )
                ]
            _clear_focus_pending(context.runtime_state)
            if _building_requirement_is_visible(observation):
                if context.params.prerequisite_mode == BuildingPrerequisiteMode.QUEUE:
                    queue_error = _queue_visible_building_prerequisite(context, observation)
                    if queue_error is None and observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON):
                        return [
                            TapAction(
                                selector_id=UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
                                reason="open_queued_building_prerequisite",
                                observe_after=True,
                            )
                        ]
                return [
                    KeyEventAction(
                        key_code="KEYCODE_BACK",
                    reason="leave_building_requirement_panel",
                    observe_after=True,
                )
            ]
            if _has_upgrade_confirmation_pending(context.runtime_state) and observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                        reason="confirm_building_upgrade",
                    ),
                    WaitAction(
                        milliseconds=_BUILDING_UPGRADE_SETTLE_WAIT_MS,
                        reason="wait_for_building_upgrade_confirmation_settle",
                        observe_after=True,
                    ),
                ]
            if observation.has(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON):
                if context.params.allow_speedups:
                    _record_pending_starting_level_from_screen(context.runtime_state, observation)
                    return [
                        TapAction(
                            selector_id=UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,
                            reason="open_inventory_build_speedup",
                            observe_after=True,
                        )
                    ]
                return [
                    KeyEventAction(
                        key_code="KEYCODE_BACK",
                        reason="leave_active_upgrade_without_speedup_permission",
                        observe_after=True,
                    )
                ]
            if observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                        reason="start_building_upgrade",
                    ),
                    WaitAction(
                        milliseconds=_BUILDING_UPGRADE_SETTLE_WAIT_MS,
                        reason="wait_for_building_upgrade_settle",
                        observe_after=True,
                    ),
                ]
            return [
                KeyEventAction(
                    key_code="KEYCODE_BACK",
                    reason="leave_ineligible_building_details",
                    observe_after=True,
                )
            ]
        if not remaining_priorities:
            _clear_focus_pending(context.runtime_state)
            return []
        candidates = _visible_requested_buildings(
            observation,
            context.runtime_state,
            remaining_priorities,
        )
        target = choose_priority_candidate(candidates, remaining_priorities, key_selector=_require_building_priority)
        if target is not None:
            _clear_focus_pending(context.runtime_state)
            _set_pending_target(context.runtime_state, target)
            return context.flows.open_visible_home_city_object(
                observation,
                target,
                reason="inspect_building_upgrade_candidate",
                runtime_state=context.runtime_state,
            )
        for priority in remaining_priorities:
            _set_focus_pending(context.runtime_state)
            return plan_focus_requested_home_city_object(
                flows=context.flows,
                observation=observation,
                target=HomeCityObjectId(priority.value),
                runtime_state=context.runtime_state,
                reason="focus_building_upgrade_candidate",
            )
        return []

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies navigation, eligibility inspection, and the eventual upgrade start."""

        if _speedup_completion_pending(context.runtime_state):
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Inventory build speedup completion is still settling.")
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                if _home_city_pending_target_level_increased(after, context.runtime_state):
                    return _finish_started_upgrade_success(
                        context.runtime_state,
                        _home_city_level_increase_success_message(context.runtime_state, after),
                    )
                return TaskResult.failure(
                    "Inventory build speedup returned home without a verified building-level increase.",
                    retryable=True,
                )
            if _building_screen_pending_target_level_increased(after, context.runtime_state):
                return _finish_started_upgrade_success(
                    context.runtime_state,
                    _building_screen_level_increase_success_message(context.runtime_state, after),
                )
            return TaskResult.replan("Inventory build speedup was submitted and needs home-city level verification.")
        if before.screen_type == ScreenType.PNC_BUILD_SPEEDUP_CONFIRM:
            if not context.params.allow_speedups:
                return TaskResult.failure("Build speedup use was not authorized.")
            _set_speedup_completion_pending(context.runtime_state)
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                if _home_city_pending_target_level_increased(after, context.runtime_state):
                    return _finish_started_upgrade_success(
                        context.runtime_state,
                        _home_city_level_increase_success_message(context.runtime_state, after),
                    )
                return TaskResult.failure(
                    "Inventory build speedup returned home without a verified building-level increase.",
                    retryable=True,
                )
            if _building_screen_pending_target_level_increased(after, context.runtime_state):
                return _finish_started_upgrade_success(
                    context.runtime_state,
                    _building_screen_level_increase_success_message(context.runtime_state, after),
                )
            return TaskResult.replan("Inventory build speedup was confirmed and needs home-city level verification.")
        if before.screen_type == ScreenType.PNC_BUILD_SPEEDUP:
            if not context.params.allow_speedups:
                return TaskResult.failure("Build speedup use was not authorized.")
            if after.screen_type == ScreenType.PNC_BUILD_SPEEDUP_CONFIRM:
                return TaskResult.replan("Auto Speedup opened the explicit inventory-consumption confirmation.")
            _set_speedup_completion_pending(context.runtime_state)
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                if _home_city_pending_target_level_increased(after, context.runtime_state):
                    return _finish_started_upgrade_success(
                        context.runtime_state,
                        _home_city_level_increase_success_message(context.runtime_state, after),
                    )
                return TaskResult.failure(
                    "Inventory build speedup returned home without a verified building-level increase.",
                    retryable=True,
                )
            return TaskResult.replan("Inventory build speedup was submitted and needs home-city level verification.")

        if before.screen_type == ScreenType.PNC_HOME_CITY and _has_post_start_help_pending(context.runtime_state):
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Post-upgrade help request is still settling.")
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                _clear_post_start_help_pending(context.runtime_state)
                return _finish_started_upgrade_success(
                    context.runtime_state,
                    "Building upgrade started and available alliance help was requested.",
                )
            return TaskResult.failure("Post-upgrade help request left the home city unexpectedly.", retryable=True)
        if (
            before.screen_type == ScreenType.PNC_HOME_CITY
            and _home_build_help_is_available(before)
            and _pending_target(context.runtime_state) is None
            and _success_verification_stage(context.runtime_state) is None
        ):
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Active building help request is still settling.")
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                return _finish_already_active_upgrade_skip(
                    context.runtime_state,
                    "Another building upgrade is already active; requested available alliance help.",
                )
            return TaskResult.skipped("Another building upgrade is already active.")
        if (
            before.screen_type == ScreenType.PNC_HOME_CITY
            and _home_city_active_build_is_visible(before)
            and _pending_target(context.runtime_state) is None
            and _success_verification_stage(context.runtime_state) is None
        ):
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Active building timer observation is still settling.")
            return _finish_already_active_upgrade_skip(
                context.runtime_state,
                "Another building upgrade is already active.",
            )
        if before.screen_type == ScreenType.UNKNOWN:
            if _has_upgrade_confirmation_pending(context.runtime_state) and after.screen_type == ScreenType.PNC_HOME_CITY:
                return _verify_started_upgrade_at_home_city(context.runtime_state, after)
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Building upgrade is waiting for the transient screen to settle.")
            if after.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_BUILD_QUEUE} or _is_upgrade_context_screen(after.screen_type):
                return TaskResult.replan("Reached a stable game screen for continued building-upgrade planning.")
            return TaskResult.failure("Building upgrade could not recover from the transient screen state.", retryable=True)
        if before.screen_type == ScreenType.PNC_BUILD_QUEUE:
            if _success_verification_stage(context.runtime_state) == _SUCCESS_VERIFICATION_STAGE_RETURN_HOME_FOR_LEVEL:
                if after.screen_type == ScreenType.UNKNOWN:
                    return TaskResult.replan("Returning home for final building-level verification is still settling.")
                if after.screen_type == ScreenType.PNC_HOME_CITY:
                    if _home_city_pending_target_level_increased(after, context.runtime_state):
                        return _finish_started_upgrade_success(
                            context.runtime_state,
                            _home_city_level_increase_success_message(context.runtime_state, after),
                        )
                    return TaskResult.failure(
                        "Building upgrade could not be verified by an increased building level after build-queue fallback.",
                        retryable=True,
                    )
                if after.screen_type == ScreenType.PNC_BUILD_QUEUE:
                    return TaskResult.replan("Build queue is still open while returning home for level verification.")
                return TaskResult.failure(
                    "Building upgrade could not return home after build-queue verification.",
                    retryable=True,
                )
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                return TaskResult.replan("Returned to home city from the build queue.")
            return TaskResult.failure("Building upgrade could not recover from the build queue.", retryable=True)
        if before.screen_type != ScreenType.PNC_HOME_CITY and not _is_upgrade_context_screen(before.screen_type):
            if after.screen_type == ScreenType.PNC_HOME_CITY or _is_upgrade_context_screen(after.screen_type):
                return TaskResult.replan("Reached home city for building upgrade planning.")
            return TaskResult.failure("Building upgrade could not reach home city.", retryable=True)
        if before.screen_type == ScreenType.PNC_HOME_CITY:
            if _success_verification_stage(context.runtime_state) == _SUCCESS_VERIFICATION_STAGE_OPEN_BUILD_QUEUE:
                if after.screen_type == ScreenType.UNKNOWN:
                    return TaskResult.replan("Build queue verification is still settling.")
                if after.screen_type == ScreenType.PNC_BUILD_QUEUE:
                    return _verify_started_upgrade_from_build_queue(context.runtime_state, after)
                if after.screen_type == ScreenType.PNC_HOME_CITY:
                    if _home_city_pending_target_level_increased(after, context.runtime_state):
                        return _finish_started_upgrade_success(
                            context.runtime_state,
                            _home_city_level_increase_success_message(context.runtime_state, after),
                        )
                    _clear_success_verification_stage(context.runtime_state)
                    return TaskResult.failure(
                        "Building upgrade could not be verified from the build queue or a changed building level.",
                        retryable=True,
                    )
                return TaskResult.failure("Build queue verification left the home city unexpectedly.", retryable=True)
            remaining_priorities = _active_requested_priorities(context.params, context.runtime_state)
            if not remaining_priorities:
                return _requested_priority_exhausted_result(context.runtime_state)
            if _is_upgrade_context_screen(after.screen_type):
                if _building_requirement_is_visible(after):
                    _mark_pending_target_ineligible(context.runtime_state)
                    _mark_screen_priority_ineligible(context.runtime_state, after.screen_type)
                    _clear_focus_pending(context.runtime_state)
                    _clear_upgrade_confirmation_pending(context.runtime_state)
                    _set_last_unmet_requirement(context.runtime_state, after)
                    if context.params.prerequisite_mode == BuildingPrerequisiteMode.QUEUE:
                        queue_error = _queue_visible_building_prerequisite(context, after)
                        if queue_error is not None:
                            return queue_error
                    return TaskResult.replan(_unmet_requirement_replan_message(after))
                if after.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
                    _clear_focus_pending(context.runtime_state)
                    _clear_upgrade_confirmation_pending(context.runtime_state)
                    return TaskResult.replan("Opened building details and confirmed the upgrade button is available.")
                _mark_pending_target_ineligible(context.runtime_state)
                _mark_screen_priority_ineligible(context.runtime_state, after.screen_type)
                _clear_focus_pending(context.runtime_state)
                _clear_upgrade_confirmation_pending(context.runtime_state)
                return TaskResult.replan("Opened building details but the selected building is not upgradeable.")
            if _has_focus_pending(context.runtime_state):
                _clear_focus_pending(context.runtime_state)
                if after.screen_type == ScreenType.PNC_HOME_CITY:
                    return TaskResult.replan("Adjusted the home-city view while searching for the requested building.")
                return TaskResult.failure("Building upgrade could not continue the home-city search.", retryable=True)
            if not _visible_requested_buildings(before, context.runtime_state, remaining_priorities):
                if after.screen_type == ScreenType.PNC_HOME_CITY:
                    return TaskResult.replan("Adjusted the home-city view while searching for the requested building.")
                return TaskResult.failure("Building upgrade could not continue the home-city search.", retryable=True)
            return TaskResult.failure("Building upgrade did not produce a verified state change.", retryable=True)
        if _is_upgrade_context_screen(before.screen_type) and _building_requirement_is_visible(before):
            if context.params.prerequisite_mode == BuildingPrerequisiteMode.QUEUE:
                if after.screen_type == ScreenType.UNKNOWN:
                    return TaskResult.replan("Queued building prerequisite navigation is still settling.")
                if after.screen_type == ScreenType.PNC_HOME_CITY or _is_upgrade_context_screen(after.screen_type):
                    return TaskResult.replan("Reached the queued building prerequisite for upgrade planning.")
                return TaskResult.failure("Queued building prerequisite navigation left the supported workflow.", retryable=True)
            _mark_screen_priority_ineligible(context.runtime_state, before.screen_type)
            _set_last_unmet_requirement(context.runtime_state, before)
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Building requirement panel is still settling while returning to home city.")
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                remaining_priorities = _remaining_requested_priorities(context.params.priority, context.runtime_state)
                if not remaining_priorities:
                    return _requested_priority_exhausted_result(context.runtime_state)
                return TaskResult.replan("Returned to home city after recording the unmet building requirement.")
            if _is_upgrade_context_screen(after.screen_type) and _building_requirement_is_visible(after):
                return TaskResult.replan("Building requirement panel is still open and needs to return to home city.")
            return TaskResult.failure("Building upgrade could not leave the unmet requirement panel.", retryable=True)
        if _is_upgrade_context_screen(before.screen_type) and _building_speedup_is_visible(before):
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Build speedup screen is still opening.")
            if after.screen_type == ScreenType.PNC_BUILD_SPEEDUP:
                return TaskResult.replan("Opened the inventory-backed build speedup screen.")
            return TaskResult.failure("Building Speedup did not open the supported inventory screen.", retryable=True)
        if _is_upgrade_context_screen(before.screen_type) and _success_verification_stage(context.runtime_state) == _SUCCESS_VERIFICATION_STAGE_RETURN_HOME:
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Returning home for upgrade verification is still settling.")
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                return _verify_started_upgrade_at_home_city(context.runtime_state, after)
            if _is_upgrade_context_screen(after.screen_type):
                return TaskResult.replan("Building upgrade is still leaving the building screen for home-city verification.")
            return TaskResult.failure("Building upgrade could not return home for verification.", retryable=True)
        if _is_upgrade_context_screen(before.screen_type) and before.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
            if _is_upgrade_context_screen(after.screen_type) and _building_requirement_is_visible(after):
                _mark_pending_target_ineligible(context.runtime_state)
                _mark_screen_priority_ineligible(context.runtime_state, after.screen_type)
                _clear_upgrade_confirmation_pending(context.runtime_state)
                _set_last_unmet_requirement(context.runtime_state, after)
                if context.params.prerequisite_mode == BuildingPrerequisiteMode.QUEUE:
                    queue_error = _queue_visible_building_prerequisite(context, after)
                    if queue_error is not None:
                        return queue_error
                return TaskResult.replan(_unmet_requirement_replan_message(after))
            if _is_upgrade_context_screen(after.screen_type) and _building_upgrade_confirmation_is_visible(after):
                if _has_upgrade_confirmation_pending(context.runtime_state):
                    return TaskResult.failure("Building upgrade did not consume the confirmed final upgrade action.", retryable=True)
                _set_upgrade_confirmation_pending(context.runtime_state)
                return TaskResult.replan("Building upgrade confirmation opened and still needs the final `Upgrade` click.")
            if _is_upgrade_context_screen(after.screen_type) and _building_speedup_is_visible(after):
                return _finish_started_upgrade_success(
                    context.runtime_state,
                    "Building upgrade started and the building screen now shows `Speedup`.",
                )
            if _is_upgrade_context_screen(after.screen_type) and not after.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
                _clear_upgrade_confirmation_pending(context.runtime_state)
                _set_success_verification_stage(context.runtime_state, _SUCCESS_VERIFICATION_STAGE_RETURN_HOME)
                return TaskResult.replan("Building upgrade needs one home-city verification pass after leaving the details screen.")
            if after.screen_type == ScreenType.PNC_HOME_CITY:
                return _verify_started_upgrade_at_home_city(context.runtime_state, after)
            if after.screen_type == ScreenType.PNC_BUILD_QUEUE:
                return _verify_started_upgrade_from_build_queue(context.runtime_state, after)
            if after.screen_type == ScreenType.UNKNOWN:
                return TaskResult.replan("Building upgrade transition is still settling after the verified upgrade click.")
            if _is_upgrade_context_screen(after.screen_type) and after.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
                if _has_upgrade_confirmation_pending(context.runtime_state):
                    return TaskResult.failure("Building upgrade did not consume the confirmed final upgrade action.", retryable=True)
            return TaskResult.failure("Building upgrade did not consume the verified upgrade action.", retryable=True)
        if after.screen_type == ScreenType.PNC_HOME_CITY:
            _clear_upgrade_confirmation_pending(context.runtime_state)
            _clear_pending_target(context.runtime_state)
            remaining_priorities = _active_requested_priorities(context.params, context.runtime_state)
            if not remaining_priorities:
                return _requested_priority_exhausted_result(context.runtime_state)
            return TaskResult.replan("Returned to home city after verifying the selected building is not upgradeable.")
        return TaskResult.failure("Building upgrade did not produce a verified state change.", retryable=True)


def _visible_supported_buildings(
    observation: Observation,
    runtime_state: dict[str, Any],
) -> tuple[DetectedSpatialObject, ...]:
    """Returns visible supported home-city buildings that have not already been proven ineligible."""

    blocked_object_ids = _ineligible_object_ids(runtime_state)
    blocked_signatures = _ineligible_target_signatures(runtime_state)
    visible_buildings: list[DetectedSpatialObject] = []
    for object_ in observation.spatial_objects(SpatialObjectKind.HOME_BUILDING):
        priority = _building_priority_from_object(object_)
        if priority is None:
            continue
        if priority in blocked_object_ids:
            continue
        if _building_target_signature(object_) in blocked_signatures:
            continue
        visible_buildings.append(object_)
    return tuple(visible_buildings)


def _visible_requested_buildings(
    observation: Observation,
    runtime_state: dict[str, Any],
    priorities: tuple[BuildingPriority, ...],
) -> tuple[DetectedSpatialObject, ...]:
    """Returns visible supported buildings whose exact ids are still requested by the active policy."""

    requested_priorities = set(priorities)
    return tuple(
        object_
        for object_ in _visible_supported_buildings(observation, runtime_state)
        if _building_priority_from_object(object_) in requested_priorities
    )


def _building_priority_from_object(object_: DetectedSpatialObject) -> BuildingPriority | None:
    """Returns the typed building priority for one upgradeable home-city spatial object."""

    metadata = getattr(object_, "metadata", {})
    object_id = home_city_object_id_from_object(object_)
    if object_id is None:
        return None
    if not home_city_object_supports_action(metadata, BuildingAction.UPGRADE):
        return None
    try:
        return BuildingPriority(object_id.value)
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

    runtime_state[_BUILDING_UPGRADE_PENDING_TARGET_STATE_KEY] = _PendingBuildingTarget(
        signature=_building_target_signature(object_),
        priority=_building_priority_from_object(object_),
        starting_level=object_.level,
    )


def _clear_pending_target(runtime_state: dict[str, Any]) -> None:
    """Clears the currently inspected building target after the task changes state."""

    runtime_state.pop(_BUILDING_UPGRADE_PENDING_TARGET_STATE_KEY, None)


def _pending_target(runtime_state: dict[str, Any]) -> _PendingBuildingTarget | None:
    """Returns the currently inspected building target when one is still tracked."""

    pending = runtime_state.get(_BUILDING_UPGRADE_PENDING_TARGET_STATE_KEY)
    if pending is None:
        return None
    if isinstance(pending, _PendingBuildingTarget):
        return pending
    raise TypeError("Unexpected building_upgrade_pending_target state.")


def _mark_pending_target_ineligible(runtime_state: dict[str, Any]) -> None:
    """Records the currently inspected building target as not upgradeable and clears the pending slot."""

    pending = runtime_state.pop(_BUILDING_UPGRADE_PENDING_TARGET_STATE_KEY, None)
    if pending is None:
        return
    if not isinstance(pending, _PendingBuildingTarget):
        raise TypeError("Unexpected building_upgrade_pending_target state.")
    signatures = _ineligible_target_signatures(runtime_state)
    signatures.add(pending.signature)
    runtime_state[_BUILDING_UPGRADE_INELIGIBLE_TARGETS_STATE_KEY] = signatures
    if pending.priority is not None:
        _remember_ineligible_priority(runtime_state, pending.priority)


def _set_upgrade_confirmation_pending(runtime_state: dict[str, Any]) -> None:
    """Records that one verified upgrade click opened a final confirmation step."""

    runtime_state[_BUILDING_UPGRADE_CONFIRMATION_PENDING_STATE_KEY] = True


def _clear_upgrade_confirmation_pending(runtime_state: dict[str, Any]) -> None:
    """Clears any remembered final-confirmation state for the current upgrade attempt."""

    runtime_state.pop(_BUILDING_UPGRADE_CONFIRMATION_PENDING_STATE_KEY, None)


def _has_upgrade_confirmation_pending(runtime_state: dict[str, Any]) -> bool:
    """Returns whether the current upgrade attempt already consumed its one confirmation replan."""

    return bool(runtime_state.get(_BUILDING_UPGRADE_CONFIRMATION_PENDING_STATE_KEY))


def _set_post_start_help_pending(runtime_state: dict[str, Any]) -> None:
    """Records that the just-started upgrade exposed one optional alliance-help action."""

    runtime_state[_BUILDING_UPGRADE_POST_START_HELP_PENDING_STATE_KEY] = True


def _clear_post_start_help_pending(runtime_state: dict[str, Any]) -> None:
    """Clears any remembered post-upgrade help action for the current task run."""

    runtime_state.pop(_BUILDING_UPGRADE_POST_START_HELP_PENDING_STATE_KEY, None)


def _has_post_start_help_pending(runtime_state: dict[str, Any]) -> bool:
    """Returns whether the task still needs to opportunistically request post-upgrade help."""

    return bool(runtime_state.get(_BUILDING_UPGRADE_POST_START_HELP_PENDING_STATE_KEY))


def _set_focus_pending(runtime_state: dict[str, Any]) -> None:
    """Records that the last planned increment was a home-city camera search move."""

    runtime_state[_BUILDING_UPGRADE_FOCUS_PENDING_STATE_KEY] = True


def _clear_focus_pending(runtime_state: dict[str, Any]) -> None:
    """Clears any remembered home-city search increment state."""

    runtime_state.pop(_BUILDING_UPGRADE_FOCUS_PENDING_STATE_KEY, None)


def _has_focus_pending(runtime_state: dict[str, Any]) -> bool:
    """Returns whether the task is waiting for one planned home-city search move to settle."""

    return bool(runtime_state.get(_BUILDING_UPGRADE_FOCUS_PENDING_STATE_KEY))


def _set_success_verification_stage(runtime_state: dict[str, Any], stage: str) -> None:
    """Stores the ordered post-start verification stage for the current upgrade attempt."""

    runtime_state[_BUILDING_UPGRADE_SUCCESS_VERIFICATION_STAGE_STATE_KEY] = stage


def _clear_success_verification_stage(runtime_state: dict[str, Any]) -> None:
    """Clears any remembered post-start verification stage for the current upgrade attempt."""

    runtime_state.pop(_BUILDING_UPGRADE_SUCCESS_VERIFICATION_STAGE_STATE_KEY, None)


def _set_speedup_completion_pending(runtime_state: dict[str, Any]) -> None:
    """Remembers that inventory speedups were submitted and level verification is required."""

    runtime_state[_BUILDING_UPGRADE_SPEEDUP_COMPLETION_PENDING_STATE_KEY] = True


def _speedup_completion_pending(runtime_state: dict[str, Any]) -> bool:
    """Returns whether an inventory speedup needs final home-city verification."""

    value = runtime_state.get(_BUILDING_UPGRADE_SPEEDUP_COMPLETION_PENDING_STATE_KEY, False)
    if not isinstance(value, bool):
        raise TypeError("Unexpected building_upgrade_speedup_completion_pending state.")
    return value


def _clear_speedup_completion_pending(runtime_state: dict[str, Any]) -> None:
    """Clears the inventory-speedup verification marker."""

    runtime_state.pop(_BUILDING_UPGRADE_SPEEDUP_COMPLETION_PENDING_STATE_KEY, None)


def _success_verification_stage(runtime_state: dict[str, Any]) -> str | None:
    """Returns the ordered post-start verification stage when one is still pending."""

    stage = runtime_state.get(_BUILDING_UPGRADE_SUCCESS_VERIFICATION_STAGE_STATE_KEY)
    if stage is None:
        return None
    if isinstance(stage, str):
        return stage
    raise TypeError("Unexpected building_upgrade_success_verification_stage state.")


def _ineligible_target_signatures(runtime_state: dict[str, Any]) -> set[tuple[object, ...]]:
    """Returns the mutable set of visible building targets already proven ineligible for this step."""

    value = runtime_state.get(_BUILDING_UPGRADE_INELIGIBLE_TARGETS_STATE_KEY)
    if isinstance(value, set):
        return value
    signatures: set[tuple[object, ...]] = set()
    runtime_state[_BUILDING_UPGRADE_INELIGIBLE_TARGETS_STATE_KEY] = signatures
    return signatures


def _ineligible_object_ids(runtime_state: dict[str, Any]) -> set[BuildingPriority]:
    """Returns the mutable set of globally ineligible unique building ids for the current task run."""

    value = runtime_state.get(_BUILDING_UPGRADE_INELIGIBLE_OBJECT_IDS_STATE_KEY)
    if isinstance(value, set):
        return value
    blocked_object_ids: set[BuildingPriority] = set()
    runtime_state[_BUILDING_UPGRADE_INELIGIBLE_OBJECT_IDS_STATE_KEY] = blocked_object_ids
    return blocked_object_ids


def _remaining_requested_priorities(
    priorities: tuple[BuildingPriority, ...],
    runtime_state: dict[str, Any],
) -> tuple[BuildingPriority, ...]:
    """Returns requested priorities that remain viable after unique-target ineligibility is accounted for."""

    blocked_object_ids = _ineligible_object_ids(runtime_state)
    return tuple(priority for priority in priorities if priority not in blocked_object_ids)


def _active_requested_priorities(
    policy: BuildingUpgradePolicy,
    runtime_state: dict[str, Any],
) -> tuple[BuildingPriority, ...]:
    """Returns the queued prerequisite or the caller's remaining original priorities."""

    queued = _queued_building_prerequisite(runtime_state)
    if queued is not None:
        return (queued.prerequisite,)
    return _remaining_requested_priorities(policy.priority, runtime_state)


def _queue_visible_building_prerequisite(
    context: TaskContext,
    observation: Observation,
) -> TaskResult | None:
    """Records one OCR-proven prerequisite or returns a terminal unsupported-requirement failure."""

    requirement_text = _building_requirement_text(observation)
    parsed = _parse_building_requirement(requirement_text)
    if parsed is None:
        return TaskResult.failure(
            f"Cannot queue unsupported building prerequisite '{requirement_text or '<unknown>'}'."
        )
    prerequisite, required_level = parsed
    existing = _queued_building_prerequisite(context.runtime_state)
    current_target = _building_priority_from_screen(observation.screen_type)
    pending = _pending_target(context.runtime_state)
    root_target = (
        existing.root_target
        if existing is not None
        else pending.priority
        if pending is not None and pending.priority is not None
        else current_target
    )
    if root_target is None:
        return TaskResult.failure("Cannot queue a prerequisite without a canonical requested building target.")
    context.runtime_state[_BUILDING_UPGRADE_QUEUED_PREREQUISITE_STATE_KEY] = _QueuedBuildingPrerequisite(
        root_target=root_target,
        prerequisite=prerequisite,
        required_level=required_level,
    )
    return None


def _parse_building_requirement(requirement_text: str | None) -> tuple[BuildingPriority, int] | None:
    """Parses one OCR requirement such as `Alliance Hall : Lv.23` into a canonical target."""

    if requirement_text is None:
        return None
    match = _BUILDING_REQUIREMENT_PATTERN.match(requirement_text.strip())
    if match is None:
        return None
    definition = home_city_object_definition_for_label(match.group("building").strip())
    if definition is None:
        return None
    try:
        priority = BuildingPriority(definition.id.value)
    except ValueError:
        return None
    return priority, int(match.group("level"))


def _queued_building_prerequisite(runtime_state: dict[str, Any]) -> _QueuedBuildingPrerequisite | None:
    """Returns the active prerequisite queue entry when one has been recorded."""

    value = runtime_state.get(_BUILDING_UPGRADE_QUEUED_PREREQUISITE_STATE_KEY)
    if value is None or isinstance(value, _QueuedBuildingPrerequisite):
        return value
    raise TypeError("Unexpected building_upgrade_queued_prerequisite state.")


def _building_priority_from_screen(screen_type: ScreenType) -> BuildingPriority | None:
    """Returns the canonical building priority implied by one exact building-owned screen when modeled."""

    object_id = home_city_object_id_for_screen(screen_type)
    if object_id is None:
        return None
    try:
        return BuildingPriority(object_id.value)
    except ValueError:
        return None


def _mark_screen_priority_ineligible(runtime_state: dict[str, Any], screen_type: ScreenType) -> None:
    """Marks one exact building-owned screen as globally ineligible when it represents a unique building."""

    priority = _building_priority_from_screen(screen_type)
    if priority is None:
        return
    _remember_ineligible_priority(runtime_state, priority)


def _remember_ineligible_priority(runtime_state: dict[str, Any], priority: BuildingPriority) -> None:
    """Stores one unique building priority as globally ineligible for the remainder of this step."""

    if _building_priority_is_repeatable(priority):
        return
    blocked_object_ids = _ineligible_object_ids(runtime_state)
    blocked_object_ids.add(priority)
    runtime_state[_BUILDING_UPGRADE_INELIGIBLE_OBJECT_IDS_STATE_KEY] = blocked_object_ids


def _building_priority_is_repeatable(priority: BuildingPriority) -> bool:
    """Returns whether the requested building priority can have multiple distinct home-city instances."""

    return is_repeatable_home_city_object(HomeCityObjectId(priority.value))


def _is_upgrade_context_screen(screen_type: ScreenType) -> bool:
    """Returns whether the current screen can verify or execute one building upgrade action."""

    return screen_type == ScreenType.PNC_BUILDING_DETAILS or is_upgradeable_primary_screen(screen_type)


def _verify_started_upgrade_at_home_city(runtime_state: dict[str, Any], observation: Observation) -> TaskResult:
    """Evaluates the ordered home-city success proofs after a verified upgrade click has settled."""

    if _home_city_active_build_is_visible(observation):
        return _complete_started_upgrade_at_home_city(
            runtime_state,
            observation,
            _home_city_timer_success_message(observation),
        )
    if _can_open_build_queue(observation):
        _set_success_verification_stage(runtime_state, _SUCCESS_VERIFICATION_STAGE_OPEN_BUILD_QUEUE)
        return TaskResult.replan(
            "Home-city verification could not prove the upgrade start, so the build queue needs checking before the final level comparison."
        )
    if _home_city_pending_target_level_increased(observation, runtime_state):
        return _complete_started_upgrade_at_home_city(
            runtime_state,
            observation,
            _home_city_level_increase_success_message(runtime_state, observation),
        )
    return TaskResult.failure("Building upgrade could not be verified from the home city.", retryable=True)


def _verify_started_upgrade_from_build_queue(runtime_state: dict[str, Any], observation: Observation) -> TaskResult:
    """Evaluates the build-queue timer proof before falling back to one final level comparison."""

    timer_text = _build_queue_active_timer_text(observation)
    if timer_text is not None:
        return _finish_started_upgrade_success(
            runtime_state,
            f"Building upgrade started and the build queue shows timer '{timer_text}'.",
        )
    _set_success_verification_stage(runtime_state, _SUCCESS_VERIFICATION_STAGE_RETURN_HOME_FOR_LEVEL)
    return TaskResult.replan("Build queue did not expose an active timer and needs one final building-level verification.")


def _complete_started_upgrade_at_home_city(
    runtime_state: dict[str, Any],
    observation: Observation,
    success_message: str,
) -> TaskResult:
    """Returns the canonical success or help-follow-up result once one ordered success proof lands at home city."""

    _clear_upgrade_confirmation_pending(runtime_state)
    _clear_last_unmet_requirement(runtime_state)
    _clear_success_verification_stage(runtime_state)
    _clear_speedup_completion_pending(runtime_state)
    _clear_pending_target(runtime_state)
    _clear_focus_pending(runtime_state)
    if _home_build_help_is_available(observation):
        _set_post_start_help_pending(runtime_state)
        return TaskResult.replan(f"{success_message} Available alliance help can be requested.")
    _clear_post_start_help_pending(runtime_state)
    return _queued_prerequisite_or_upgrade_success(runtime_state, success_message)


def _finish_started_upgrade_success(runtime_state: dict[str, Any], message: str) -> TaskResult:
    """Clears post-start runtime state once one non-home success proof has already completed the task."""

    queued = _queued_building_prerequisite(runtime_state)
    _clear_post_start_help_pending(runtime_state)
    _clear_upgrade_confirmation_pending(runtime_state)
    _clear_last_unmet_requirement(runtime_state)
    _clear_success_verification_stage(runtime_state)
    _clear_speedup_completion_pending(runtime_state)
    _clear_pending_target(runtime_state)
    _clear_focus_pending(runtime_state)
    runtime_state.pop(_BUILDING_UPGRADE_QUEUED_PREREQUISITE_STATE_KEY, None)
    if queued is not None:
        return TaskResult.success(_queued_prerequisite_success_message(queued, message))
    return TaskResult.success(message)


def _queued_prerequisite_or_upgrade_success(runtime_state: dict[str, Any], message: str) -> TaskResult:
    """Returns a prerequisite-queue outcome when the started upgrade belongs to a dependency."""

    queued = _queued_building_prerequisite(runtime_state)
    runtime_state.pop(_BUILDING_UPGRADE_QUEUED_PREREQUISITE_STATE_KEY, None)
    if queued is None:
        return TaskResult.success(message)
    return TaskResult.success(_queued_prerequisite_success_message(queued, message))


def _queued_prerequisite_success_message(queued: _QueuedBuildingPrerequisite, message: str) -> str:
    """Formats the scheduler-ready outcome after one prerequisite upgrade enters the game queue."""

    return (
        f"Prerequisite '{queued.prerequisite.value}' toward Lv.{queued.required_level} started for "
        f"'{queued.root_target.value}'. Run the original upgrade again after construction completes. {message}"
    )


def _finish_already_active_upgrade_skip(runtime_state: dict[str, Any], message: str) -> TaskResult:
    """Clears runtime upgrade state once the task proves another active construction already occupies the queue."""

    _clear_post_start_help_pending(runtime_state)
    _clear_upgrade_confirmation_pending(runtime_state)
    _clear_last_unmet_requirement(runtime_state)
    _clear_success_verification_stage(runtime_state)
    _clear_speedup_completion_pending(runtime_state)
    _clear_pending_target(runtime_state)
    _clear_focus_pending(runtime_state)
    return TaskResult.skipped(message)


def _home_city_timer_success_message(observation: Observation) -> str:
    """Returns the success message for the primary home-city timer proof."""

    timer_text = _home_city_active_build_timer_text(observation)
    if timer_text is None:
        return "Building upgrade started and a home-city construction timer is visible."
    return f"Building upgrade started and the home city shows timer '{timer_text}'."


def _visible_pending_target(observation: Observation, runtime_state: dict[str, Any]) -> DetectedSpatialObject | None:
    """Returns the pending home-city target when it remains visible after upgrade verification."""

    pending = _pending_target(runtime_state)
    if pending is None:
        return None
    visible_buildings = observation.spatial_objects(SpatialObjectKind.HOME_BUILDING)
    exact_match = next((object_ for object_ in visible_buildings if _building_target_signature(object_) == pending.signature), None)
    if exact_match is not None:
        return exact_match
    if pending.priority is None or _building_priority_is_repeatable(pending.priority):
        return None
    return next((object_ for object_ in visible_buildings if _building_priority_from_object(object_) == pending.priority), None)


def _home_city_pending_target_level_increased(observation: Observation, runtime_state: dict[str, Any]) -> bool:
    """Returns whether the visible pending target now shows a higher level than the pre-upgrade baseline."""

    pending = _pending_target(runtime_state)
    if pending is None or pending.starting_level is None:
        return False
    target = _visible_pending_target(observation, runtime_state)
    if target is None or target.level is None:
        return False
    return target.level > pending.starting_level


def _home_city_level_increase_success_message(runtime_state: dict[str, Any], observation: Observation) -> str:
    """Returns the success message for the fast-complete level-increase fallback proof."""

    pending = _pending_target(runtime_state)
    target = _visible_pending_target(observation, runtime_state)
    if pending is None or target is None or pending.starting_level is None or target.level is None:
        return "Building upgrade finished quickly and the building level increased."
    target_name = target.name_text or (pending.priority.value if pending.priority is not None else "building")
    return (
        f"Building upgrade finished quickly and '{target_name}' increased "
        f"from Lv.{pending.starting_level} to Lv.{target.level}."
    )


def _building_upgrade_confirmation_is_visible(observation: Observation) -> bool:
    """Returns whether the current building screen is showing the shared final upgrade-confirmation layout."""

    return observation.has(UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL)


def _building_speedup_is_visible(observation: Observation) -> bool:
    """Returns whether the current building screen replaced `Upgrade` with the shared `Speedup` control."""

    return observation.has(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON)


def _set_last_unmet_requirement(runtime_state: dict[str, Any], observation: Observation) -> None:
    """Stores the most recent unmet prerequisite label so terminal skips can explain why the task stopped."""

    requirement_text = _building_requirement_text(observation)
    if requirement_text is None:
        _clear_last_unmet_requirement(runtime_state)
        return
    runtime_state[_BUILDING_UPGRADE_LAST_UNMET_REQUIREMENT_STATE_KEY] = requirement_text


def _clear_last_unmet_requirement(runtime_state: dict[str, Any]) -> None:
    """Clears any remembered unmet prerequisite description for the current task run."""

    runtime_state.pop(_BUILDING_UPGRADE_LAST_UNMET_REQUIREMENT_STATE_KEY, None)


def _requested_priority_exhausted_result(runtime_state: dict[str, Any]) -> TaskResult:
    """Returns the terminal known outcome once every requested unique target has been proven ineligible."""

    requirement_text = runtime_state.get(_BUILDING_UPGRADE_LAST_UNMET_REQUIREMENT_STATE_KEY)
    if isinstance(requirement_text, str) and requirement_text.strip() != "":
        return TaskResult.failure(
            f"Requested building upgrade is blocked by unmet prerequisite '{requirement_text}', "
            "and prerequisite resolution is not supported yet."
        )
    return TaskResult.skipped("No requested building upgrades are currently eligible.")


def _unmet_requirement_replan_message(observation: Observation) -> str:
    """Returns the shared replan message for building screens gated by unmet upgrade prerequisites."""

    requirement_text = _building_requirement_text(observation)
    if requirement_text is None:
        return "Building upgrade is blocked by an unmet requirement and needs to return to home city."
    return f"Building upgrade is blocked by unmet requirement '{requirement_text}' and needs to return to home city."
