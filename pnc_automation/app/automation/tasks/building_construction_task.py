"""Task that constructs one exact building from its canonical empty-slot family."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.app.automation.engine.task import (
    BaseAutomationTask,
    CastleTargetPolicy,
    TaskId,
    TaskPreflight,
    TaskResult,
)
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.automation.tasks.building_workflow_support import (
    build_queue_active_timer_text,
    building_requirement_is_visible,
    building_requirement_text,
    can_open_build_queue,
    home_build_help_is_available,
    home_city_active_build_is_visible,
)
from pnc_automation.app.automation.tasks.open_building_support import plan_focus_requested_home_city_object
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, KeyEventAction, TapAction, WaitAction
from pnc_automation.app.pnc.domain.building_catalog import (
    ConstructionSlotFamily,
    HomeCityObjectId,
    home_city_object_definition_for_label,
    home_city_object_id_for_screen,
    home_city_object_id_from_metadata,
    require_building_construction_source,
)
from pnc_automation.app.pnc.domain.observation import (
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.domain.policy_models import BuildingConstructionPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

_OPTION_SELECTED = "building_construction_option_selected"
_ACTION_EXECUTED = "building_construction_action_executed"
_TARGET_COUNT_BEFORE = "building_construction_target_count_before"
_VERIFY_ATTEMPTS = "building_construction_verification_attempts"
_QUEUE_CHECK_ATTEMPTED = "building_construction_queue_check_attempted"
_SETTLE_WAIT_MS = 1500
_MAX_VERIFY_ATTEMPTS = 2


class BuildingConstructionTask(BaseAutomationTask):
    """Constructs one building with a single mutation followed by bounded verification."""

    id = TaskId.BUILDING_CONSTRUCT
    castle_target_policy = CastleTargetPolicy.OPTIONAL
    preflight = TaskPreflight.HOME_CITY

    def max_replans_per_step(self, context: TaskContext) -> int | None:
        """Allows a bounded home-city search plus direct-start verification."""

        return context.flows.home_city_navigator.focus_step_budget() + 8

    def parse_params(self, params: Mapping[str, Any]) -> BuildingConstructionPolicy:
        """Builds the typed construction policy."""

        return BuildingConstructionPolicy.from_params(params)

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Accepts stable game screens after the runner-owned home-city preflight."""

        del context
        return observation.screen_type not in {
            ScreenType.ANDROID_HOME,
            ScreenType.PNC_LOGIN,
            ScreenType.PNC_ACCOUNT_SWITCH,
            ScreenType.PNC_CASTLE_SELECTION,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans source-slot opening, option selection, one final build tap, or verification."""

        target = context.params.building
        source = require_building_construction_source(target)
        action_executed = bool(context.runtime_state.get(_ACTION_EXECUTED))

        if action_executed:
            return self._plan_verification(context, observation)
        if observation.screen_type == ScreenType.PNC_BUILDING_CONSTRUCTION:
            if not _construction_screen_matches_target(observation, target):
                return []
            if not observation.has(UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON):
                return []
            context.runtime_state[_ACTION_EXECUTED] = True
            return [
                TapAction(
                    selector_id=UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON,
                    reason=f"confirm_resource_funded_construction_of_{target.value}",
                    observe_after=True,
                )
            ]
        if observation.screen_type == ScreenType.PNC_BUILD_QUEUE:
            return [KeyEventAction(key_code="KEYCODE_BACK", reason="leave_idle_build_queue", observe_after=True)]
        if observation.screen_type == source.menu_screen_type:
            if not observation.has(source.option_selector_id):
                return []
            if bool(context.runtime_state.get(_OPTION_SELECTED)):
                return [
                    WaitAction(
                        milliseconds=_SETTLE_WAIT_MS,
                        reason="verify_building_option_selection",
                        observe_after=True,
                    )
                ]
            context.runtime_state[_OPTION_SELECTED] = True
            return [
                TapAction(
                    selector_id=source.option_selector_id,
                    reason=f"construct_{target.value}",
                    observe_after=True,
                )
            ]
        if observation.screen_type != ScreenType.PNC_HOME_CITY:
            return context.flows.ensure_home_city(observation)
        if home_city_active_build_is_visible(observation) or home_build_help_is_available(observation):
            return []
        visible_slot = next(
            (
                object_
                for object_ in observation.spatial_objects(SpatialObjectKind.HOME_EMPTY_SLOT)
                if home_city_object_id_from_metadata(object_.metadata) == source.slot_id
            ),
            None,
        )
        if visible_slot is not None:
            _record_target_count_before(context.runtime_state, observation, target)
            return context.flows.open_visible_home_city_object(
                observation,
                visible_slot,
                reason=f"open_{source.slot_family.value}_construction_slot",
                runtime_state=context.runtime_state,
            )
        if source.slot_family in {ConstructionSlotFamily.FIXED, ConstructionSlotFamily.LARGE}:
            return plan_focus_requested_home_city_object(
                flows=context.flows,
                observation=observation,
                target=target,
                runtime_state=context.runtime_state,
                reason=f"open_{source.slot_family.value}_construction_position",
            )
        return context.flows.open_home_city_empty_slot(
            observation,
            _source_slot_query(source.slot_id),
            runtime_state=context.runtime_state,
        )

    def _plan_verification(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans bounded read-only checks and never repeats the construction mutation."""

        if building_requirement_is_visible(observation):
            return []
        if (
            observation.screen_type == ScreenType.PNC_HOME_CITY
            and can_open_build_queue(observation)
            and not bool(context.runtime_state.get(_QUEUE_CHECK_ATTEMPTED))
        ):
            attempts = _verification_attempts(context.runtime_state)
            if attempts >= 1:
                context.runtime_state[_QUEUE_CHECK_ATTEMPTED] = True
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                        reason="open_build_queue_after_construction",
                        observe_after=True,
                    )
                ]
        attempts = _verification_attempts(context.runtime_state)
        if attempts >= _MAX_VERIFY_ATTEMPTS:
            return []
        context.runtime_state[_VERIFY_ATTEMPTS] = attempts + 1
        return [WaitAction(milliseconds=_SETTLE_WAIT_MS, reason="verify_building_construction", observe_after=True)]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Verifies source opening, resource failure, or direct construction start."""

        target = context.params.building
        source = require_building_construction_source(target)
        if not bool(context.runtime_state.get(_ACTION_EXECUTED)):
            if _construction_busy(before):
                return TaskResult.skipped("Another building construction is already active.")
            if bool(context.runtime_state.get(_OPTION_SELECTED)):
                if (
                    after.screen_type == ScreenType.PNC_BUILDING_CONSTRUCTION
                    and _construction_screen_matches_target(after, target)
                    and after.has(UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON)
                ):
                    return TaskResult.replan(f"Opened the resource-funded confirmation for '{target.value}'.")
                if after.screen_type == source.menu_screen_type and after.has(source.option_selector_id):
                    return TaskResult.failure("The construction option was not consumed; it will not be tapped again.")
                if after.screen_type == ScreenType.UNKNOWN:
                    return TaskResult.replan("Waiting for the construction confirmation to become observable.")
                return TaskResult.failure("The selected construction option did not open its confirmation screen.")
            if after.screen_type == source.menu_screen_type and after.has(source.option_selector_id):
                return TaskResult.replan(f"Opened the {source.slot_family.value} construction menu.")
            if after.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.UNKNOWN}:
                return TaskResult.replan("Continuing the bounded search for the requested construction slot.")
            return TaskResult.failure("Could not open the requested building's canonical construction slot.", retryable=True)

        if building_requirement_is_visible(after):
            requirement = building_requirement_text(after)
            suffix = "" if requirement is None else f": {requirement}"
            return TaskResult.failure(f"Insufficient resources or unmet construction requirement{suffix}.")
        if _construction_started(after, target, context.runtime_state):
            return TaskResult.success(f"Construction of '{target.value}' started.")
        if after.screen_type == ScreenType.PNC_BUILDING_CONSTRUCTION:
            return TaskResult.failure("The ordinary Build action was not consumed; it will not be tapped again.")
        if after.screen_type == source.menu_screen_type and after.has(source.option_selector_id):
            return TaskResult.failure("The construction option was not consumed; it will not be tapped again.")
        if after.screen_type == ScreenType.UNKNOWN:
            return TaskResult.replan("Construction started without a resource popup; waiting for direct-start proof.")
        if _verification_attempts(context.runtime_state) < _MAX_VERIFY_ATTEMPTS:
            return TaskResult.replan("Construction started without a resource popup; checking timer and build queue.")
        return TaskResult.failure("Construction action was consumed but its start could not be verified.", retryable=True)


def _source_slot_query(slot_id: HomeCityObjectId) -> SpatialObjectQuery:
    """Builds the exact typed spatial query for one canonical empty slot."""

    return SpatialObjectQuery(
        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
        kind=SpatialObjectKind.HOME_EMPTY_SLOT,
        metadata_key="home_city_object_id",
        metadata_value=slot_id.value,
    )


def _verification_attempts(runtime_state: dict[str, Any]) -> int:
    """Returns the validated count of post-action observation attempts."""

    value = runtime_state.get(_VERIFY_ATTEMPTS, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError("Unexpected building_construction_verification_attempts state.")
    return value


def _construction_busy(observation: Observation) -> bool:
    """Returns whether an existing construction already occupies the build queue."""

    return home_city_active_build_is_visible(observation) or home_build_help_is_available(observation)


def _construction_started(
    observation: Observation,
    target: HomeCityObjectId,
    runtime_state: dict[str, Any],
) -> bool:
    """Returns whether a timer, queue row, target screen, or increased city count proves start."""

    if home_city_active_build_is_visible(observation):
        return True
    if build_queue_active_timer_text(observation) is not None:
        return True
    if home_city_object_id_for_screen(observation.screen_type) == target and observation.has(
        UiElementId.PNC_BUILDING_SPEEDUP_BUTTON
    ):
        return True
    before_count = runtime_state.get(_TARGET_COUNT_BEFORE)
    if before_count is None or observation.screen_type != ScreenType.PNC_HOME_CITY:
        return False
    if not isinstance(before_count, int) or isinstance(before_count, bool) or before_count < 0:
        raise TypeError("Unexpected building_construction_target_count_before state.")
    return _visible_target_count(observation, target) > before_count


def _record_target_count_before(
    runtime_state: dict[str, Any],
    observation: Observation,
    target: HomeCityObjectId,
) -> None:
    """Records the visible target count once, immediately before opening the chosen empty slot."""

    runtime_state.setdefault(_TARGET_COUNT_BEFORE, _visible_target_count(observation, target))


def _visible_target_count(observation: Observation, target: HomeCityObjectId) -> int:
    """Counts visible home-city buildings with the requested canonical object id."""

    return sum(
        1
        for object_ in observation.spatial_objects(SpatialObjectKind.HOME_BUILDING)
        if home_city_object_id_from_metadata(object_.metadata) == target
    )


def _construction_screen_matches_target(observation: Observation, target: HomeCityObjectId) -> bool:
    """Returns whether the construction confirmation header names the requested building."""

    header = observation.get(UiElementId.PNC_BUILDING_CONSTRUCTION_HEADER)
    if header is None or header.extracted_text is None:
        return False
    definition = home_city_object_definition_for_label(header.extracted_text)
    return definition is not None and definition.id == target
