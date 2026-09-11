"""Translates declarative actions into ADB-backed emulator interactions."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from pnc_automation.core.infra.emulator.session import BlueStacksSession
from pnc_automation.core.errors import FrameProvenanceError, SelectorResolutionError
from pnc_automation.app.automation.engine.read_only_policy import ReadOnlyProbePolicy
from pnc_automation.app.pnc.domain.chat import chat_channel_selector_id
from pnc_automation.app.pnc.domain.mail import multiline_text_field_selector_ids
from pnc_automation.app.pnc.domain.action_requests import (
    ActionRequest,
    ActionTimingProfile,
    InputTextAction,
    KeyEventAction,
    LaunchAppAction,
    SelectChatChannelAction,
    SwipeAction,
    SwipePurpose,
    TapAction,
    TapListEntryAction,
    TapPointAction,
    TapSpatialObjectAction,
    WaitAction,
    resolve_swipe_points_for_action,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    DetectedSpatialObject,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
    SpatialSurfaceType,
    VisibleElement,
    list_entry_matches,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry


@dataclass(slots=True)
class ActionExecutor:
    """Executes action requests against one emulator session."""

    session: BlueStacksSession
    selector_registry: SelectorRegistry
    stable_click_delay_ms: int
    post_action_observe_delay_ms: int
    chat_stable_click_delay_ms: int
    chat_post_action_observe_delay_ms: int
    logger: logging.LoggerAdapter
    world_map_movement_stable_click_delay_ms: int = 300
    world_map_movement_post_action_observe_delay_ms: int = 800
    sleep: Callable[[float], None] = time.sleep
    read_only_policy: ReadOnlyProbePolicy = ReadOnlyProbePolicy()
    max_input_attempts: int | None = None
    input_attempts: int = 0
    input_attempt_deadline: float | None = None

    def execute_actions(
        self,
        actions: Sequence[ActionRequest],
        initial_observation: Observation,
        *,
        observe: Callable[[str, ObservationRequest | None], Observation],
    ) -> Observation:
        """Executes the action sequence and returns the freshest observation."""

        current_observation = initial_observation
        observed_after_action = False
        executed_any_action = False
        for index, action in enumerate(actions):
            action_executed = self.execute_action(action, current_observation)
            executed_any_action = executed_any_action or action_executed
            if getattr(action, "observe_after", False) and action_executed:
                current_observation = self.observe_action_follow_up(
                    action=action,
                    label_prefix=f"post_action_{index + 1}",
                    observe=observe,
                )
                if not self.validate_follow_up(action, current_observation):
                    return current_observation
                observed_after_action = True
        if executed_any_action and not observed_after_action:
            self._sleep_ms(self.post_action_observe_delay_ms)
            return observe("post_actions", None)
        return current_observation

    def observe_action_follow_up(
        self,
        *,
        action: ActionRequest,
        label_prefix: str,
        observe: Callable[[str, ObservationRequest | None], Observation],
    ) -> Observation:
        """Captures one action follow-up and promotes transient narrow-request misses to one broad runtime re-observation."""

        self._sleep_ms(self._observe_delay_ms_for(action))
        follow_up_request = action.follow_up_request
        first_after = observe(label_prefix, follow_up_request)
        if self._should_retry_with_full_runtime_request(
            action=action,
            observation=first_after,
            request=follow_up_request,
        ):
            return observe(f"{label_prefix}_runtime_retry", ObservationRequest.full_runtime_default())
        return first_after

    def execute_action(self, action: ActionRequest, observation: Observation) -> bool:
        """Executes one declarative action and returns whether it changed emulator state."""

        self.logger.info("Executing action.", extra={"action_type": type(action).__name__, "screen_type": observation.screen_type})
        if isinstance(action, TapAction):
            self.selector_registry.require_supported(action.selector_id)
            element = observation.require(action.selector_id)
            self._validate_visible_element_provenance(element, observation, action)
            target = element.action_point if element.action_point is not None else element.bounds.center()
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, TapPointAction):
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self.session.tap_point(action.x, action.y)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, TapListEntryAction):
            entry = self._require_entry(action, observation)
            self._validate_list_entry_provenance(entry, observation, action)
            if entry.kind in {
                ListEntryKind.DAILY_QUEST,
                ListEntryKind.RESOURCE_ITEM,
                ListEntryKind.RESOURCE_INVENTORY_EXCLUSION,
                ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED,
            }:
                self._validate_protected_row_geometry(entry, action)
                assert entry.action_point is not None
                target = entry.action_point
            else:
                target = entry.action_point if action.use_action_point and entry.action_point is not None else entry.bounds.center()
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, TapSpatialObjectAction):
            target = action.target_point
            if target is None:
                object_ = self._require_spatial_object(action, observation)
                target = (
                    object_.action_point
                    if action.use_action_point and object_.action_point is not None
                    else object_.bounds.center()
                )
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, SelectChatChannelAction):
            if observation.screen_type != ScreenType.PNC_CHAT:
                raise SelectorResolutionError(
                    "SelectChatChannelAction requires the shared chat screen.",
                    screen_type=observation.screen_type,
                )
            if observation.is_chat_channel_active(action.channel):
                return False
            selector_id = chat_channel_selector_id(action.channel)
            self.selector_registry.require_supported(selector_id)
            element = observation.require(selector_id)
            self._validate_visible_element_provenance(element, observation, action)
            target = element.action_point if element.action_point is not None else element.bounds.center()
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, InputTextAction):
            if action.selector_id is not None:
                self.selector_registry.require_supported(action.selector_id)
                element = observation.require(action.selector_id)
                self._validate_visible_element_provenance(element, observation, action)
                x, y = element.action_point if element.action_point is not None else element.bounds.center()
            else:
                x = y = 0
            with self._authorized_input(action, observation):
                if action.selector_id is not None:
                    self._record_input_attempt(action, observation)
                    self.session.tap_point(x, y)
                    self._sleep_ms(self._stable_delay_ms_for(action))
                    self._clear_existing_text(action, observation)
                self._input_text(action, observation)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, KeyEventAction):
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self.session.press_key(action.key_code)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, WaitAction):
            self._validate_read_only_action(action, observation)
            self._sleep_ms(action.milliseconds)
            return True
        if isinstance(action, LaunchAppAction):
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self.session.launch_app()
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, SwipeAction):
            if observation.image_size is None:
                raise SelectorResolutionError("Swipe actions require the current screenshot dimensions.")
            width, height = observation.image_size
            start_x, start_y, end_x, end_y = resolve_swipe_points_for_action(
                width=width,
                height=height,
                action=action,
            )
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self.session.swipe(
                    start_x,
                    start_y,
                    end_x,
                    end_y,
                    duration_ms=action.duration_ms,
                    input_source=action.input_source.value,
                    gesture_primitive=action.gesture_primitive.value,
                )
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        raise SelectorResolutionError(f"Unsupported action type '{type(action).__name__}'.", action_type=type(action).__name__)

    def validate_follow_up(self, action: ActionRequest, observation: Observation) -> bool:
        """Returns whether the action sequence can safely continue from the observed follow-up state."""

        if isinstance(action, SelectChatChannelAction):
            if observation.blocking_popup or observation.screen_type in {
                ScreenType.PNC_POPUP,
                ScreenType.PNC_LOADING,
                ScreenType.UNKNOWN,
            }:
                return False
            if observation.screen_type != ScreenType.PNC_CHAT:
                return False
            if not observation.is_chat_channel_active(action.channel):
                return False
            if observation.chat_draft_empty is None:
                return False
            return True
        follow_up_request = getattr(action, "follow_up_request", None)
        if follow_up_request is None:
            return True
        return self._matches_follow_up_request(observation, follow_up_request)

    def _require_entry(self, action: TapListEntryAction, observation: Observation) -> DetectedListEntry:
        """Returns the matching list entry for one dynamic-entry tap."""

        matches = [
            entry
            for entry in observation.entries(action.entry_kind)
            if list_entry_matches(
                entry,
                title_text=action.title_text,
                metadata_key=action.metadata_key,
                metadata_value=action.metadata_value,
                selected=action.selected,
            )
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SelectorResolutionError(
                "The requested list entry tap target is ambiguous; semantic identity matched multiple rows.",
                entry_kind=action.entry_kind,
                title_text=action.title_text,
                metadata_key=action.metadata_key,
                metadata_value=action.metadata_value,
                match_count=len(matches),
            )
        raise SelectorResolutionError(
            "Could not resolve the requested list entry tap target.",
            entry_kind=action.entry_kind,
            title_text=action.title_text,
            metadata_key=action.metadata_key,
            metadata_value=action.metadata_value,
        )

    @contextmanager
    def _authorized_input(self, action: ActionRequest, observation: Observation):
        """Holds one session provenance lock through the complete logical input."""

        self._validate_read_only_action(action, observation)

        if observation.decision.coordinate_only:
            if not (
                isinstance(action, SwipeAction)
                and action.purpose == SwipePurpose.WORLD_MAP_MOVEMENT
                and observation.screen_type == ScreenType.PNC_WORLD_MAP
                and observation.spatial_surface is not None
                and observation.spatial_surface.surface_type == SpatialSurfaceType.WORLD_MAP
                and observation.spatial_surface.viewport.coordinate is not None
            ):
                raise SelectorResolutionError(
                    "Coordinate-only observations authorize only typed world-map movement swipes.",
                    action_type=type(action).__name__,
                    screen_type=observation.screen_type,
                )
        elif not observation.decision.action_eligible:
            raise SelectorResolutionError(
                "UI input requires a clear or independently blocked screen decision.",
                action_type=type(action).__name__,
                screen_type=observation.screen_type,
                guard=observation.decision.guard,
            )
        elif observation.decision.guard == GuardVerdict.BLOCKED and not (
            isinstance(action, (TapAction, TapListEntryAction))
            or (isinstance(action, InputTextAction) and action.selector_id is not None)
        ):
            raise SelectorResolutionError(
                "A blocked screen authorizes only controls proved on the blocking overlay; raw input is denied.",
                action_type=type(action).__name__,
                screen_type=observation.screen_type,
            )

        frame_ref = observation.frame_ref
        if frame_ref is None:
            raise SelectorResolutionError(
                "UI input requires a screenshot with session provenance; unverified observations cannot dispatch.",
                action_type=type(action).__name__,
                screen_type=observation.screen_type,
            )
        try:
            with self.session.authorized_input(frame_ref):
                yield
        except FrameProvenanceError as error:
            raise SelectorResolutionError(
                "UI input proof was rejected by the session provenance guard.",
                action_type=type(action).__name__,
                screen_type=observation.screen_type,
                provenance_error=error.message,
                provenance_error_type=type(error).__name__,
                provenance_details=error.details,
            ) from error

    def _validate_visible_element_provenance(
        self,
        element: object,
        observation: Observation,
        action: ActionRequest,
    ) -> None:
        """Rejects selector geometry that was not published for this exact decision and frame."""

        if observation.frame_ref is None:
            raise SelectorResolutionError(
                "UI input requires a screenshot with session provenance; unverified observations cannot dispatch.",
                action_type=type(action).__name__,
                screen_type=observation.screen_type,
            )
        if not isinstance(element, VisibleElement):
            # The map is typed by Observation; this branch protects malformed fakes.
            raise SelectorResolutionError("Selector target has an invalid runtime type.", action_type=type(action).__name__)
        if element.frame_ref != observation.frame_ref or element.source_screen != observation.screen_type:
            raise SelectorResolutionError(
                "Selector target provenance does not match the current observation.",
                action_type=type(action).__name__,
                selector_id=element.selector_id,
                screen_type=observation.screen_type,
            )
        if element.source_layout_id != observation.decision.layout_id:
            raise SelectorResolutionError(
                "Selector target layout does not match the current screen decision.",
                action_type=type(action).__name__,
                selector_id=element.selector_id,
                screen_type=observation.screen_type,
            )

    def _validate_list_entry_provenance(
        self,
        entry: DetectedListEntry,
        observation: Observation,
        action: ActionRequest,
    ) -> None:
        """Rejects list-row geometry that came from another frame or source layout."""

        if observation.frame_ref is None:
            raise SelectorResolutionError(
                "UI input requires a screenshot with session provenance; unverified observations cannot dispatch.",
                action_type=type(action).__name__,
                screen_type=observation.screen_type,
            )
        if entry.frame_ref != observation.frame_ref or entry.source_screen != observation.screen_type:
            raise SelectorResolutionError(
                "List entry provenance does not match the current observation.",
                action_type=type(action).__name__,
                entry_kind=entry.kind,
            )
        if entry.source_layout_id != observation.decision.layout_id:
            raise SelectorResolutionError(
                "List entry layout does not match the current screen decision.",
                action_type=type(action).__name__,
                entry_kind=entry.kind,
            )

    @staticmethod
    def _validate_protected_row_geometry(
        entry: DetectedListEntry,
        action: TapListEntryAction,
    ) -> None:
        """Require independently materialized action geometry for protected row families."""

        if not action.use_action_point:
            raise SelectorResolutionError(
                "Protected row taps must explicitly request the observed action point.",
                entry_kind=entry.kind,
            )
        if entry.kind in {
            ListEntryKind.RESOURCE_INVENTORY_EXCLUSION,
            ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED,
        }:
            raise SelectorResolutionError(
                "Excluded or unresolved inventory rows are never actionable.",
                entry_kind=entry.kind,
            )
        if entry.row_status != RowRecognitionStatus.COMPLETE:
            raise SelectorResolutionError(
                "Protected row taps require a complete visual row.",
                entry_kind=entry.kind,
                row_status=entry.row_status,
            )
        if entry.action_point is None or entry.action_bounds is None:
            raise SelectorResolutionError(
                "Protected row taps require an action point and independently detected action bounds.",
                entry_kind=entry.kind,
            )
        if not entry.bounds.contains_bounds(entry.action_bounds):
            raise SelectorResolutionError(
                "Protected row action bounds must remain inside the row bounds.",
                entry_kind=entry.kind,
            )
        if not entry.action_bounds.contains_point(entry.action_point):
            raise SelectorResolutionError(
                "Protected row action point must lie inside its action bounds.",
                entry_kind=entry.kind,
            )

    def _validate_read_only_action(self, action: ActionRequest, observation: Observation) -> None:
        """Checks the explicit source-state action policy before any dispatch."""

        self.read_only_policy.validate(action, observation)

    def _record_input_attempt(self, action: ActionRequest, observation: Observation) -> None:
        """Counts one imminent low-level input and enforces a bounded probe budget."""

        self.input_attempts += 1
        if self.input_attempt_deadline is not None and time.monotonic() > self.input_attempt_deadline:
            raise SelectorResolutionError(
                "Read-only probe exhausted its duration budget before input dispatch.",
                input_deadline=self.input_attempt_deadline,
                input_attempts=self.input_attempts,
                action_type=type(action).__name__,
                screen_type=observation.screen_type,
            )
        if self.max_input_attempts is not None and self.input_attempts > self.max_input_attempts:
            raise SelectorResolutionError(
                "Read-only probe exhausted its low-level input-attempt budget.",
                max_input_attempts=self.max_input_attempts,
                input_attempts=self.input_attempts,
                action_type=type(action).__name__,
                screen_type=observation.screen_type,
            )

    def configure_input_attempt_budget(self, max_inputs: int | None, *, duration_seconds: float | None = None) -> None:
        """Sets and resets the optional low-level input budget for a bounded probe."""

        if max_inputs is not None and max_inputs <= 0:
            raise ValueError("Input-attempt budget must be positive when configured.")
        if duration_seconds is not None and duration_seconds <= 0:
            raise ValueError("Input-attempt duration budget must be positive when configured.")
        self.max_input_attempts = max_inputs
        self.input_attempts = 0
        self.input_attempt_deadline = None if duration_seconds is None else time.monotonic() + duration_seconds

    def _require_spatial_object(self, action: TapSpatialObjectAction, observation: Observation) -> DetectedSpatialObject:
        """Returns the matching visible spatial object for one spatial-object tap."""

        if action.query is None:
            raise SelectorResolutionError("TapSpatialObjectAction requires a semantic spatial-object query.")
        return observation.require_spatial_object(action.query)

    def _sleep_ms(self, milliseconds: int) -> None:
        """Sleeps using millisecond units for action pacing."""

        if milliseconds <= 0:
            return
        self.sleep(milliseconds / 1000.0)

    def _stable_delay_ms_for(self, action: ActionRequest) -> int:
        """Returns the pacing delay applied after one concrete UI action."""

        if action.timing_profile == ActionTimingProfile.CHAT:
            return self.chat_stable_click_delay_ms
        if action.timing_profile == ActionTimingProfile.WORLD_MAP_MOVEMENT:
            return self.world_map_movement_stable_click_delay_ms
        return self.stable_click_delay_ms

    def _observe_delay_ms_for(self, action: ActionRequest) -> int:
        """Returns the delay applied before one observe-after capture."""

        if action.timing_profile == ActionTimingProfile.CHAT:
            return self.chat_post_action_observe_delay_ms
        if action.timing_profile == ActionTimingProfile.WORLD_MAP_MOVEMENT:
            return self.world_map_movement_post_action_observe_delay_ms
        return self.post_action_observe_delay_ms

    def _clear_existing_text(self, action: InputTextAction, observation: Observation) -> None:
        """Clears one selector-backed draft when the action requests replace-in-place input."""

        if not action.replace_existing:
            return
        if action.selector_id is None:
            raise SelectorResolutionError("InputTextAction.replace_existing requires a selector-backed field.")
        field_state = observation.text_field_state(action.selector_id)
        if field_state is None:
            if action.selector_id == UiElementId.PNC_CHAT_INPUT_FIELD and observation.chat_draft_empty is not None:
                if observation.chat_draft_empty:
                    return
                delete_budget = _delete_budget(observation.chat_draft_text)
                self._record_input_attempt(action, observation)
                self.session.press_key("KEYCODE_MOVE_END")
                for _ in range(delete_budget):
                    self._record_input_attempt(action, observation)
                    self.session.press_key("KEYCODE_DEL")
                self._sleep_ms(self._stable_delay_ms_for(action))
                return
            raise SelectorResolutionError(
                "Observed text-field state is required before replacing existing text.",
                selector_id=action.selector_id,
                screen_type=observation.screen_type,
            )
        if field_state.empty:
            return
        self._record_input_attempt(action, observation)
        self.session.press_key("KEYCODE_MOVE_END")
        for _ in range(_delete_budget(field_state.text)):
            self._record_input_attempt(action, observation)
            self.session.press_key("KEYCODE_DEL")
        self._sleep_ms(self._stable_delay_ms_for(action))

    def _input_text(self, action: InputTextAction, observation: Observation) -> None:
        """Inputs text through the shared single-line or multiline field policy."""

        if "\n" not in action.text and "\r" not in action.text:
            self._record_input_attempt(action, observation)
            self.session.input_text(action.text)
            return
        if action.selector_id is None:
            raise SelectorResolutionError("Multiline text entry requires a selector-backed field.", text=action.text)
        if action.selector_id not in multiline_text_field_selector_ids():
            raise SelectorResolutionError(
                "The requested selector does not support multiline text entry.",
                selector_id=action.selector_id,
                screen_type=observation.screen_type,
            )
        normalized_lines = action.text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for index, line in enumerate(normalized_lines):
            self._record_input_attempt(action, observation)
            self.session.input_text(line)
            if index == len(normalized_lines) - 1:
                continue
            self._record_input_attempt(action, observation)
            self.session.press_key("KEYCODE_ENTER")

    def _matches_follow_up_request(
        self,
        observation: Observation,
        request: ObservationRequest,
    ) -> bool:
        """Returns whether one observed follow-up landed on a usable screen for the remaining action sequence."""

        if observation.blocking_popup or observation.screen_type in {
            ScreenType.PNC_POPUP,
            ScreenType.PNC_LOADING,
            ScreenType.UNKNOWN,
        }:
            return False
        if not request.candidate_screen_types:
            return True
        return observation.screen_type in request.candidate_screen_types

    def _should_retry_with_full_runtime_request(
        self,
        *,
        action: ActionRequest,
        observation: Observation,
        request: ObservationRequest | None,
    ) -> bool:
        """Returns whether one narrow follow-up should be retried immediately with the full runtime observation request."""

        del action
        if request is None or request == ObservationRequest.full_runtime_default():
            return False
        if request == ObservationRequest.world_map_movement_proof_follow_up():
            return False
        if observation.has(UiElementId.PNC_STATUS_BANNER):
            return False
        if observation.screen_type == ScreenType.UNKNOWN:
            return True
        return self._world_map_surface_retry_required(observation=observation, request=request)

    def _world_map_surface_retry_required(
        self,
        *,
        observation: Observation,
        request: ObservationRequest,
    ) -> bool:
        """Returns whether a world-map follow-up landed on the correct coarse screen but still lacks a usable parsed viewport."""

        if request != ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP):
            return False
        if observation.screen_type != ScreenType.PNC_WORLD_MAP:
            return False
        surface = observation.spatial_surface
        return (
            surface is None
            or surface.surface_type != SpatialSurfaceType.WORLD_MAP
            or surface.viewport.coordinate is None
        )


def _delete_budget(draft_text: str | None) -> int:
    """Returns a conservative delete count for one observed reusable text field."""

    if draft_text is None or draft_text.strip() == "":
        return 36
    return max(len(draft_text) + 8, 24)
