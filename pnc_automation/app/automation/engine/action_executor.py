"""Translates declarative actions into ADB-backed emulator interactions."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

from pnc_automation.core.infra.emulator.session import BlueStacksSession
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchEvent,
    InputDispatchFailure,
    InputDispatchRecord,
    SwipeDispatch,
    TapDispatch,
    WheelDispatch,
)
from pnc_automation.core.errors import FrameProvenanceError, SelectorResolutionError
from pnc_automation.core.infra.diagnostics.performance import performance_wait
from pnc_automation.app.automation.engine.read_only_policy import ReadOnlyProbePolicy
from pnc_automation.app.automation.engine.developmental_control import (
    DevelopmentalCasePurpose,
    DevelopmentalControlScope,
    MeasuredControlProof,
)
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
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
    WheelAction,
    resolve_swipe_points_for_action,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    DetectedSpatialObject,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectSourceKind,
    SpatialSurfaceType,
    VisibleElement,
    list_entry_matches,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.domain.screen_decision import is_reviewed_viewport
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.text.normalization import normalize_ocr_text


_HUMAN_DELAY_JITTER_RANGE = (0.9, 1.1)
_HUMAN_KEY_DELAY_MS_RANGE = (25, 70)


@dataclass(slots=True)
class ActionExecutor:
    """Executes action requests against one emulator session."""

    session: BlueStacksSession
    stable_click_delay_ms: int
    post_action_observe_delay_ms: int
    chat_stable_click_delay_ms: int
    chat_post_action_observe_delay_ms: int
    logger: logging.LoggerAdapter
    selector_registry: SelectorRegistry
    world_map_movement_stable_click_delay_ms: int = 300
    world_map_movement_post_action_observe_delay_ms: int = 800
    sleep: Callable[[float], None] = time.sleep
    read_only_policy: ReadOnlyProbePolicy = ReadOnlyProbePolicy()
    max_input_attempts: int | None = None
    input_attempts: int = 0
    input_attempt_deadline: float | None = None
    human_mode: bool = False
    rng: random.Random = field(default_factory=random.Random, repr=False)
    input_dispatch_recorder: Callable[[InputDispatchEvent], None] | None = None

    def execute_developmental_control(
        self,
        scope: DevelopmentalControlScope,
        proof: MeasuredControlProof,
        observation: Observation,
    ) -> InputDispatchRecord:
        """Send one released, freshly measured task-owned control.

        The caller owns the frozen CaseSpec and consumes its case attempt before
        calling. This operation verifies their typed relationships; it does not
        infer visual meaning from UNKNOWN or promote a production selector.
        Use CoreRuntime's wrapper for the mandatory immediate follow-up capture.
        """

        self._validate_developmental_control(scope, proof, observation)
        with self._authorized_frame_input(scope, observation):
            self._record_input_attempt(scope, observation)
            dispatch = self._dispatch_tap_point(
                scope, observation, *proof.action_point,
                exact_geometry=True, safe_bounds=proof.bounds,
            )
        assert observation.frame_ref is not None
        return InputDispatchRecord(
            source_frame=observation.frame_ref,
            dispatch=dispatch,
            artifact_path=observation.artifact_path,
        )

    def _validate_developmental_control(
        self,
        scope: DevelopmentalControlScope,
        proof: MeasuredControlProof,
        observation: Observation,
    ) -> None:
        """Check released-case, physical-body, and current-frame relations."""

        def refuse(reason: str) -> None:
            raise SelectorResolutionError(reason, case_id=scope.case_id, control=scope.control_name)

        if self.read_only_policy.enabled or scope.read_only:
            refuse("A read-only scope cannot send a developmental control.")
        if self.max_input_attempts is None or self.input_attempt_deadline is None:
            refuse("Developmental control requires an active cumulative input and duration budget.")
        if scope.purpose not in {
            DevelopmentalCasePurpose.CONTROL_DISCOVERY,
            DevelopmentalCasePurpose.CONTROL_VALIDATION,
        }:
            refuse("This released case does not authorize a developmental control input.")
        if not isinstance(scope.effect, WorkflowEffect) or not isinstance(proof.intended_effect, WorkflowEffect):
            refuse("Developmental control requires one typed, known effect.")
        if scope.effect != proof.intended_effect:
            refuse("Measured control effect differs from the released case effect.")
        if scope.effect == WorkflowEffect.RESOURCE_CHANGING and not scope.resource_allowance_ref:
            refuse("Resource-changing control lacks the released allowance reference.")
        if (not isinstance(scope.target, HomeCityObjectId)
                or not all((scope.assignment_id, scope.case_id, scope.case_spec_ref, scope.operation_id,
                    scope.released_action_id, scope.control_name))):
            refuse("Developmental control lacks a named released case or action.")
        attempt = scope.attempt
        if (attempt.case_id != scope.case_id or attempt.control_name != scope.control_name
                or not attempt.journal_ref or attempt.limit < 1
                or not 1 <= attempt.number <= attempt.limit):
            refuse("Developmental control lacks a matching consumed case attempt.")
        if proof.control_name != scope.control_name or proof.foreground_target != scope.target:
            refuse("Measured foreground control differs from the released target or control.")
        if not proof.task_owned_foreground or not proof.visual_reason.strip():
            refuse("Measured control lacks explicit task-owned foreground visual evidence.")
        if (not scope.allowed_source_screens
                or not all(isinstance(screen, ScreenType) for screen in scope.allowed_source_screens)
                or observation.screen_type not in scope.allowed_source_screens
                or observation.screen_type in {
                    ScreenType.PNC_LOADING, ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP,
                }):
            refuse("This current screen is not an assigned task-owned control source.")
        if observation.frame_ref is None or observation.artifact_path is None:
            refuse("Developmental control requires a persisted current frame.")
        if (proof.frame_ref != observation.frame_ref or proof.artifact_path != observation.artifact_path
                or proof.frame_fingerprint != observation.frame_fingerprint
                or proof.image_size != observation.image_size or proof.decision != observation.decision
                or proof.screen_type != observation.screen_type or not proof.frame_fingerprint):
            refuse("Measured control annotation does not bind the current persisted frame.")
        if observation.image_size is None or not is_reviewed_viewport(observation.image_size):
            refuse("Measured control lacks a reviewed native viewport.")
        width, height = observation.image_size
        if (proof.bounds.width <= 0 or proof.bounds.height <= 0
                or proof.bounds.x < 0 or proof.bounds.y < 0
                or proof.bounds.x + proof.bounds.width > width
                or proof.bounds.y + proof.bounds.height > height
                or not proof.bounds.contains_point(proof.action_point)):
            refuse("Measured control point and bounds must lie inside the native frame.")
        self._validate_developmental_input_chain(scope, observation)

    @staticmethod
    def _validate_developmental_input_chain(
        scope: DevelopmentalControlScope, observation: Observation,
    ) -> None:
        """Require one exact body receipt and a continuous physical input chain."""

        def refuse(reason: str) -> None:
            raise SelectorResolutionError(reason, case_id=scope.case_id)

        witness = scope.body_entry
        source = witness.observation
        body = witness.action.expected_object
        receipt = witness.receipt
        if (source.frame_ref is None or source.artifact_path is None
                or source.frame_fingerprint is None
                or source.image_size is None or not is_reviewed_viewport(source.image_size)
                or witness.case_id != scope.case_id
                or witness.operation_id != scope.operation_id
                or receipt.source_frame != source.frame_ref
                or receipt.artifact_path != source.artifact_path
                or source.screen_type != ScreenType.PNC_HOME_CITY
                or source.decision.guard != GuardVerdict.CLEAR
                or not witness.action.exact_geometry or body is None
                or body.kind != SpatialObjectKind.HOME_BUILDING
                or body.source_kind != SpatialObjectSourceKind.TEMPLATE
                or body.frame_ref != source.frame_ref
                or body.source_screen != source.screen_type
                or body.source_layout_id != source.decision.layout_id
                or body.home_city_slot != scope.home_city_slot
                or home_city_object_id_from_metadata(body.metadata) != scope.target
                or body.action_bounds is None or body.action_point is None
                or not body.action_bounds.contains_point(body.action_point)
                or witness.action.target_point != body.action_point
                or not isinstance(receipt.dispatch, TapDispatch)
                or receipt.dispatch.point != body.action_point
                or receipt.dispatch.input_sequence != source.frame_ref.input_sequence + 1):
            refuse("Developmental control lacks an exact semantic body-entry receipt.")
        source.require_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE).require_visible_object(body)
        chain = scope.input_chain
        if not chain or chain[0] != receipt:
            refuse("Developmental control input chain lacks its exact body-entry receipt.")
        previous = receipt
        for current in chain[1:]:
            if (not isinstance(current.dispatch, TapDispatch)
                    or current.source_frame.session_id != previous.source_frame.session_id
                    or current.source_frame.session_epoch != previous.source_frame.session_epoch
                    or current.source_frame.input_sequence != previous.dispatch.input_sequence
                    or current.dispatch.input_sequence != current.source_frame.input_sequence + 1):
                refuse("Developmental control input chain has an unrecorded or foreign input.")
            previous = current
        first = scope.latest_input_follow_up
        first_ref = first.frame_ref
        current_ref = observation.frame_ref
        if (first_ref is None or current_ref is None or first.artifact_path is None
                or first.frame_fingerprint is None
                or first_ref.session_id != previous.source_frame.session_id
                or first_ref.session_epoch != previous.source_frame.session_epoch
                or first_ref.input_sequence != previous.dispatch.input_sequence
                or first_ref.capture_sequence != previous.source_frame.capture_sequence + 1
                or current_ref.session_id != first_ref.session_id
                or current_ref.session_epoch != first_ref.session_epoch
                or current_ref.input_sequence != first_ref.input_sequence
                or current_ref.capture_sequence < first_ref.capture_sequence):
            refuse("Developmental control requires an immediate follow-up or fresh no-input recapture.")

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

    def execute_action(
        self,
        action: ActionRequest,
        observation: Observation,
        *,
        required_update_relaunch: bool = False,
    ) -> bool:
        """Executes one declarative action and returns whether it changed emulator state."""

        self.logger.info("Executing action.", extra={"action_type": type(action).__name__, "screen_type": observation.screen_type})
        if isinstance(action, TapAction):
            self._validate_selector_input(action.selector_id)
            element = observation.require(action.selector_id)
            self._validate_visible_element_provenance(element, observation, action)
            target = element.action_point if element.action_point is not None else element.bounds.center()
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self._dispatch_tap_point(action, observation, *target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, TapPointAction):
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self._dispatch_tap_point(action, observation, action.x, action.y)
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
                self._dispatch_tap_point(action, observation, *target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, TapSpatialObjectAction):
            if action.expected_object is not None:
                expected = action.expected_object
                if observation.frame_ref is None or expected.frame_ref != observation.frame_ref:
                    raise SelectorResolutionError(
                        "Spatial tap target belongs to a different capture frame.",
                        object_kind=expected.kind,
                    )
                surface_type = None if action.query is None else action.query.surface_type
                observation.require_spatial_surface(surface_type).require_visible_object(expected)
                if action.target_point != expected.action_point:
                    raise SelectorResolutionError(
                        "Spatial tap point differs from the selected visible object.",
                        object_kind=expected.kind,
                    )
                if expected.source_kind == SpatialObjectSourceKind.YOLO:
                    self._validate_yolo_spatial_action(
                        object_=expected,
                        observation=observation,
                        target=action.target_point,
                        query=action.query,
                        require_unique_query=False,
                    )
                if action.exact_geometry:
                    if action.target_point is None:
                        raise SelectorResolutionError(
                            "Exact spatial-object taps require the observed action point.",
                            object_kind=expected.kind,
                        )
                    if expected.action_bounds is None or expected.action_bounds.width <= 0 or expected.action_bounds.height <= 0:
                        raise SelectorResolutionError(
                            "Exact spatial-object taps require nonempty observed action bounds.",
                            object_kind=expected.kind,
                        )
                    if observation.image_size is None or not (
                        0 <= action.target_point[0] < observation.image_size[0]
                        and 0 <= action.target_point[1] < observation.image_size[1]
                    ):
                        raise SelectorResolutionError(
                            "Exact spatial-object tap point must lie inside the current display.",
                            object_kind=expected.kind,
                            target_point=action.target_point,
                            image_size=observation.image_size,
                        )
            target = action.target_point
            if target is None:
                object_ = self._require_spatial_object(action, observation)
                if object_.source_kind == SpatialObjectSourceKind.YOLO:
                    self._validate_yolo_spatial_action(
                        object_=object_,
                        observation=observation,
                        target=object_.action_point,
                        query=action.query,
                        require_unique_query=True,
                    )
                target = (
                    object_.action_point
                    if object_.source_kind == SpatialObjectSourceKind.YOLO
                    or (action.use_action_point and object_.action_point is not None)
                    else object_.bounds.center()
                )
            elif action.expected_object is None and observation.spatial_surface is not None:
                surface = observation.spatial_surface
                matches = tuple(
                    object_
                    for object_ in surface.objects
                    if object_.source_kind == SpatialObjectSourceKind.YOLO
                    and (
                        object_.bounds.contains_point(target)
                        or (
                            action.query is not None
                            and (action.query.surface_type is None or action.query.surface_type == surface.surface_type)
                            and object_.matches(action.query)
                        )
                    )
                )
                if matches:
                    if action.query is None or len(matches) != 1:
                        raise SelectorResolutionError(
                            "World YOLO spatial taps require one exact semantic object.",
                        )
                    self._validate_yolo_spatial_action(
                        object_=matches[0],
                        observation=observation,
                        target=target,
                        query=action.query,
                        require_unique_query=True,
                    )
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                if action.exact_geometry:
                    assert action.expected_object is not None and action.expected_object.action_bounds is not None
                    self._dispatch_tap_point(
                        action,
                        observation,
                        *target,
                        exact_geometry=True,
                        safe_bounds=action.expected_object.action_bounds,
                    )
                else:
                    self._dispatch_tap_point(action, observation, *target)
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
            self._validate_selector_input(selector_id)
            element = observation.require(selector_id)
            self._validate_visible_element_provenance(element, observation, action)
            target = element.action_point if element.action_point is not None else element.bounds.center()
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                self._dispatch_tap_point(action, observation, *target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, InputTextAction):
            if action.selector_id is not None:
                self._validate_selector_input(action.selector_id)
                element = observation.require(action.selector_id)
                self._validate_visible_element_provenance(element, observation, action)
                x, y = element.action_point if element.action_point is not None else element.bounds.center()
            else:
                x = y = 0
            with self._authorized_input(action, observation):
                if action.selector_id is not None:
                    self._record_input_attempt(action, observation)
                    self._dispatch_tap_point(action, observation, x, y)
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
            with self._authorized_input(
                action,
                observation,
                required_update_relaunch=required_update_relaunch,
            ):
                self._record_input_attempt(action, observation)
                self.session.launch_app()
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, SwipeAction):
            if observation.image_size is None:
                raise SelectorResolutionError("Swipe actions require the current screenshot dimensions.")
            width, height = observation.image_size
            self._validate_home_city_swipe(action)
            start_x, start_y, end_x, end_y = resolve_swipe_points_for_action(
                width=width,
                height=height,
                action=action,
            )
            if action.purpose == SwipePurpose.HOME_CITY_CAMERA:
                for point in ((start_x, start_y), (end_x, end_y)):
                    if not (0 <= point[0] < width and 0 <= point[1] < height):
                        raise SelectorResolutionError(
                            "Home camera swipe endpoints must lie inside the current display.",
                            point=point,
                            image_size=(width, height),
                        )
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                try:
                    dispatch = self.session.swipe(
                        start_x,
                        start_y,
                        end_x,
                        end_y,
                        duration_ms=action.duration_ms,
                        input_source=action.input_source.value,
                        gesture_primitive=action.gesture_primitive.value,
                        exact_geometry=action.exact_geometry,
                        safe_bounds=action.safe_bounds,
                    )
                except Exception as error:
                    self._emit_dispatch_failure(action, observation, error, input_kind="swipe")
                    raise
                self._emit_dispatch_record(action, observation, dispatch)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, WheelAction):
            if observation.image_size is None:
                raise SelectorResolutionError("Wheel actions require the current screenshot dimensions.")
            # Cheap authorization gates run before the bounded transport setup;
            # authorized_input retains the source frame and it is revalidated
            # for age again after the blocking mapping read, right before send.
            self._validate_read_only_action(action, observation)
            try:
                self.session.prepare_scroll_transport()
            except Exception as error:
                self._emit_dispatch_failure(action, observation, error, input_kind="wheel")
                raise
            with self._authorized_input(action, observation):
                self._record_input_attempt(action, observation)
                try:
                    dispatch = self.session.scroll_wheel(
                        action.x,
                        action.y,
                        vertical_detent=action.vertical_detent,
                        frame_size=observation.image_size,
                    )
                except Exception as error:
                    self._emit_dispatch_failure(action, observation, error, input_kind="wheel")
                    raise
                self._emit_dispatch_record(action, observation, dispatch)
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
    def _authorized_input(
        self,
        action: ActionRequest,
        observation: Observation,
        *,
        required_update_relaunch: bool = False,
    ):
        """Holds one session provenance lock through the complete logical input."""

        self._validate_read_only_action(
            action,
            observation,
            required_update_relaunch=required_update_relaunch,
        )

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

        with self._authorized_frame_input(action, observation):
            yield

    @contextmanager
    def _authorized_frame_input(
        self, action: ActionRequest | DevelopmentalControlScope, observation: Observation,
    ):
        """Reuse the session's epoch, age, latest-frame, and once-only lock."""

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

    @staticmethod
    def _validate_home_city_swipe(action: SwipeAction) -> None:
        """Requires the reviewed Home-camera swipe shape before any dispatch."""

        if action.purpose != SwipePurpose.HOME_CITY_CAMERA:
            return
        if any(
            ratio is None
            for ratio in (action.start_x_ratio, action.start_y_ratio, action.end_x_ratio, action.end_y_ratio)
        ):
            raise SelectorResolutionError(
                "Home camera swipes require explicit start and end ratios.",
                purpose=action.purpose.value,
            )
        if not action.exact_geometry:
            raise SelectorResolutionError(
                "Home camera swipes require exact geometry.",
                purpose=action.purpose.value,
            )
        bounds = action.safe_bounds
        if bounds is None or bounds.width <= 0 or bounds.height <= 0:
            raise SelectorResolutionError(
                "Home camera swipes require nonempty native safe bounds.",
                purpose=action.purpose.value,
                safe_bounds=bounds,
            )

    @staticmethod
    def _home_city_input(action: ActionRequest | DevelopmentalControlScope) -> bool:
        """Returns whether one action is canonical Home-city input for typed traces."""

        if isinstance(action, WheelAction):
            return True
        if isinstance(action, SwipeAction):
            return action.purpose == SwipePurpose.HOME_CITY_CAMERA
        if isinstance(action, TapSpatialObjectAction):
            return action.exact_geometry
        return False

    def _dispatch_tap_point(
        self,
        action: ActionRequest | DevelopmentalControlScope,
        observation: Observation,
        x: int,
        y: int,
        *,
        exact_geometry: bool = False,
        safe_bounds: Bounds | None = None,
    ) -> TapDispatch:
        """Sends one tap and binds that send boundary to exactly one typed event.

        A send failure emits one InputDispatchFailure, then preserves the
        original exception — keeping the send error as the primary error even
        when reporting it also fails. The dispatch receipt is emitted only
        after the send returned, so a successful-send reporting failure can
        never fabricate a send-failure event or a second tap.
        """

        try:
            if exact_geometry or safe_bounds is not None:
                dispatch = self.session.tap_point(
                    x,
                    y,
                    exact_geometry=exact_geometry,
                    safe_bounds=safe_bounds,
                )
            else:
                dispatch = self.session.tap_point(x, y)
        except Exception as error:
            try:
                self._emit_dispatch_failure(action, observation, error, input_kind="tap")
            except BaseException as report_error:
                raise error from report_error
            raise
        self._emit_dispatch_record(action, observation, dispatch)
        return dispatch

    def _emit_dispatch_record(
        self,
        action: ActionRequest | DevelopmentalControlScope,
        observation: Observation,
        dispatch: SwipeDispatch | WheelDispatch | TapDispatch,
    ) -> None:
        """Publishes one actual dispatch receipt bound to its authorizing frame."""

        recorder = self.input_dispatch_recorder
        if recorder is None or observation.frame_ref is None:
            return
        recorder(
            InputDispatchRecord(
                source_frame=observation.frame_ref,
                dispatch=dispatch,
                artifact_path=observation.artifact_path,
                home_city=self._home_city_input(action),
            )
        )

    def _emit_dispatch_failure(
        self,
        action: ActionRequest | DevelopmentalControlScope,
        observation: Observation,
        error: BaseException,
        *,
        input_kind: str,
    ) -> None:
        """Publishes one input attempt that ended without a dispatch receipt."""

        recorder = self.input_dispatch_recorder
        if recorder is None:
            return
        details = getattr(error, "details", None)
        phase = details.get("failure_phase") if isinstance(details, dict) else None
        recorder(
            InputDispatchFailure(
                source_frame=observation.frame_ref,
                input_kind=input_kind,
                failure_phase=phase if isinstance(phase, str) else "dispatch",
                exception_type=type(error).__name__,
                artifact_path=observation.artifact_path,
                home_city=self._home_city_input(action),
            )
        )

    def _validate_selector_input(self, selector_id: UiElementId) -> None:
        """Reject read-only label targets before center fallback or input authorization."""

        selector = self.selector_registry.require_supported(selector_id)
        if selector.interaction_kind == SelectorInteractionKind.LABEL:
            raise SelectorResolutionError(
                "Label selectors cannot be used as UI input targets.",
                selector_id=selector_id,
                interaction_kind=selector.interaction_kind.value,
            )

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

    def _validate_read_only_action(
        self,
        action: ActionRequest,
        observation: Observation,
        *,
        required_update_relaunch: bool = False,
    ) -> None:
        """Checks the explicit source-state action policy before any dispatch."""

        self.read_only_policy.validate(
            action,
            observation,
            required_update_relaunch=required_update_relaunch,
        )

    def _record_input_attempt(
        self, action: ActionRequest | DevelopmentalControlScope, observation: Observation,
    ) -> None:
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

    @staticmethod
    def _validate_yolo_spatial_action(
        *,
        object_: DetectedSpatialObject,
        observation: Observation,
        target: tuple[int, int] | None,
        query: SpatialObjectQuery | None,
        require_unique_query: bool,
    ) -> None:
        """Require reviewed geometry, one semantic match, and current-frame YOLO provenance."""

        qualification = object_.action_qualification
        if qualification is None or object_.action_point is None or object_.action_bounds is None:
            raise SelectorResolutionError(
                "World YOLO observations are not qualified for spatial taps.",
                object_kind=object_.kind,
            )
        if object_.kind == SpatialObjectKind.CASTLE and (
            object_.name_text is None
            or normalize_ocr_text(object_.name_text) == "MYTERRITORY"
        ):
            raise SelectorResolutionError(
                "World YOLO Castle taps require a current remote player name label.",
                object_kind=object_.kind,
            )
        if observation.frame_ref is None or object_.frame_ref != observation.frame_ref:
            raise SelectorResolutionError(
                "World YOLO spatial target belongs to a different capture frame.",
                object_kind=object_.kind,
            )
        if target != object_.action_point or not object_.action_bounds.contains_point(target):
            raise SelectorResolutionError(
                "World YOLO tap point differs from its reviewed action geometry.",
                object_kind=object_.kind,
            )
        if query is not None and observation.spatial_surface is not None:
            matches = tuple(
                candidate
                for candidate in observation.spatial_surface.objects
                if candidate.source_kind == SpatialObjectSourceKind.YOLO
                and candidate.matches(query)
            )
            if object_ not in matches or (require_unique_query and len(matches) != 1):
                raise SelectorResolutionError(
                    "World YOLO semantic target is absent or ambiguous on the current frame.",
                    object_kind=object_.kind,
                )

    def _sleep_ms(self, milliseconds: int) -> None:
        """Sleeps using millisecond units for action pacing."""

        if milliseconds <= 0:
            return
        performance_wait(
            "action_dispatch_delay",
            milliseconds / 1000.0,
            self.sleep,
            span_name="action.delay",
        )

    def _stable_delay_ms_for(self, action: ActionRequest) -> int:
        """Returns the pacing delay applied after one concrete UI action.

        In human mode the delay is jittered within a tight band around the
        configured value; observation pacing and authored wait durations are
        never jittered.
        """

        if action.timing_profile == ActionTimingProfile.CHAT:
            delay_ms = self.chat_stable_click_delay_ms
        elif action.timing_profile == ActionTimingProfile.WORLD_MAP_MOVEMENT:
            delay_ms = self.world_map_movement_stable_click_delay_ms
        else:
            delay_ms = self.stable_click_delay_ms
        if not self.human_mode:
            return delay_ms
        return max(0, round(delay_ms * self.rng.uniform(*_HUMAN_DELAY_JITTER_RANGE)))

    def _human_key_pause(self) -> None:
        """Pauses briefly between machine-timed key events while human mode is enabled."""

        if self.human_mode:
            self._sleep_ms(round(self.rng.uniform(*_HUMAN_KEY_DELAY_MS_RANGE)))

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
                self._human_key_pause()
                for _ in range(delete_budget):
                    self._record_input_attempt(action, observation)
                    self.session.press_key("KEYCODE_DEL")
                    self._human_key_pause()
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
        self._human_key_pause()
        for _ in range(_delete_budget(field_state.text)):
            self._record_input_attempt(action, observation)
            self.session.press_key("KEYCODE_DEL")
            self._human_key_pause()
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
            self._human_key_pause()

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
