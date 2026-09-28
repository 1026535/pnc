"""One-tap, observed-completion navigation for independently recognized screens."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
import time
from typing import Literal, NoReturn, Protocol

from pnc_automation.app.pnc.domain.action_requests import (
    ActionRequest,
    InputTextAction,
    KeyEventAction,
    SelectChatChannelAction,
    SwipeAction,
    SwipePurpose,
    TapAction,
    TapListEntryAction,
    TapPointAction,
    TapSpatialObjectAction,
    WheelAction,
    resolve_swipe_points_for_action,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
    primary_screen_type_for_home_city_object,
    upgrade_entry_selector_for_screen,
)
from pnc_automation.app.pnc.domain.building_details import BuildingDetailPhase
from pnc_automation.app.pnc.domain.castle_roster_scan import castle_roster_window_signature
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityViewEvidence,
    HomeCityZoomStatus,
)
from pnc_automation.app.pnc.domain.home_city_slots import (
    HomeCitySlotSelector,
    validate_home_city_slot_selector,
)
from pnc_automation.app.pnc.domain.hero_recruit_result import (
    HERO_RECRUIT_RESULT_LAYOUTS,
    HeroRecruitResultPhase,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    DetectedSpatialObject,
    ListEntryKind,
    Observation,
    SpatialObjectSourceKind,
    SpatialSurfaceType,
    VisibleElementSourceKind,
    RowRecognitionStatus,
    castle_entry_matches,
    castle_entry_identity_matches,
)
from pnc_automation.app.pnc.domain.bag import BagTab, bag_tab_selector_id
from pnc_automation.app.pnc.domain.bag_items import (
    TreasureIdentity,
    bag_chest_preview_layout,
    bag_item_identity_key,
    bag_item_inspection_supported,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import (
    RESEARCH_CATEGORY_DEFINITIONS,
    ResearchNodeId,
    research_category_definition,
    research_node_for_title,
)
from pnc_automation.app.pnc.domain.trial_challenge import (
    TrialCategory,
    trial_category_title,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.domain.chat import (
    ChatChannel,
    chat_channel_selector_id,
    count_matching_player_chat_entries,
    parse_chat_message_params,
)
from pnc_automation.app.pnc.domain.mail import (
    MailboxAvailability,
    MailboxType,
    mailbox_category_selector_id,
    mail_thread_row_key,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.home_city_scan import (
    HomeCityCoverageRegion,
    HomeCityScanError,
    HomeCityScanResult,
    HomeCityScanState,
    HomeCityScanStopReason,
    camera_view_center_atlas,
)
from pnc_automation.app.pnc.vision.home_city_camera import (
    HomeCityCameraTarget,
    home_city_camera_target,
    load_home_city_camera_catalog,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    HOME_CITY_HUD_SAFE_MAX_X_RATIO,
    HOME_CITY_HUD_SAFE_MAX_Y_RATIO,
    HOME_CITY_HUD_SAFE_MIN_X_RATIO,
    HOME_CITY_HUD_SAFE_MIN_Y_RATIO,
    home_city_scan_step_budget,
    plan_home_city_camera_step,
)

_MAX_CASTLE_ROSTER_SWIPES = 6
# Consensus fitting is accurate to a few reference pixels; anything at or below
# this delta after a pan means the camera did not measurably move.
_CAMERA_STALL_TOLERANCE_REFERENCE_PX = 12

_RESEARCH_DETAIL_ANCHOR_REASONS = frozenset(
    {
        "visual_anchor:research_tree_node_detail",
        "visual_anchor:research_tree_node_detail_active",
        "visual_anchor:research_tree_node_detail_max",
    }
)


class NavigationActuator(Protocol):
    """The existing device action executor, without its legacy retry orchestration."""

    def execute_action(self, action: ActionRequest, observation: Observation) -> bool: ...


@dataclass(frozen=True, slots=True)
class NavigationEdge:
    """A reviewed, non-spending screen transition; no caller-supplied coordinates."""

    source: ScreenType
    selector: UiElementId
    destinations: frozenset[ScreenType]

    def __post_init__(self) -> None:
        if not self.destinations or ScreenType.UNKNOWN in self.destinations or self.source == ScreenType.UNKNOWN:
            raise ValueError("Navigation edges require known source and destination screens.")
        if self.source in self.destinations:
            raise ValueError("A navigation edge must change screen identity.")


@dataclass(frozen=True, slots=True)
class NavigationPolicy:
    """Passive observation limits, independent of action count."""

    max_observations: int = 8
    max_seconds: float = 45.0
    poll_seconds: float = 0.25
    stable_observations: int = 2
    max_home_zoom_inputs: int = 12
    max_home_pose_observations: int = 3
    # Six measured outward detents plus endpoint confirmation took about 50s
    # in turn013. Home includes that work and acquisition in one lifetime;
    # ordinary screen transitions retain max_seconds.
    max_home_seconds: float = 90.0

    def __post_init__(self) -> None:
        if type(self.max_observations) is not int or type(self.stable_observations) is not int:
            raise ValueError("Observation budgets must be integers.")
        if not 2 <= self.stable_observations <= self.max_observations:
            raise ValueError("Navigation requires at least two stable observations within its budget.")
        if not 0 < self.max_seconds <= 120 or not 0 <= self.poll_seconds <= 2:
            raise ValueError("Invalid navigation time budget.")
        if not 0 < self.max_home_seconds <= 120:
            raise ValueError("Home operation time budget must be within (0, 120] seconds.")
        if any(type(value) is not int or value < 1 for value in (
            self.max_home_zoom_inputs, self.max_home_pose_observations,
        )):
            raise ValueError("Home zoom and pose observation budgets must be positive integers.")


@dataclass(slots=True)
class _HomeCityOperation:
    """One Home request's deadline, input counts and current evidence lifetime."""

    core: NavigationCore
    targets: tuple[HomeCityCameraTarget, ...]
    observe_content: Callable[[str], Observation]
    label: str
    started: float
    state: HomeCityScanState = field(default_factory=HomeCityScanState)
    calibration_id: str | None = None

    def stop(self, reason: HomeCityScanStopReason, message: str) -> NoReturn:
        """Keep ordinary evidence stops typed without swallowing authority errors."""
        result = self.state.result(reason, targets=self.targets)
        self.core.record({
            "event": "home_city_scan_stopped", "operation_id": self.label,
            "reason": reason.value, "gestures": result.gestures,
            "zoom_inputs": result.zoom_inputs,
            "inspected_slots": [slot.slot_index for slot in result.inspected_slots],
            "remaining_slots": [slot.slot_index for slot in result.remaining_slots],
            "remaining_fixed_targets": [target.value for target in result.remaining_fixed_targets],
        })
        raise HomeCityScanError(message, result)

    def check_deadline(self) -> None:
        """Check the same operation clock before and after blocking work."""
        if self.core.clock() - self.started >= self.core.policy.max_home_seconds:
            self.stop(HomeCityScanStopReason.DEADLINE_EXHAUSTED,
                      "Home navigation exhausted its operation deadline; no further input sent.")

    def capture(self, previous: Observation | None, stage: str) -> Observation:
        """Capture fresh content without hiding extra captures in another observer."""
        self.check_deadline()
        if previous is not None:
            self.core.sleep(self.core.policy.poll_seconds)
        self.check_deadline()
        frame = self.observe_content(f"{self.label}_{stage}")
        self.check_deadline()
        if previous is not None:
            if frame.captured_at <= previous.captured_at:
                raise RuntimeError("Home navigation received a stale capture; no further input sent.")
            if previous.frame_ref is not None and frame.frame_ref is not None:
                if (previous.frame_ref.session_id != frame.frame_ref.session_id
                        or previous.frame_ref.session_epoch != frame.frame_ref.session_epoch):
                    raise RuntimeError("Home navigation lost instance/session continuity; no further input sent.")
        _require_home_city_surface(frame)
        self.trace(frame, stage)
        return frame

    def trace(
        self, frame: Observation, stage: str, *, target: HomeCityObjectId | None = None,
        slot: HomeCitySlotSelector | None = None,
    ) -> None:
        """Record typed Home evidence through the existing runtime trace owner."""
        surface = frame.spatial_surface
        view = None if surface is None else surface.home_city_view
        proof = None if surface is None else surface.camera_proof
        self.core.record({
            "event": "home_city_navigation_step", "operation_id": self.label,
            "stage": stage, "artifact": str(frame.artifact_path),
            "target": (target.value if target is not None else
                       self.targets[0].object_id.value if len(self.targets) == 1 else None),
            "slot": None if slot is None else slot.slot_index,
            "zoom_status": None if view is None else view.zoom_status.value,
            "calibration_id": None if view is None else view.calibration_id,
            "zoom": None if proof is None else proof.zoom,
            "translation": None if proof is None else proof.translation,
            "group_ids": [] if proof is None else sorted(proof.matched_group_ids),
            "zoom_inputs": self.state.zoom_inputs, "gestures": self.state.gestures,
            "elapsed_seconds": self.core.clock() - self.started,
        })

    def view(self, frame: Observation) -> HomeCityViewEvidence | None:
        """Reject a view copied from another frame before using its verdict or anchor."""
        _require_home_city_surface(frame)
        image_size = _require_building_image_size(frame)
        view = frame.spatial_surface.home_city_view
        if view is not None and (
            view.frame_size != image_size
            or view.frame_ref != frame.frame_ref
            or view.source_screen not in (None, frame.screen_type)
            or view.source_layout_id not in (None, frame.decision.layout_id)
        ):
            raise RuntimeError("Home view evidence does not belong to the current frame.")
        proof = frame.spatial_surface.camera_proof
        if proof is not None and proof.localized:
            _require_localized_camera(frame)
            if proof.frame_ref != frame.frame_ref:
                raise RuntimeError("Home camera proof does not belong to the current frame.")
        return view

    def endpoint(self, frame: Observation) -> bool:
        """Require the calibrated unsnapped verdict, never the rounded grid zoom alone."""
        view = self.view(frame)
        proof = frame.spatial_surface.camera_proof
        return bool(view is not None and view.zoom_status == HomeCityZoomStatus.AT_ENDPOINT
                    and proof is not None and proof.localized)

    def send(self, action: ActionRequest, frame: Observation) -> None:
        """End the operation on uncertain input while preserving transport exception types."""
        self.check_deadline()
        try:
            executed = self.core.actuator.execute_action(action, frame)
        except Exception as error:
            self.core.record({
                "event": "home_city_input_failed", "operation_id": self.label,
                "input_kind": type(action).__name__, "error_type": type(error).__name__,
            })
            raise
        if not executed:
            self.stop(HomeCityScanStopReason.INPUT_UNCERTAIN,
                      "Home input was not confirmed; no automatic replay or dependent input sent.")
        self.check_deadline()

    def normalize(self) -> Observation:
        """Reach two consecutive current endpoint fits using single outward wheel inputs."""
        current = self.capture(None, "entry")
        passive = 1
        pending_wheel: Observation | None = None
        while True:
            view = self.view(current)
            if view is not None and view.zoom_status == HomeCityZoomStatus.UNSUPPORTED:
                self.stop(HomeCityScanStopReason.ZOOM_UNRESOLVED,
                          "This Home view has no supported endpoint calibration; no wheel input sent.")
            if self.endpoint(current):
                # Two endpoint frames are normalization proof, not a pan settle loop.
                if passive >= self.core.policy.max_home_pose_observations:
                    self.stop(HomeCityScanStopReason.ZOOM_UNRESOLVED,
                              "Endpoint confirmation exceeded its passive observation allowance.")
                after = self.capture(current, "endpoint_confirmation")
                passive += 1
                if self.endpoint(after) and self.view(after).calibration_id == view.calibration_id:
                    self.calibration_id = view.calibration_id
                    return after
                current = after
                continue
            if view is None or view.zoom_status in (
                HomeCityZoomStatus.UNRESOLVED, HomeCityZoomStatus.UNSUPPORTED,
            ):
                # A current positively qualified anchor may normalize an unlocalized
                # start. After input, unresolved scale only permits passive captures.
                if pending_wheel is not None or view is None or view.zoom_anchor is None:
                    if passive >= self.core.policy.max_home_pose_observations:
                        self.stop(HomeCityScanStopReason.ZOOM_UNRESOLVED,
                                  "Current Home zoom could not be qualified within its passive allowance.")
                    current = self.capture(current, "zoom_reacquisition")
                    passive += 1
                    continue
            if pending_wheel is not None:
                before_proof = pending_wheel.spatial_surface.camera_proof
                after_proof = current.spatial_surface.camera_proof
                progressed = (before_proof is not None and after_proof is not None
                              and after_proof.localized
                              and (not before_proof.localized or after_proof.zoom < before_proof.zoom))
                if not progressed:
                    unchanged = (before_proof is not None and after_proof is not None
                                 and before_proof.localized and after_proof.localized
                                 and before_proof.zoom == after_proof.zoom
                                 and before_proof.translation == after_proof.translation
                                 and [(item.landmark_id, item.bounds) for item in before_proof.evidence]
                                 == [(item.landmark_id, item.bounds) for item in after_proof.evidence])
                    if (unchanged and view.zoom_status == HomeCityZoomStatus.NOT_AT_ENDPOINT
                            and passive >= self.core.policy.max_home_pose_observations):
                        self.stop(HomeCityScanStopReason.ZOOM_INEFFECTIVE,
                                  "Wheel input left a positively non-endpoint fixed fit unchanged.")
                    if passive >= self.core.policy.max_home_pose_observations:
                        self.stop(HomeCityScanStopReason.ZOOM_UNRESOLVED,
                                  "Wheel input did not establish measured progress toward the endpoint.")
                    current = self.capture(current, "zoom_progress_reacquisition")
                    passive += 1
                    continue
            if view.zoom_anchor is None:
                self.stop(HomeCityScanStopReason.ZOOM_ANCHOR_UNRESOLVED,
                          "Current frame has no qualified wheel anchor; no input sent.")
            if self.state.zoom_inputs >= self.core.policy.max_home_zoom_inputs:
                self.stop(HomeCityScanStopReason.ZOOM_BUDGET_EXHAUSTED,
                          "Home normalization exhausted its wheel input allowance.")
            self.state.zoom_inputs += 1
            x, y = view.zoom_anchor.point
            self.send(WheelAction(x=x, y=y, vertical_detent=1,
                                  reason="normalize_home_city_widest"), current)
            pending_wheel = current
            current = self.capture(current, "after_wheel")
            passive = 1

    def localized_after(self, before: Observation, stage: str) -> Observation:
        """Return the first fresh endpoint/pose proof, with at most three captures."""
        previous = before
        for index in range(self.core.policy.max_home_pose_observations):
            current = self.capture(previous, f"{stage}_{index}")
            view = self.view(current)
            if view is not None and (
                view.zoom_status == HomeCityZoomStatus.NOT_AT_ENDPOINT
                or (view.calibration_id is not None and view.calibration_id != self.calibration_id)
            ):
                self.stop(HomeCityScanStopReason.ZOOM_CHANGED,
                          "Home scale departed from its normalized endpoint; no further input sent.")
            if self.endpoint(current):
                return current
            previous = current
        self.stop(HomeCityScanStopReason.LOCALIZATION_UNRESOLVED,
                  "Home pose/endpoint could not be reacquired within the passive allowance.")


@dataclass(slots=True)
class NavigationCore:
    """Own completion exactly once; never re-tap or recover an unknown interruption."""

    actuator: NavigationActuator
    observe: Callable[[str], Observation]
    edges: tuple[NavigationEdge, ...]
    policy: NavigationPolicy = field(default_factory=NavigationPolicy)
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    record: Callable[[dict[str, object]], None] = lambda _: None
    observe_ready: Callable[[str], Observation] | None = None
    _sequence: int = field(default=0, init=False)

    def transition(self, edge: NavigationEdge) -> Observation:
        """Reacquire the source, tap once, and require a stable observed destination."""
        if edge not in self.edges:
            raise ValueError("Transition is outside the reviewed navigation graph.")
        self._sequence += 1
        label = f"core_{self._sequence}"
        before = self._observe_source(f"{label}_source")
        if before.blocking_popup or before.screen_type != edge.source:
            raise RuntimeError("Navigation source changed or is interrupted; no action sent.")
        element = before.visible_elements.get(edge.selector)
        if element is None or element.source_kind != VisibleElementSourceKind.TEMPLATE:
            raise RuntimeError("Navigation control lacks current-frame visual evidence; no action sent.")
        self.record({"event": "pending", "source": edge.source.name, "selector": edge.selector.value,
                     "artifact": str(before.artifact_path)})
        action = TapAction(selector_id=edge.selector, reason="replacement_navigation")
        return self._execute_and_confirm(action, before, edge.destinations, label)

    def open_visible_building(
        self,
        target: HomeCityObjectId,
        *,
        observe_content: Callable[[str], Observation],
        on_target_acquired: Callable[[DetectedSpatialObject], None] | None = None,
        require_measured: bool = False,
        home_city_slot: HomeCitySlotSelector | None = None,
    ) -> Observation:
        """Open one observed city object without atlas estimates or camera prediction."""
        _require_reviewed_building_route(target=target, edges=self.edges)
        validate_home_city_slot_selector(target, home_city_slot)
        spec = home_city_camera_target(target)
        operation = self._home_operation(observe_content, () if spec is None else (spec,))
        before = operation.normalize()
        # The old flag cannot waive normalization or authorize an offscreen tour.
        return self._open_reacquired_building(
            target=target, source=before, operation=operation,
            on_target_acquired=on_target_acquired, home_city_slot=home_city_slot,
        )

    def open_building(
        self,
        target: HomeCityObjectId,
        *,
        observe_content: Callable[[str], Observation],
        on_target_acquired: Callable[[DetectedSpatialObject], None] | None = None,
        home_city_slot: HomeCitySlotSelector | None = None,
    ) -> Observation:
        """Acquire a fresh body through the catalog's measured scan contract."""
        _require_reviewed_building_route(target=target, edges=self.edges)
        validate_home_city_slot_selector(target, home_city_slot)
        spec = home_city_camera_target(target)
        operation = self._home_operation(observe_content, () if spec is None else (spec,))
        current = operation.normalize()
        if spec is None:
            # Preserve independently verified direct-visible routes. A missing
            # target qualification cannot authorize the historical blind tour.
            resolved = _resolve_observed_building_target(
                current, target=target, require_measured=True, home_city_slot=home_city_slot,
            )
            if resolved is not None and _is_hud_safe_building_point(
                resolved[1], image_size=current.image_size,
            ):
                return self._open_reacquired_building(
                    target=target, source=current, operation=operation,
                    on_target_acquired=on_target_acquired,
                    home_city_slot=home_city_slot or resolved[0].home_city_slot,
                )
            operation.stop(HomeCityScanStopReason.NO_QUALIFIED_ROUTE,
                           "Building has no qualified offscreen acquisition route; no pan or tap sent.")
        result = self._scan_home_city(
            current=current, operation=operation,
            acquire_target=target, home_city_slot=home_city_slot,
            on_target_acquired=on_target_acquired,
        )
        assert isinstance(result, Observation)
        return result

    def discover_home_city(
        self, *, observe_content: Callable[[str], Observation],
    ) -> HomeCityScanResult:
        """Survey qualified candidates within one budget, without tapping occupants."""
        operation = self._home_operation(observe_content, load_home_city_camera_catalog().targets)
        try:
            current = operation.normalize()
            result = self._scan_home_city(current=current, operation=operation)
        except HomeCityScanError as error:
            return error.result
        assert isinstance(result, HomeCityScanResult)
        return result

    def _home_operation(
        self, observe_content: Callable[[str], Observation],
        targets: tuple[HomeCityCameraTarget, ...],
    ) -> _HomeCityOperation:
        """Allocate one request lifetime; internal reacquisition never starts another."""
        self._sequence += 1
        return _HomeCityOperation(self, targets, observe_content,
                                  f"core_{self._sequence}_home", self.clock())

    def _scan_home_city(
        self,
        *,
        current: Observation,
        operation: _HomeCityOperation,
        acquire_target: HomeCityObjectId | None = None,
        home_city_slot: HomeCitySlotSelector | None = None,
        on_target_acquired: Callable[[DetectedSpatialObject], None] | None = None,
    ) -> Observation | HomeCityScanResult:
        """One request-local measured scanner shared by acquisition and discovery."""
        state = operation.state
        targets = operation.targets
        avoid_direction: str | None = None
        attempted_routes: set[tuple[object, ...]] = set()
        stop = operation.stop
        proof = _require_localized_camera(current)
        state.observe(current, targets=targets, usable_region=_usable_home_region(proof))
        budget = home_city_scan_step_budget()
        while True:
            operation.check_deadline()
            resolved = (None if acquire_target is None else _resolve_observed_building_target(
                current, target=acquire_target, require_measured=True,
                home_city_slot=home_city_slot,
            ))
            if avoid_direction is None and resolved is not None and _is_hud_safe_building_point(
                resolved[1], image_size=current.image_size,
            ):
                return self._open_reacquired_building(
                    target=acquire_target, source=current, operation=operation,
                    on_target_acquired=on_target_acquired,
                    home_city_slot=home_city_slot or resolved[0].home_city_slot,
                )
            proposals = []
            unplanned_candidates = False
            unsafe_candidates = False
            for spec in targets:
                if (acquire_target is None and spec.reference_slot is None
                        and spec.object_id in state.inspected_targets):
                    continue
                candidates = ((resolved[0].home_city_slot,) if resolved is not None
                              else state.candidate_slots(spec, proof, exact=home_city_slot))
                for slot in candidates:
                    try:
                        step = plan_home_city_camera_step(
                            observation=current, target=spec.object_id, home_city_slot=slot,
                            avoid_direction=avoid_direction,
                        )
                    except SelectorResolutionError:
                        unplanned_candidates = True
                        continue
                    if not _qualified_home_pan(step.action, current):
                        unsafe_candidates = True
                        continue
                    proposals.append((step.distance_to_goal(proof), spec.object_id.value, spec, slot, step))
                    break  # Preserve each family's candidate priority.
            if not proposals:
                return stop(
                    HomeCityScanStopReason.NO_SAFE_GESTURE if unsafe_candidates else (
                    HomeCityScanStopReason.NO_PROGRESS if avoid_direction is not None else (
                        HomeCityScanStopReason.NO_QUALIFIED_ROUTE if unplanned_candidates
                        else HomeCityScanStopReason.CANDIDATES_INSPECTED
                    )),
                    "No qualified pan remains after no camera movement or unresolved body evidence; "
                    "remaining slots are unknown, not absent.",
                )
            if state.gestures >= budget:
                return stop(HomeCityScanStopReason.BUDGET_EXHAUSTED,
                            "Measured Home-city scan exhausted its canonical gesture budget.")
            _, _, spec, slot, step = min(proposals, key=lambda item: (item[0], item[1]))
            route = (proof.translation, proof.zoom, spec.object_id, slot, step.action.direction)
            if route in attempted_routes:
                stop(HomeCityScanStopReason.NO_PROGRESS,
                     "Home scan revisited the same pose/candidate/direction; no repeated pan sent.")
            attempted_routes.add(route)
            state.gestures += 1
            operation.trace(current, "pan", target=spec.object_id, slot=slot)
            self.record({
                "event": "pending_building_pan", "target": spec.object_id.value,
                "slot": None if slot is None else slot.slot_index,
                "step": state.gestures, "action": step.action.reason,
                "artifact": None if current.artifact_path is None else str(current.artifact_path),
            })
            operation.send(step.action, current)
            after = operation.localized_after(current, f"after_pan_{state.gestures}")
            after_proof = _require_localized_camera(after)
            discovered = state.observe(
                after, targets=targets, usable_region=_usable_home_region(after_proof),
            )
            if abs(after_proof.zoom - proof.zoom) > 0.02:
                stop(HomeCityScanStopReason.ZOOM_CHANGED,
                     "Home camera scale changed after normalization; no replanning or input sent.")
            else:
                before_center = camera_view_center_atlas(proof)
                after_center = camera_view_center_atlas(after_proof)
                movement = max(abs(a - b) for a, b in zip(before_center, after_center))
                advanced = step.distance_to_goal(proof) - step.distance_to_goal(after_proof) > 12
                if movement > _CAMERA_STALL_TOLERANCE_REFERENCE_PX and (discovered or advanced):
                    state.consecutive_no_progress = 0
                    avoid_direction = None
                else:
                    state.consecutive_no_progress += 1
                    avoid_direction = step.action.direction
                    if state.consecutive_no_progress >= 2:
                        return stop(HomeCityScanStopReason.NO_PROGRESS,
                                    "Two consecutive pans made no camera movement or useful progress.")
            current, proof = after, after_proof

    def _open_reacquired_building(
        self,
        *,
        target: HomeCityObjectId,
        source: Observation,
        operation: _HomeCityOperation,
        on_target_acquired: Callable[[DetectedSpatialObject], None] | None,
        home_city_slot: HomeCitySlotSelector | None = None,
    ) -> Observation:
        """Tap the freshly measured source; recapture after an intervening callback.

        The source is the current endpoint-confirmation or post-pan observation,
        not a stored point. An unconditional extra scan wastes the operation's
        deadline and can replace a usable frame with a transient HUD occlusion.
        Session provenance still rejects a stale source at actual dispatch.
        """
        destination = _require_reviewed_building_route(target=target, edges=self.edges)

        def acquire(before: Observation) -> tuple[Observation, DetectedSpatialObject, tuple[int, int]]:
            operation.check_deadline()
            view = operation.view(before)
            if view is not None and view.zoom_status == HomeCityZoomStatus.NOT_AT_ENDPOINT:
                operation.stop(HomeCityScanStopReason.ZOOM_CHANGED,
                               "Home scale changed before the building tap.")
            if not operation.endpoint(before) or view.calibration_id != operation.calibration_id:
                operation.stop(HomeCityScanStopReason.LOCALIZATION_UNRESOLVED,
                               "Final building frame has no current normalized pose; no tap sent.")
            resolved = _resolve_observed_building_target(
                before, target=target, require_measured=True, home_city_slot=home_city_slot,
            )
            if resolved is None:
                operation.stop(HomeCityScanStopReason.NO_QUALIFIED_ROUTE,
                               "Building is absent or ambiguous on the final frame; no tap sent.")
            body, point = resolved
            if not _is_hud_safe_building_point(point, image_size=before.image_size):
                operation.stop(HomeCityScanStopReason.NO_SAFE_GESTURE,
                               "Final building body overlaps the HUD; no tap sent.")
            return before, body, point

        before, body, point = acquire(source)
        home_city_slot = home_city_slot or body.home_city_slot
        if on_target_acquired is not None:
            on_target_acquired(body)
            before, body, point = acquire(operation.capture(before, "body_after_callback"))
        self.record({"event": "pending_building", "target": target.value,
                     "artifact": str(before.artifact_path), "point": point})
        operation.trace(before, "tap", target=target, slot=home_city_slot)
        return self._execute_and_confirm(
            TapSpatialObjectAction(target_point=point, expected_object=body, exact_geometry=True,
                                   reason="replacement_observed_building"),
            before, frozenset({destination}), operation.label,
            home_operation=operation,
        )

    def open_building_upgrade_detail(
        self,
        target: HomeCityObjectId,
        *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Open the internal upgrade detail of one already-opened building panel.

        The source must be a fresh, CLEAR observation of a building-owned panel
        whose typed detail identifies ``target``. A frame already proved as the
        matching UPGRADE detail returns its fresh content observation with no
        extra tap. Otherwise at most one entry tap on the phase-owned Upgrade
        control is sent, and completion requires a fresh CLEAR same-building
        UPGRADE detail â€” the same ScreenType alone is never sufficient. The
        spending Upgrade control is never used as a navigation entry here.
        """

        if not isinstance(target, HomeCityObjectId):
            raise ValueError("Upgrade detail navigation requires a known HomeCityObjectId target.")
        self._sequence += 1
        label = f"core_{self._sequence}_building_upgrade_detail"
        before = observe_content(f"{label}_source")
        _require_building_panel_for_target(before, target=target)
        if before.building_detail.phase is BuildingDetailPhase.UPGRADE:
            return before
        entry = _building_upgrade_entry_selector(before)
        if entry is None:
            raise RuntimeError("Building primary shows no measured upgrade entry; no tap sent.")
        self.record({"event": "pending_upgrade_detail", "target": target.value,
                     "selector": entry.value, "artifact": str(before.artifact_path)})
        return self._execute_content_and_confirm(
            TapAction(selector_id=entry, reason="open_building_upgrade_detail"),
            before,
            frozenset({before.screen_type, ScreenType.PNC_BUILDING_DETAILS}),
            label,
            observe_content,
            completion_predicate=lambda frame: _building_upgrade_detail_matches(frame, target=target),
        )

    def close_building_upgrade_detail(
        self,
        target: HomeCityObjectId,
        *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Return the qualified Institute upgrade panel to its same-building primary.

        This internal Back changes phase without changing ScreenType. Other
        buildings need their own observed return evidence before using it.
        """
        if target is not HomeCityObjectId.INSTITUTE:
            raise ValueError("Only the Institute internal upgrade return is qualified.")
        self._sequence += 1
        label = f"core_{self._sequence}_building_upgrade_close"
        before = observe_content(f"{label}_source")
        _require_building_panel_for_target(before, target=target)
        if before.building_detail.phase is BuildingDetailPhase.PRIMARY:
            return before
        if not _template_control(before, UiElementId.PNC_BACK_BUTTON_TOP_LEFT):
            raise RuntimeError("Building upgrade detail has no measured Back; no tap sent.")
        return self._execute_content_and_confirm(
            TapAction(selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                      reason="close_building_upgrade_detail"),
            before,
            frozenset({ScreenType.PNC_INSTITUTE}),
            label,
            observe_content,
            completion_predicate=lambda frame: (
                frame.decision.guard is GuardVerdict.CLEAR
                and frame.building_detail is not None
                and frame.building_detail.building_id is target
                and frame.building_detail.phase is BuildingDetailPhase.PRIMARY
            ),
        )

    def open_mailbox(
        self, mailbox: MailboxType, *, observe_content: Callable[[str], Observation],
    ) -> MailboxAvailability:
        """Open one typed mail category after proving its fresh hub availability."""
        if not isinstance(mailbox, MailboxType):
            raise ValueError("Mailbox navigation requires a MailboxType value.")
        self._sequence += 1
        label = f"core_{self._sequence}_mailbox"
        hub = observe_content(f"{label}_hub")
        if hub.blocking_popup or hub.screen_type != ScreenType.PNC_MAIL_HUB:
            raise RuntimeError("Mailbox navigation requires a freshly observed, unblocked mail hub.")
        candidates = tuple(
            entry
            for entry in hub.entries(ListEntryKind.MAILBOX_CATEGORY)
            if entry.metadata.get("mailbox_type") == mailbox.value
        )
        if len(candidates) != 1:
            raise RuntimeError("Requested mailbox category is missing or ambiguous; no tap sent.")
        available = candidates[0].metadata.get("available")
        if type(available) is not bool:
            raise RuntimeError("Requested mailbox category has no typed availability disposition; no tap sent.")
        if not available:
            self.record({"event": "mailbox_unavailable", "mailbox": mailbox.value})
            return MailboxAvailability.UNAVAILABLE
        selector = mailbox_category_selector_id(mailbox)
        edge = next(
            (
                candidate
                for candidate in self.edges
                if candidate.source == ScreenType.PNC_MAIL_HUB and candidate.selector == selector
            ),
            None,
        )
        if edge is None:
            raise ValueError("Requested mailbox category is missing from the reviewed navigation graph.")
        self.transition(edge)
        return MailboxAvailability.AVAILABLE

    def open_mail_thread(
        self, row_key: str, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Open exactly one freshly observed mailbox thread row by its canonical identity."""
        if not isinstance(row_key, str) or row_key.strip() == "":
            raise ValueError("Mail thread navigation requires a non-empty canonical row key.")
        self._sequence += 1
        label = f"core_{self._sequence}_mail_thread"
        before = observe_content(f"{label}_source")
        if before.blocking_popup or before.screen_type != ScreenType.PNC_MAILBOX_LIST:
            raise RuntimeError("Mail thread navigation requires a freshly observed, unblocked mailbox list.")
        candidates = tuple(
            entry
            for entry in before.entries(ListEntryKind.MAIL_THREAD)
            if mail_thread_row_key(entry) == row_key
        )
        if len(candidates) != 1 or candidates[0].action_point is None:
            raise RuntimeError("Mail thread row is absent, ambiguous, or lacks an observed action point; no tap sent.")
        point = candidates[0].action_point
        self.record({"event": "pending_mail_thread", "artifact": str(before.artifact_path), "row_key": row_key})
        return self._execute_and_confirm(
            TapPointAction(x=point[0], y=point[1], reason="replacement_open_mail_thread"),
            before,
            frozenset({ScreenType.PNC_MAIL_THREAD}),
            label,
        )

    def select_chat_channel(
        self, channel: ChatChannel, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Select one observed chat tab and require fresh frames confirming its channel."""

        if not isinstance(channel, ChatChannel):
            raise ValueError("Chat channel selection requires a ChatChannel value.")
        self._sequence += 1
        label = f"core_{self._sequence}_chat_channel"
        before = observe_content(f"{label}_source")
        if before.blocking_popup or before.screen_type != ScreenType.PNC_CHAT:
            raise RuntimeError("Chat channel selection requires a freshly observed, unblocked Chat screen.")
        if before.active_chat_channel == channel:
            return before
        selector = chat_channel_selector_id(channel)
        element = before.visible_elements.get(selector)
        if element is None or element.source_kind != VisibleElementSourceKind.TEMPLATE:
            raise RuntimeError("Chat channel control lacks current-frame visual evidence; no action sent.")
        self.record({"event": "pending_chat_channel", "channel": channel.value,
                     "selector": selector.value, "artifact": str(before.artifact_path)})
        return self._execute_content_and_confirm(
            SelectChatChannelAction(channel=channel, reason="replacement_select_chat_channel"),
            before,
            frozenset({ScreenType.PNC_CHAT}),
            label,
            observe_content,
            completion_predicate=lambda observation: observation.active_chat_channel == channel,
        )

    def select_bag_tab(
        self, tab: BagTab, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Select one measured Bag subtab and require fresh frames confirming it."""

        if not isinstance(tab, BagTab):
            raise ValueError("Bag tab selection requires a BagTab value.")
        self._sequence += 1
        label = f"core_{self._sequence}_bag_tab"
        before = observe_content(f"{label}_source")
        if (
            before.blocking_popup
            or before.screen_type != ScreenType.PNC_BAG
            or before.decision.guard != GuardVerdict.CLEAR
            or before.active_bag_tab is None
        ):
            raise RuntimeError("Bag tab selection requires a freshly observed, unblocked Bag screen.")
        if before.active_bag_tab == tab:
            return before
        selector = bag_tab_selector_id(tab)
        element = before.visible_elements.get(selector)
        if element is None or element.source_kind != VisibleElementSourceKind.TEMPLATE:
            raise RuntimeError("Bag tab control lacks current-frame visual evidence; no action sent.")
        self.record({"event": "pending_bag_tab", "tab": tab.value,
                     "selector": selector.value, "artifact": str(before.artifact_path)})
        return self._execute_content_and_confirm(
            TapAction(selector_id=selector, reason="replacement_select_bag_tab"),
            before,
            frozenset({ScreenType.PNC_BAG}),
            label,
            observe_content,
            completion_predicate=lambda observation: (
                observation.decision.guard == GuardVerdict.CLEAR
                and observation.active_bag_tab == tab
            ),
        )

    def open_bag_chest_preview(
        self, identity: TreasureIdentity, *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Open one qualified Treasure magnifier and require the matching read-only preview.

        Only Treasure identities whose preview destination family is qualified
        (Arena Surprise Chest, Common 1st Victory Chest) are supported; other
        recognized magnifiers stay observation-only and are rejected before any
        tap. Completion requires fresh preview frames whose independently parsed
        title identity agrees with the requested source.
        """

        if not isinstance(identity, TreasureIdentity):
            raise ValueError("Bag chest preview requires a TreasureIdentity.")
        if not bag_item_inspection_supported(identity):
            raise ValueError("Treasure identity is not a qualified inspection target.")
        self._sequence += 1
        label = f"core_{self._sequence}_bag_chest_preview"
        source = observe_content(f"{label}_source")
        if (
            source.screen_type != ScreenType.PNC_BAG or source.blocking_popup
            or source.decision.guard != GuardVerdict.CLEAR
            or source.decision.layout_id != "bag"
            or source.active_bag_tab != BagTab.TREASURE
        ):
            raise RuntimeError("Chest preview requires a freshly observed, unblocked Bag Treasure tab.")
        key = bag_item_identity_key(identity)
        matches = tuple(
            entry for entry in source.entries(ListEntryKind.BAG_ITEM)
            if entry.bag_item_facts is not None
            and entry.bag_item_facts.identity is not None
            and bag_item_identity_key(entry.bag_item_facts.identity) == key
        )
        if (
            len(matches) != 1 or matches[0].row_status != RowRecognitionStatus.COMPLETE
            or matches[0].action_point is None or matches[0].action_bounds is None
            or not matches[0].action_bounds.contains_point(matches[0].action_point)
            or not matches[0].bounds.contains_bounds(matches[0].action_bounds)
        ):
            raise RuntimeError("Qualified chest item is missing, changed or ambiguous; no tap sent.")
        return self._execute_content_and_confirm(
            TapListEntryAction(
                entry_kind=ListEntryKind.BAG_ITEM,
                metadata_key="identity", metadata_value=key,
                use_action_point=True, reason="open_bag_chest_preview",
            ),
            source, frozenset({ScreenType.PNC_BAG_CHEST_PREVIEW}), label, observe_content,
            completion_predicate=lambda frame: _bag_chest_preview_matches(
                frame, identity=identity, layout_id=bag_chest_preview_layout(identity),
            ),
        )

    def acknowledge_hero_recruit_result(
        self, before: Observation, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Acknowledge one retained result through its phase-owned safe control.

        The caller supplies its fresh content observation so it can retain the
        result before input. This route never exposes the paid Recruit control.
        """

        result = before.hero_recruit_result
        if (
            before.screen_type != ScreenType.PNC_HERO_RECRUIT_RESULT
            or before.blocking_popup or before.decision.guard != GuardVerdict.CLEAR
            or result is None or before.frame_ref is None
            or result.frame_ref != before.frame_ref
            or result.source_screen != before.screen_type
            or result.source_layout_id != before.decision.layout_id
            or HERO_RECRUIT_RESULT_LAYOUTS.get(before.decision.layout_id) != result.phase
        ):
            raise RuntimeError("Hero result acknowledgment requires current, qualified phase facts.")
        presentation = result.phase == HeroRecruitResultPhase.HERO_PRESENTATION
        selector = (UiElementId.PNC_HERO_RESULT_CONFIRM if presentation
                    else UiElementId.PNC_HERO_RESULT_CLOSE)
        element = before.visible_elements.get(selector)
        if (
            element is None or element.source_kind != VisibleElementSourceKind.TEMPLATE
            or element.frame_ref != before.frame_ref
            or element.source_layout_id != before.decision.layout_id
            or element.source_screen != before.screen_type
            or element.action_point is None or not element.bounds.contains_point(element.action_point)
        ):
            raise RuntimeError("Hero result acknowledgment lacks its fresh phase-owned control; no tap sent.")
        self._sequence += 1
        label = f"core_{self._sequence}_hero_result_acknowledge"
        destination = (ScreenType.PNC_HERO_RECRUIT_RESULT if presentation else ScreenType.PNC_HERO_HALL)
        self.record({"event": "pending_hero_result_acknowledgment", "phase": result.phase.value,
                     "selector": selector.value, "artifact": str(before.artifact_path)})
        return self._execute_content_and_confirm(
            TapAction(selector_id=selector, reason="acknowledge_hero_recruit_result"),
            before, frozenset({destination}), label, observe_content,
            completion_predicate=lambda frame: (
                frame.decision.guard == GuardVerdict.CLEAR
                and (not presentation or (
                    frame.hero_recruit_result is not None
                    and frame.hero_recruit_result.phase == HeroRecruitResultPhase.FRAGMENT_RESULT
                    and frame.hero_recruit_result.frame_ref == frame.frame_ref
                    and HERO_RECRUIT_RESULT_LAYOUTS.get(frame.decision.layout_id)
                    == HeroRecruitResultPhase.FRAGMENT_RESULT
                ))
            ),
        )

    def send_chat_message(
        self,
        channel: ChatChannel,
        message: str,
        active_castle: CastleIdentity,
        *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Send one validated chat message through fresh observed controls."""

        if (
            not isinstance(channel, ChatChannel)
            or channel not in {ChatChannel.WORLD, ChatChannel.ALLIANCE}
        ):
            raise ValueError("Chat sending requires a supported ChatChannel value.")
        params = parse_chat_message_params(
            {"message": message},
            task_label="send_chat_message",
        )
        if not isinstance(active_castle, CastleIdentity):
            raise ValueError("Chat sending requires a CastleIdentity.")
        self._sequence += 1
        label = f"core_{self._sequence}_chat_send"
        before = observe_content(f"{label}_source")
        _require_chat_send_source(before)
        if before.active_chat_channel == channel:
            requested = before
        else:
            requested = self.select_chat_channel(
                channel,
                observe_content=_guard_chat_empty_selection_observer(observe_content),
            )
            _require_chat_send_source(requested, channel=channel)
        baseline = count_matching_player_chat_entries(
            requested.entries(ListEntryKind.CHAT_MESSAGE),
            message=params.message,
            castle=active_castle,
        )
        send_observe_content = _guard_chat_send_observer(observe_content, channel=channel)
        if _chat_focused_empty_ready(requested, channel=channel):
            focused = requested
        else:
            input_element = requested.get(UiElementId.PNC_CHAT_INPUT_FIELD)
            if input_element is None or input_element.source_kind != VisibleElementSourceKind.TEMPLATE:
                raise RuntimeError(
                    "Chat sending requires current-frame template input and focused-empty controls; no action sent."
                )
            focused = self._execute_content_and_confirm(
                TapAction(
                    selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                    reason="replacement_focus_chat_input",
                ),
                requested,
                frozenset({ScreenType.PNC_CHAT}),
                f"{label}_focus",
                send_observe_content,
                completion_predicate=lambda observation: _chat_focused_empty_ready(
                    observation, channel=channel
                ),
            )
        typed = self._execute_content_and_confirm(
            InputTextAction(
                text=params.message,
                selector_id=None,
                replace_existing=False,
                reason="replacement_type_chat_message",
            ),
            focused,
            frozenset({ScreenType.PNC_CHAT}),
            f"{label}_type",
            send_observe_content,
            completion_predicate=lambda observation: _chat_typed_message_ready(
                observation, params.message, channel=channel
            ),
        )
        return self._execute_content_and_confirm(
            TapAction(
                selector_id=UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON,
                reason="replacement_submit_chat_message",
            ),
            typed,
            frozenset({ScreenType.PNC_CHAT}),
            f"{label}_submit",
            send_observe_content,
            completion_predicate=lambda observation: _chat_receipt_ready(
                observation,
                channel=channel,
                message=params.message,
                active_castle=active_castle,
                baseline=baseline,
            ),
        )

    def scroll_mailbox(
        self, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Scroll one freshly observed mailbox list and require a fresh list frame."""
        self._sequence += 1
        label = f"core_{self._sequence}_mailbox_scroll"
        before = observe_content(f"{label}_source")
        if before.blocking_popup or before.screen_type != ScreenType.PNC_MAILBOX_LIST:
            raise RuntimeError("Mailbox scrolling requires a freshly observed, unblocked mailbox list.")
        return self._execute_content_and_confirm(
            SwipeAction(
                direction="up",
                distance_ratio=0.58,
                duration_ms=450,
                reason="replacement_scroll_mailbox",
            ),
            before,
            frozenset({ScreenType.PNC_MAILBOX_LIST}),
            label,
            observe_content,
        )

    def open_research_category(
        self, category: ResearchCategory, *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Open a measured Institute category and prove its matching tree layout."""

        definition = research_category_definition(category)
        self._sequence += 1
        label = f"core_{self._sequence}_research_category"
        source = observe_content(f"{label}_source")
        if (
            source.screen_type != ScreenType.PNC_INSTITUTE or source.blocking_popup
            or source.decision.guard != GuardVerdict.CLEAR
            or not _template_control(source, definition.entry_selector)
        ):
            raise RuntimeError("Research category entry requires a proved Institute control.")
        return self._execute_content_and_confirm(
            TapAction(selector_id=definition.entry_selector, reason="open_research_category"),
            source, frozenset({ScreenType.PNC_RESEARCH_TREE}), label, observe_content,
            completion_predicate=lambda frame: _proved_research_category(frame) == category,
        )

    def open_research_node(
        self, title: str, category: ResearchCategory, *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Select one fresh category node and prove its matching detail identity.

        Completion requires a fresh detail frame whose typed facts identify the
        requested node; a generic Start template alone never proves the wrong
        node was not opened. Active or locked matching details stay readable,
        while mutation readiness remains owned by the Start boundary.
        """

        if not isinstance(category, ResearchCategory) or not isinstance(title, str) or not title.strip():
            raise ValueError("Research selection requires a typed category and named node.")
        requested_node = research_node_for_title(title, category=category)
        if requested_node is None:
            raise ValueError("Research node title is unsupported in the requested category.")
        self._sequence += 1
        label = f"core_{self._sequence}_research_node"
        source = observe_content(f"{label}_source")
        if _proved_research_category(source) != category:
            raise RuntimeError("Research node selection requires the proved requested category grid.")
        matches = tuple(
            entry for entry in source.entries(ListEntryKind.RESEARCH)
            if entry.research_facts is not None
            and entry.research_facts.node_id == requested_node
            and entry.research_facts.category == category
        )
        if (
            len(matches) != 1 or matches[0].row_status != RowRecognitionStatus.COMPLETE
            or matches[0].action_point is None or matches[0].action_bounds is None
            or not matches[0].action_bounds.contains_point(matches[0].action_point)
            or not matches[0].bounds.contains_bounds(matches[0].action_bounds)
        ):
            raise RuntimeError("Research node is missing, changed or ambiguous; no tap sent.")
        return self._execute_content_and_confirm(
            TapListEntryAction(
                entry_kind=ListEntryKind.RESEARCH, title_text=title,
                metadata_key="category", metadata_value=category.value,
                use_action_point=True, reason="open_research_candidate",
            ),
            source, frozenset({ScreenType.PNC_RESEARCH_TREE}), label, observe_content,
            completion_predicate=lambda frame: _research_detail_matches(
                frame, node_id=requested_node, category=category
            ),
        )

    def scroll_research_tree(
        self, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Swipe one proved category grid once and require the same fresh category.

        The gesture is the single reviewed command captured in
        ``12_research_scroll_result.json``; a failed confirmation never sends
        another swipe.
        """

        self._sequence += 1
        label = f"core_{self._sequence}_research_scroll"
        before = observe_content(f"{label}_source")
        category = _proved_research_category(before)
        if category is None:
            raise RuntimeError("Research tree actions require a proved category grid.")
        return self._execute_content_and_confirm(
            SwipeAction(
                reason="replacement_scroll_research_tree",
                start_x_ratio=0.86,
                start_y_ratio=0.75,
                end_x_ratio=0.86,
                end_y_ratio=0.43,
                duration_ms=700,
            ),
            before,
            frozenset({ScreenType.PNC_RESEARCH_TREE}),
            label,
            observe_content,
            completion_predicate=lambda frame: _proved_research_category(frame) == category,
        )

    def close_research_detail(
        self, *, observe_content: Callable[[str], Observation],
        category: ResearchCategory | None = None,
    ) -> Observation:
        """Send one Android Back from the proved detail and require the tree grid."""

        if category is not None:
            research_category_definition(category)
        self._sequence += 1
        label = f"core_{self._sequence}_research_detail_close"
        before = observe_content(f"{label}_source")
        if (
            before.screen_type != ScreenType.PNC_RESEARCH_TREE or before.blocking_popup
            or before.decision.guard != GuardVerdict.CLEAR
            or not any(
                evidence.reason
                in _RESEARCH_DETAIL_ANCHOR_REASONS
                for evidence in before.decision.evidence
            )
        ):
            raise RuntimeError("Research detail close requires a proved detail frame.")
        return self._execute_content_and_confirm(
            KeyEventAction(key_code="KEYCODE_BACK", reason="replacement_close_research_detail"),
            before,
            frozenset({ScreenType.PNC_RESEARCH_TREE}),
            label,
            observe_content,
            completion_predicate=lambda frame: (
                (returned := _proved_research_category(frame)) is not None
                and (category is None or returned == category)
            ),
        )

    def open_campaign_chapter(
        self, chapter_number: int, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Open one observed unlocked Campaign chapter row and prove its path title."""

        if isinstance(chapter_number, bool) or not isinstance(chapter_number, int) or chapter_number <= 0:
            raise ValueError("Campaign chapter navigation requires a positive integer chapter number.")
        self._sequence += 1
        label = f"core_{self._sequence}_campaign_chapter"
        source = observe_content(f"{label}_source")
        if (
            source.screen_type != ScreenType.PNC_CAMPAIGN_MAP or source.blocking_popup
            or source.decision.guard != GuardVerdict.CLEAR
        ):
            raise RuntimeError("Campaign chapter navigation requires a freshly observed, unblocked Campaign map.")
        matches = tuple(
            entry for entry in source.entries(ListEntryKind.CAMPAIGN_CHAPTER)
            if entry.campaign_node is not None
            and entry.campaign_node.chapter_number == chapter_number
            and entry.campaign_node.locked is False
        )
        if (
            len(matches) != 1 or matches[0].row_status != RowRecognitionStatus.COMPLETE
            or matches[0].action_point is None or matches[0].action_bounds is None
            or not matches[0].action_bounds.contains_point(matches[0].action_point)
            or not matches[0].bounds.contains_bounds(matches[0].action_bounds)
        ):
            raise RuntimeError(
                "Requested Campaign chapter is missing, locked, clipped, unreadable or ambiguous; no tap sent."
            )
        return self._execute_content_and_confirm(
            TapListEntryAction(
                entry_kind=ListEntryKind.CAMPAIGN_CHAPTER,
                metadata_key="chapter_number", metadata_value=chapter_number,
                use_action_point=True, reason="open_campaign_chapter",
            ),
            source, frozenset({ScreenType.PNC_CAMPAIGN_CHAPTER}), label, observe_content,
            completion_predicate=lambda frame: (
                frame.decision.guard == GuardVerdict.CLEAR
                and frame.campaign_chapter is not None
                and frame.campaign_chapter.chapter_number == chapter_number
            ),
        )

    def open_trial_stats(
        self, category: TrialCategory, *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Open one proved category Stats entry and require the matching read-only detail.

        Only Gear Trial's Stats control is a qualified non-spending inspection
        destination; other categories are explicitly unsupported rather than
        force-fit to the Gear detail. Completion requires fresh Applicable
        Stats frames whose bounded footer fact agrees with the selected card.
        """

        if not isinstance(category, TrialCategory):
            raise ValueError("Trial Stats inspection requires a TrialCategory.")
        if category != TrialCategory.GEAR:
            raise ValueError("Only Gear Trial Stats is a qualified inspection target.")
        self._sequence += 1
        label = f"core_{self._sequence}_trial_stats"
        source = observe_content(f"{label}_source")
        if (
            source.screen_type != ScreenType.PNC_TRIAL_CHALLENGE or source.blocking_popup
            or source.decision.guard != GuardVerdict.CLEAR
            or not any(
                evidence.reason == "visual_anchor:trial_challenge_live"
                for evidence in source.decision.evidence
            )
        ):
            raise RuntimeError("Trial Stats inspection requires the proved Trial Challenge list.")
        matches = tuple(
            entry for entry in source.entries(ListEntryKind.TRIAL_CATEGORY)
            if entry.trial_card_facts is not None
            and entry.trial_card_facts.category == category
        )
        if (
            len(matches) != 1 or matches[0].row_status != RowRecognitionStatus.COMPLETE
            or matches[0].action_point is None or matches[0].action_bounds is None
            or not matches[0].action_bounds.contains_point(matches[0].action_point)
            or not matches[0].bounds.contains_bounds(matches[0].action_bounds)
        ):
            raise RuntimeError("Gear Trial Stats entry is missing, changed or ambiguous; no tap sent.")
        return self._execute_content_and_confirm(
            TapListEntryAction(
                entry_kind=ListEntryKind.TRIAL_CATEGORY,
                title_text=trial_category_title(category),
                metadata_key="category", metadata_value=category.value,
                use_action_point=True, reason="open_trial_stats",
            ),
            source, frozenset({ScreenType.PNC_TRIAL_APPLICABLE_STATS}), label, observe_content,
            completion_predicate=lambda frame: _trial_stats_detail_matches(
                frame, category=category
            ),
        )

    def scroll_daily_quest(
        self, *, adjusted: bool, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Perform one existing Daily-list gesture and prove fresh Daily completion."""

        if type(adjusted) is not bool:
            raise ValueError("Daily scrolling requires a boolean adjusted flag.")
        self._sequence += 1
        label = f"core_{self._sequence}_daily_scroll"
        before = observe_content(f"{label}_source")
        if before.screen_type != ScreenType.PNC_QUEST_DAILY or before.blocking_popup:
            raise RuntimeError("Daily scrolling requires an unblocked Daily screen.")
        return self._execute_content_and_confirm(
            SwipeAction(
                reason="daily_scroll_adjusted" if adjusted else "daily_scroll",
                start_x_ratio=0.5, start_y_ratio=0.82 if adjusted else 0.80,
                end_x_ratio=0.5, end_y_ratio=0.49 if adjusted else 0.44,
                duration_ms=420 if adjusted else 350,
            ),
            before, frozenset({ScreenType.PNC_QUEST_DAILY}), label, observe_content,
        )

    def scroll_resource_inventory(
        self, *, upward: bool, adjusted: bool, fine: bool = False,
        observe_content: Callable[[str], Observation],
        confirm_scroll: Callable[[], Observation],
    ) -> Observation:
        """Swipe the selected Resource list once; its scanner owns stable row completion."""

        if any(type(flag) is not bool for flag in (upward, adjusted, fine)):
            raise ValueError("Resource scrolling requires boolean gesture flags.")
        self._sequence += 1
        before = observe_content(f"core_{self._sequence}_resource_scroll_source")
        require_resource_inventory_surface(before)
        low = 0.64 if fine else (0.78 if adjusted else 0.85)
        high = 0.46 if fine else (0.42 if adjusted else 0.32)
        if not self.actuator.execute_action(
            SwipeAction(
                reason=("resource_inventory_focus_scroll" if fine else
                        "resource_inventory_scroll_adjusted" if adjusted else "resource_inventory_scroll"),
                start_x_ratio=0.5, end_x_ratio=0.5,
                start_y_ratio=high if upward else low,
                end_y_ratio=low if upward else high,
                duration_ms=420 if adjusted else 350,
            ), before,
        ):
            raise RuntimeError("Navigation actuator did not execute the Resource scroll.")
        started = self.clock()
        after = confirm_scroll()
        if self.clock() - started >= self.policy.max_seconds:
            raise RuntimeError("Resource scroll completion budget exhausted; the gesture was not repeated.")
        require_resource_inventory_surface(after)
        if after.captured_at <= before.captured_at:
            raise RuntimeError("Resource scroll completion received a stale capture.")
        return after

    def scroll_castle_roster(
        self,
        direction: Literal["up", "down"],
        *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Scroll the Manage Characters roster once without selecting a row."""

        if direction not in {"up", "down"}:
            raise ValueError("Castle-roster scrolling requires direction 'up' or 'down'.")
        self._sequence += 1
        label = f"core_{self._sequence}_castle_roster_scroll"
        before = observe_content(f"{label}_source")
        if before.blocking_popup or before.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            raise RuntimeError(
                "Castle-roster scrolling requires a freshly observed, unblocked Manage Characters screen."
            )
        return self._execute_content_and_confirm(
            SwipeAction(
                direction=direction,
                distance_ratio=0.58,
                duration_ms=450,
                reason="replacement_scan_active_castle",
                start_x_ratio=0.90,
                start_y_ratio=0.82 if direction == "up" else 0.18,
                end_x_ratio=0.90,
                end_y_ratio=0.18 if direction == "up" else 0.82,
            ),
            before,
            frozenset({ScreenType.PNC_CASTLE_SELECTION}),
            label,
            observe_content,
        )

    def select_castle(
        self,
        target: CastleIdentity,
        *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Select one exact observed Manage Characters row with bounded live scanning."""

        if not isinstance(target, CastleIdentity):
            raise ValueError("Castle selection requires a CastleIdentity target.")
        self._sequence += 1
        label = f"core_{self._sequence}_castle_select"
        current = observe_content(f"{label}_source")
        for direction in ("down", "up"):
            seen_windows: set[tuple[tuple[str, str], ...]] = set()
            for step_index in range(_MAX_CASTLE_ROSTER_SWIPES + 1):
                self._require_castle_selection_source(current)
                signature = castle_roster_window_signature(current)
                if signature in seen_windows:
                    break
                seen_windows.add(signature)
                candidates = _matching_castle_entries(current, target)
                if len(candidates) > 1:
                    raise RuntimeError(
                        "Requested castle row is ambiguous; no further gesture or building tap was sent."
                    )
                if candidates:
                    if not castle_entry_matches(candidates[0], target):
                        raise RuntimeError(
                            "Requested castle row has a mismatched level; no further gesture or building tap was sent."
                        )
                    if candidates[0].selected:
                        self.record(
                            {
                                "event": "castle_already_selected",
                                "target": target.castle_name,
                                "kingdom": target.kingdom,
                                "artifact": None if current.artifact_path is None else str(current.artifact_path),
                            }
                        )
                        return current
                    return self._select_visible_castle(
                        target=target,
                        source=current,
                        label=label,
                        observe_content=observe_content,
                    )
                if step_index == _MAX_CASTLE_ROSTER_SWIPES:
                    break
                current = self.scroll_castle_roster(direction, observe_content=observe_content)
        raise RuntimeError(
            "Requested castle row was not found within the bounded roster scan; no further gesture or building tap was sent."
        )

    @staticmethod
    def _require_castle_selection_source(observation: Observation) -> None:
        """Reject an interrupted or unexpected roster frame before scanning it."""

        if observation.blocking_popup or observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            raise RuntimeError(
                "Castle selection requires a freshly observed, unblocked Manage Characters screen."
            )

    def _select_visible_castle(
        self,
        *,
        target: CastleIdentity,
        source: Observation,
        label: str,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Reacquire one target row, then tap its current observed action point once."""

        reacquired = observe_content(f"{label}_reacquire")
        if reacquired.captured_at <= source.captured_at:
            raise RuntimeError("Castle selection reacquired a stale roster frame; no castle selection tap was sent.")
        self._require_castle_selection_source(reacquired)
        candidates = _matching_castle_entries(reacquired, target)
        if len(candidates) != 1:
            raise RuntimeError(
                "Requested castle row changed or became ambiguous; no castle selection tap was sent."
            )
        entry = candidates[0]
        if not castle_entry_matches(entry, target):
            raise RuntimeError(
                "Requested castle row changed to a mismatched level; no castle selection tap was sent."
            )
        if entry.selected:
            self.record(
                {
                    "event": "castle_already_selected",
                    "target": target.castle_name,
                    "kingdom": target.kingdom,
                    "artifact": None if reacquired.artifact_path is None else str(reacquired.artifact_path),
                }
            )
            return reacquired
        if entry.action_point is None:
            raise RuntimeError(
                "Requested castle row has no observed action point; no castle selection tap was sent."
            )
        if (
            not isinstance(entry.action_point, tuple)
            or len(entry.action_point) != 2
            or any(type(value) is not int for value in entry.action_point)
            or not entry.bounds.contains_point(entry.action_point)
        ):
            raise RuntimeError(
                "Requested castle row has a malformed action point; no castle selection tap was sent."
            )
        self.record(
            {
                "event": "pending_castle_select",
                "target": target.castle_name,
                "kingdom": target.kingdom,
                "artifact": None if reacquired.artifact_path is None else str(reacquired.artifact_path),
            }
        )
        return self._execute_content_and_confirm(
            TapListEntryAction(
                entry_kind=ListEntryKind.CASTLE,
                title_text=entry.title_text,
                metadata_key="kingdom",
                metadata_value=target.kingdom,
                selected=False,
                use_action_point=True,
                reason="replacement_select_castle",
            ),
            reacquired,
            frozenset({ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY}),
            label,
            observe_content,
            completion_predicate=lambda observation: (
                observation.screen_type == ScreenType.PNC_HOME_CITY
                or _selected_castle_observed(observation, target=target)
            ),
        )

    def _execute_content_and_confirm(
        self,
        action: ActionRequest,
        before: Observation,
        destinations: frozenset[ScreenType],
        label: str,
        observe_content: Callable[[str], Observation],
        *,
        completion_predicate: Callable[[Observation], bool] | None = None,
    ) -> Observation:
        """Execute one bounded content action without replaying a failed gesture."""
        if not self.actuator.execute_action(action, before):
            raise RuntimeError("Navigation actuator did not execute the content action.")
        return self.confirm_content_after_action(
            before, destinations, label, observe_content,
            completion_predicate=completion_predicate,
        )

    def confirm_content_after_action(
        self, before: Observation, destinations: frozenset[ScreenType], label: str,
        observe_content: Callable[[str], Observation], *,
        completion_predicate: Callable[[Observation], bool] | None = None,
    ) -> Observation:
        """Passively confirm one already dispatched action without issuing another."""

        started = self.clock()
        stable = 0
        previous = ScreenType.UNKNOWN
        previous_completed = False
        captured_at = before.captured_at
        for index in range(self.policy.max_observations):
            if self.clock() - started >= self.policy.max_seconds:
                break
            self.sleep(self.policy.poll_seconds)
            after = observe_content(f"{label}_after_{index}")
            self.record({"event": "observed", "screen": after.screen_type.name,
                         "artifact": str(after.artifact_path), "blocked": after.blocking_popup})
            if after.captured_at <= captured_at:
                raise RuntimeError("Content action received a stale capture; completion is unproven.")
            captured_at = after.captured_at
            if self.clock() - started >= self.policy.max_seconds:
                break
            if after.blocking_popup:
                raise RuntimeError("Content action was interrupted; no recovery action or repeated gesture sent.")
            completed = after.screen_type in destinations and (
                completion_predicate is None or completion_predicate(after)
            )
            if completed:
                stable = stable + 1 if previous_completed and after.screen_type == previous else 1
                if stable >= self.policy.stable_observations:
                    self.record({"event": "confirmed", "screen": after.screen_type.name})
                    return after
            else:
                stable = 0
                if after.screen_type not in {before.screen_type, ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
                    raise RuntimeError("Content action reached an unexpected screen; inspect the recorded frame.")
            previous = after.screen_type
            previous_completed = completed
        raise RuntimeError("Content action completion budget exhausted; the gesture was not repeated.")

    def _execute_and_confirm(
        self, action: ActionRequest, before: Observation,
        destinations: frozenset[ScreenType], label: str,
        *, home_operation: _HomeCityOperation | None = None,
    ) -> Observation:
        """Share the single completion owner for template controls and observed objects."""
        if home_operation is not None:
            home_operation.send(action, before)
        elif not self.actuator.execute_action(action, before):
            raise RuntimeError("Navigation actuator did not execute the transition.")
        started = self.clock()
        stable = 0
        previous = ScreenType.UNKNOWN
        captured_at = before.captured_at
        for index in range(self.policy.max_observations):
            if home_operation is not None:
                home_operation.check_deadline()
            if self.clock() - started >= self.policy.max_seconds:
                break
            self.sleep(self.policy.poll_seconds)
            after = self.observe(f"{label}_after_{index}")
            self.record({"event": "observed", "screen": after.screen_type.name,
                         "artifact": str(after.artifact_path), "blocked": after.blocking_popup})
            if after.captured_at <= captured_at:
                raise RuntimeError("Navigation received a stale capture; completion is unproven.")
            captured_at = after.captured_at
            if home_operation is not None:
                home_operation.check_deadline()
            if self.clock() - started >= self.policy.max_seconds:
                break
            if after.blocking_popup:
                raise RuntimeError("Navigation interrupted; no recovery action or repeated tap sent.")
            if after.screen_type in destinations:
                stable = stable + 1 if after.screen_type == previous else 1
                if stable >= self.policy.stable_observations:
                    self.record({"event": "confirmed", "screen": after.screen_type.name})
                    return after
            else:
                stable = 0
                if after.screen_type not in {before.screen_type, ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
                    if home_operation is not None:
                        home_operation.stop(HomeCityScanStopReason.UNEXPECTED_DESTINATION,
                                            "Building tap reached an unexpected screen; no second tap sent.")
                    raise RuntimeError("Navigation reached an unexpected screen; inspect the recorded frame.")
            previous = after.screen_type
        if home_operation is not None:
            home_operation.stop(HomeCityScanStopReason.NO_PROGRESS,
                                "Building destination was not confirmed within its observation allowance.")
        raise RuntimeError("Navigation completion budget exhausted; the tap was not repeated.")

    def navigate(self, target: ScreenType, *, max_transitions: int = 8) -> Observation:
        """Replan through the reviewed graph after each confirmed transition."""
        if max_transitions < 1 or target == ScreenType.UNKNOWN:
            raise ValueError("Navigation needs a known target and positive transition budget.")
        current = self._observe_source("core_route_source")
        for _ in range(max_transitions):
            if current.blocking_popup or current.screen_type == ScreenType.UNKNOWN:
                raise RuntimeError("Cannot route from an unknown or interrupted screen.")
            if current.screen_type == target:
                return current
            edge = self._first_edge(current.screen_type, target)
            current = self.transition(edge)
        if current.screen_type != target:
            raise RuntimeError("Navigation route budget exhausted.")
        return current

    def _first_edge(self, source: ScreenType, target: ScreenType) -> NavigationEdge:
        queue = deque([(source, None)])
        visited = {source}
        while queue:
            screen, first = queue.popleft()
            for edge in self.edges:
                if edge.source != screen:
                    continue
                for destination in sorted(edge.destinations, key=lambda value: value.name):
                    if destination == target:
                        return first or edge
                    if destination not in visited:
                        visited.add(destination)
                        queue.append((destination, first or edge))
        raise RuntimeError(f"No reviewed route from {source.name} to {target.name}.")

    def _observe_source(self, label: str) -> Observation:
        """Capture a reviewed edge source through the optional loading-ready boundary."""

        if self.observe_ready is not None:
            return self.observe_ready(label)
        return self.observe(label)


def _require_building_panel_for_target(observation: Observation, target: HomeCityObjectId) -> None:
    """Require a CLEAR building-owned panel whose typed detail proves the requested owner and phase."""

    detail = observation.building_detail
    if (
        observation.blocking_popup
        or observation.decision.guard != GuardVerdict.CLEAR
        or detail is None
        or detail.building_id != target
        or detail.phase not in (BuildingDetailPhase.PRIMARY, BuildingDetailPhase.UPGRADE)
    ):
        raise RuntimeError("Building panel is absent, foreign, interrupted, or unphased; no action sent.")


def _building_upgrade_entry_selector(observation: Observation) -> UiElementId | None:
    """Resolve the published primary-panel Upgrade entry control for this frame."""

    named = upgrade_entry_selector_for_screen(observation.screen_type)
    for selector_id in (UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON, named):
        if selector_id is None:
            continue
        element = observation.get(selector_id)
        if element is not None and element.source_kind is VisibleElementSourceKind.TEMPLATE:
            return selector_id
    return None


def _building_upgrade_detail_matches(frame: Observation, *, target: HomeCityObjectId) -> bool:
    """Require a fresh CLEAR typed UPGRADE detail owned by the requested building."""

    detail = frame.building_detail
    return (
        not frame.blocking_popup
        and frame.decision.guard == GuardVerdict.CLEAR
        and detail is not None
        and detail.phase is BuildingDetailPhase.UPGRADE
        and detail.building_id == target
    )


def require_resource_inventory_surface(observation: Observation) -> None:
    """Require a guarded Bag whose typed selection is the measured Resource tab."""

    if (
        observation.screen_type != ScreenType.PNC_BAG
        or observation.blocking_popup
        or observation.decision.guard != GuardVerdict.CLEAR
        or observation.active_bag_tab != BagTab.RESOURCE
        or not _template_control(observation, UiElementId.PNC_BAG_SUBTAB_RESOURCE)
    ):
        raise RuntimeError("Resource inventory requires a guarded Bag with the selected Resource tab.")


def _require_reviewed_building_route(
    *,
    target: HomeCityObjectId,
    edges: tuple[NavigationEdge, ...],
) -> ScreenType:
    """Returns a modeled building endpoint after proving its reviewed return edge exists."""

    destination = primary_screen_type_for_home_city_object(target)
    if destination is None or not any(edge.source == destination for edge in edges):
        raise ValueError("Building has no reviewed return route in this core.")
    return destination


def _require_home_city_surface(observation: Observation) -> None:
    """Requires one fresh, unblocked Home observation with the canonical spatial surface."""

    if (
        observation.screen_type != ScreenType.PNC_HOME_CITY
        or observation.blocking_popup
        or observation.decision.guard != GuardVerdict.CLEAR
        or observation.spatial_surface is None
        or observation.spatial_surface.surface_type != SpatialSurfaceType.HOME_CITY_SURFACE
    ):
        raise RuntimeError("Building navigation requires a freshly observed, unblocked city surface.")


def _selected_castle_observed(observation: Observation, *, target: CastleIdentity) -> bool:
    """Returns whether exactly one observed target row is marked selected."""

    if observation.blocking_popup or observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
        return False
    matches = _matching_castle_entries(observation, target)
    return len(matches) == 1 and matches[0].selected and castle_entry_matches(matches[0], target)


def _matching_castle_entries(
    observation: Observation,
    target: CastleIdentity,
) -> tuple[DetectedListEntry, ...]:
    """Returns all observed castle rows with the exact kingdom/name identity."""

    return tuple(
        entry
        for entry in observation.entries(ListEntryKind.CASTLE)
        if entry.title_text is not None and castle_entry_identity_matches(entry, target)
    )


def _require_localized_camera(observation: Observation) -> HomeCityCameraProof:
    """Requires a fresh localized camera proof bound to the current observation frame."""

    _require_home_city_surface(observation)
    proof = observation.spatial_surface.camera_proof
    if proof is None or not proof.localized or proof.translation is None:
        raise RuntimeError(
            "Home camera could not localize the current frame; no gesture or building tap was sent."
        )
    if proof.frame_size != _require_building_image_size(observation):
        raise RuntimeError("Camera proof dimensions do not match the current frame; no input sent.")
    if (
        observation.frame_ref is not None
        and proof.frame_ref is not None
        and proof.frame_ref != observation.frame_ref
    ):
        raise RuntimeError(
            "Camera proof does not belong to the current observation frame; no gesture or building tap was sent."
        )
    return proof


def _usable_home_region(proof: HomeCityCameraProof) -> HomeCityCoverageRegion:
    """Inverse-project the shared HUD-free band, without camera-bound assumptions."""
    width, height = proof.reference_size
    left, top = proof.project_reference_to_atlas((
        width * HOME_CITY_HUD_SAFE_MIN_X_RATIO, height * HOME_CITY_HUD_SAFE_MIN_Y_RATIO,
    ))
    right, bottom = proof.project_reference_to_atlas((
        width * HOME_CITY_HUD_SAFE_MAX_X_RATIO, height * HOME_CITY_HUD_SAFE_MAX_Y_RATIO,
    ))
    return HomeCityCoverageRegion(left, top, right, bottom)


def _resolve_observed_building_target(
    observation: Observation,
    *,
    target: HomeCityObjectId,
    require_measured: bool = False,
    home_city_slot: HomeCitySlotSelector | None = None,
) -> tuple[DetectedSpatialObject, tuple[int, int]] | None:
    """Finds one exact observed target and validates its point and image dimensions."""

    _require_home_city_surface(observation)
    candidates = [
        item
        for item in observation.spatial_surface.objects
        if home_city_object_id_from_metadata(item.metadata) == target
        and (home_city_slot is None or item.home_city_slot == home_city_slot)
    ]
    if require_measured or home_city_slot is not None:
        candidates = [
            item
            for item in candidates
            if item.source_kind == SpatialObjectSourceKind.TEMPLATE
        ]
    image_size = _require_building_image_size(observation)
    for candidate in candidates:
        validate_home_city_slot_selector(target, candidate.home_city_slot)
    if len(candidates) > 1:
        # Distinct measured slot identities are repeated instances, not rival
        # detections of one instance. Prefer an already safe body, then stable
        # slot order. Untagged or duplicate-slot evidence remains ambiguous.
        slots = [item.home_city_slot for item in candidates]
        if (
            any(slot is None for slot in slots)
            or len(set(slots)) != len(slots)
            or any(item.source_kind != SpatialObjectSourceKind.TEMPLATE for item in candidates)
        ):
            raise RuntimeError("Building is absent or ambiguous; no further gesture or building tap was sent.")
        candidates.sort(key=lambda item: (
            not (item.action_point is not None and _is_hud_safe_building_point(
                item.action_point, image_size=image_size,
            )),
            item.home_city_slot.slot_index,
        ))
    if not candidates:
        return None
    candidate = candidates[0]
    if candidate.action_point is None:
        raise RuntimeError("Observed building target has no action point; no further gesture or building tap was sent.")
    if (
        not isinstance(candidate.action_point, tuple)
        or len(candidate.action_point) != 2
        or any(type(value) is not int for value in candidate.action_point)
        or not (0 <= candidate.action_point[0] < image_size[0])
        or not (0 <= candidate.action_point[1] < image_size[1])
    ):
        raise RuntimeError(
            "Observed building target has a malformed or out-of-image action point; "
            "no further gesture or building tap was sent."
        )
    return candidate, candidate.action_point


def _require_building_image_size(observation: Observation) -> tuple[int, int]:
    """Returns positive screenshot dimensions required for observed building validation."""

    image_size = observation.image_size
    if (
        not isinstance(image_size, tuple)
        or len(image_size) != 2
        or any(type(value) is not int or value <= 0 for value in image_size)
    ):
        raise RuntimeError(
            "Building observation has no valid image dimensions; "
            "no further gesture or building tap was sent."
        )
    return image_size


def _is_hud_safe_building_point(
    point: tuple[int, int],
    *,
    image_size: tuple[int, int] | None,
) -> bool:
    """Returns whether one observed point stays inside the shared HUD-safe tap band."""

    width, height = image_size if image_size is not None else (0, 0)
    if width <= 0 or height <= 0:
        raise RuntimeError("Building observation has no valid image dimensions; no building tap was sent.")
    return (
        width * HOME_CITY_HUD_SAFE_MIN_X_RATIO <= point[0] <= width * HOME_CITY_HUD_SAFE_MAX_X_RATIO
        and height * HOME_CITY_HUD_SAFE_MIN_Y_RATIO <= point[1] <= height * HOME_CITY_HUD_SAFE_MAX_Y_RATIO
    )


def _qualified_home_pan(action: SwipeAction, observation: Observation) -> bool:
    """Require the planner's independent lane and explicit exact native geometry."""
    if (action.purpose is not SwipePurpose.HOME_CITY_CAMERA
            or action.exact_geometry is not True or action.safe_bounds is None
            or any(value is None for value in (
                action.start_x_ratio, action.start_y_ratio,
                action.end_x_ratio, action.end_y_ratio,
            ))):
        return False
    width, height = _require_building_image_size(observation)
    try:
        x1, y1, x2, y2 = resolve_swipe_points_for_action(width=width, height=height, action=action)
    except SelectorResolutionError:
        return False
    return (action.safe_bounds.contains_point((x1, y1))
            and action.safe_bounds.contains_point((x2, y2))
            # The measured gesture lane owns HUD exclusion. The conservative
            # building-tap band is not the lane (the qualified ground strip
            # extends below that band), and cannot substitute for its proof.
            and 0 <= x1 < width and 0 <= x2 < width
            and 0 <= y1 < height and 0 <= y2 < height
            and (x1, y1) != (x2, y2))


def _template_control(observation: Observation, selector_id: UiElementId) -> bool:
    """Return whether one selector was matched by a current-frame template."""

    element = observation.get(selector_id)
    return element is not None and element.source_kind == VisibleElementSourceKind.TEMPLATE


def _proved_research_category(observation: Observation) -> ResearchCategory | None:
    """Resolve a clear grid from its qualified visual evidence and layout."""

    if (
        observation.screen_type != ScreenType.PNC_RESEARCH_TREE or observation.blocking_popup
        or observation.decision.guard != GuardVerdict.CLEAR
    ):
        return None
    matches = tuple(
        item.category for item in RESEARCH_CATEGORY_DEFINITIONS
        if (observation.decision.layout_id is None
            or observation.decision.layout_id == item.layout_id)
        and any(evidence.reason == f"visual_anchor:{item.layout_id}"
                for evidence in observation.decision.evidence)
    )
    return matches[0] if len(matches) == 1 else None


def _research_detail_matches(
    frame: Observation,
    *,
    node_id: ResearchNodeId,
    category: ResearchCategory,
) -> bool:
    """Prove the fresh detail belongs to the requested node and category.

    The detail's typed identity must resolve to the requested node. When the
    panel displays its own category it must agree; when the panel hides it,
    the freshly proved source category plus the direct single-tap transition
    supply the navigation context instead.
    """

    detail = frame.research_detail
    return (
        frame.decision.guard == GuardVerdict.CLEAR
        and any(
            evidence.reason in _RESEARCH_DETAIL_ANCHOR_REASONS
            for evidence in frame.decision.evidence
        )
        and detail is not None
        and detail.node_id == node_id
        and (detail.category is None or detail.category == category)
    )


def _trial_stats_detail_matches(frame: Observation, *, category: TrialCategory) -> bool:
    """Prove the fresh Applicable Stats detail belongs to the requested category.

    The footer's typed category must agree with the selected source card; an
    unreadable footer never confirms the wrong destination was not opened.
    """

    detail = frame.trial_stats_detail
    return (
        frame.decision.guard == GuardVerdict.CLEAR
        and any(
            evidence.reason == "visual_anchor:trial_gear_applicable_stats"
            for evidence in frame.decision.evidence
        )
        and detail is not None
        and detail.category == category
    )


def _bag_chest_preview_matches(
    frame: Observation, *, identity: TreasureIdentity, layout_id: str | None,
) -> bool:
    """Prove the fresh chest preview belongs to the requested Treasure identity.

    The qualified layout and the independently parsed title identity must both
    agree; an unreadable title never confirms the wrong popup was not opened.
    """

    preview = frame.bag_preview
    return (
        frame.decision.guard == GuardVerdict.CLEAR
        and layout_id is not None
        and frame.decision.layout_id == layout_id
        and preview is not None
        and preview.source_identity == identity
    )


def _require_chat_send_source(
    observation: Observation,
    *,
    channel: ChatChannel | None = None,
) -> None:
    """Require an unblocked Chat frame with explicit empty-draft template evidence."""

    supported_active_channel = observation.active_chat_channel in {
        ChatChannel.WORLD,
        ChatChannel.ALLIANCE,
    }
    if (
        observation.screen_type != ScreenType.PNC_CHAT
        or observation.blocking_popup
        or not supported_active_channel
        or (channel is not None and observation.active_chat_channel != channel)
    ):
        channel_text = "" if channel is None else f" {channel.value}"
        raise RuntimeError(
            f"Chat sending requires a fresh, unblocked{channel_text} Chat frame; no action sent."
        )
    if observation.chat_draft_empty is not True:
        raise RuntimeError("Chat draft is not explicitly empty; no focus or text action sent.")
    if not (
        _template_control(observation, UiElementId.PNC_CHAT_INPUT_FIELD)
        or _template_control(observation, UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT)
    ):
        raise RuntimeError("Chat draft emptiness lacks positive template evidence; no action sent.")


def _guard_chat_send_observer(
    observe_content: Callable[[str], Observation],
    *,
    channel: ChatChannel,
) -> Callable[[str], Observation]:
    """Reject interruption and channel drift before send completion can authorize another action."""

    def observe(label: str) -> Observation:
        observation = observe_content(label)
        if observation.screen_type in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
            raise RuntimeError("Chat send observed an unknown or loading frame; completion is unproven.")
        if observation.blocking_popup:
            raise RuntimeError("Chat send was interrupted by a blocking popup; no repeated action sent.")
        if observation.screen_type != ScreenType.PNC_CHAT or observation.active_chat_channel != channel:
            raise RuntimeError("Chat send observed the wrong channel or screen; completion is unproven.")
        return observation

    return observe


def _guard_chat_empty_selection_observer(
    observe_content: Callable[[str], Observation],
) -> Callable[[str], Observation]:
    """Keep every channel-selection frame within the pre-switch empty-draft contract."""

    def observe(label: str) -> Observation:
        observation = observe_content(label)
        _require_chat_send_source(observation)
        return observation

    return observe


def _chat_focused_empty_ready(observation: Observation, *, channel: ChatChannel) -> bool:
    """Require focused placeholder, gold return control, channel, and OCR empty state."""

    return (
        observation.screen_type == ScreenType.PNC_CHAT
        and not observation.blocking_popup
        and observation.active_chat_channel == channel
        and observation.chat_draft_empty is True
        and _template_control(observation, UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT)
        and _template_control(observation, UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON)
    )


def _chat_typed_message_ready(observation: Observation, message: str, *, channel: ChatChannel) -> bool:
    """Require exact OCR draft text and the still-visible focused send control."""

    return (
        observation.screen_type == ScreenType.PNC_CHAT
        and not observation.blocking_popup
        and observation.active_chat_channel == channel
        and observation.chat_draft_empty is False
        and observation.chat_draft_text == message
        and _template_control(observation, UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON)
    )


def _chat_receipt_ready(
    observation: Observation,
    *,
    channel: ChatChannel,
    message: str,
    active_castle: CastleIdentity,
    baseline: int,
) -> bool:
    """Require a fresh empty draft and a strictly increased canonical own-row count."""

    if (
        observation.screen_type != ScreenType.PNC_CHAT
        or observation.blocking_popup
        or observation.active_chat_channel != channel
        or observation.chat_draft_empty is not True
    ):
        return False
    receipt_count = count_matching_player_chat_entries(
        observation.entries(ListEntryKind.CHAT_MESSAGE),
        message=message,
        castle=active_castle,
    )
    return receipt_count > baseline


def reviewed_navigation_edges() -> tuple[NavigationEdge, ...]:
    """Initial graph derived from September 2026 active-castle navigation evidence.

    Deliberately excludes purchases, claims, recruitment, castle selection, and
    camera coordinates. Legacy workflows remain outside this migration boundary.
    """
    screen = ScreenType
    selector = UiElementId
    quest = frozenset({screen.PNC_QUEST_MAIN, screen.PNC_QUEST_DAILY})
    edges = [
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_HOME_WORLD_SWITCH, frozenset({screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_HOME_NAV, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_CAMPAIGN_MAP, selector.PNC_CAMPAIGN_HOME_PORTAL, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_CAMPAIGN_CHAPTER, selector.PNC_CAMPAIGN_BACK_BUTTON, frozenset({screen.PNC_CAMPAIGN_MAP})),
        NavigationEdge(screen.PNC_CAMPAIGN_STAGE, selector.PNC_CAMPAIGN_CLOSE_BUTTON, frozenset({screen.PNC_CAMPAIGN_CHAPTER})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_QUEST, quest),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_BAG, frozenset({screen.PNC_BAG})),
        NavigationEdge(screen.PNC_BAG_CHEST_PREVIEW, selector.PNC_BAG_CHEST_PREVIEW_CLOSE, frozenset({screen.PNC_BAG})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_MAIL, frozenset({screen.PNC_MAIL_HUB})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_CHAT_SHORTCUT, frozenset({screen.PNC_CHAT})),
        NavigationEdge(
            screen.PNC_CHAT,
            selector.PNC_BACK_BUTTON_TOP_LEFT,
            frozenset({screen.PNC_HOME_CITY, screen.PNC_WORLD_MAP, screen.PNC_MORE_MENU}),
        ),
        NavigationEdge(screen.PNC_MAIL_HUB, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_MAIL_HUB, selector.PNC_MAIL_ROW_PLAYER_MAIL, frozenset({screen.PNC_MAILBOX_LIST})),
        NavigationEdge(screen.PNC_MAIL_HUB, selector.PNC_MAIL_ROW_ALLIANCE_MAIL, frozenset({screen.PNC_MAILBOX_LIST})),
        NavigationEdge(screen.PNC_MAILBOX_LIST, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_MAIL_HUB})),
        NavigationEdge(screen.PNC_MAIL_THREAD, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_MAILBOX_LIST})),
        NavigationEdge(screen.PNC_QUEST_MAIN, selector.PNC_QUEST_TAB_DAILY, frozenset({screen.PNC_QUEST_DAILY})),
        NavigationEdge(screen.PNC_QUEST_DAILY, selector.PNC_QUEST_TAB_MAIN, frozenset({screen.PNC_QUEST_MAIN})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_MORE, frozenset({screen.PNC_MORE_MENU})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_BOTTOM_NAV_MORE, frozenset({screen.PNC_MORE_MENU})),
        NavigationEdge(screen.PNC_MORE_MENU, selector.PNC_MORE_SETTINGS, frozenset({screen.PNC_SETTINGS})),
        NavigationEdge(screen.PNC_MORE_MENU, selector.PNC_MORE_RANK, frozenset({screen.PNC_RANK_HUB})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_MORE_MANAGE_CHAR, frozenset({screen.PNC_CASTLE_SELECTION})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_SETTINGS_RANK, frozenset({screen.PNC_RANK_HUB})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_SETTINGS_PREFERENCES, frozenset({screen.PNC_SETTINGS_PREFERENCES})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_SETTINGS_NOTIFICATIONS, frozenset({screen.PNC_NOTIFICATIONS})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_HOME_CITY, screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_RANK_HUB, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_SETTINGS, screen.PNC_HOME_CITY, screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_HOME_RESEARCH_BUTTON, frozenset({screen.PNC_RESEARCH_QUEUE})),
        NavigationEdge(screen.PNC_RESEARCH_QUEUE, selector.PNC_RESEARCH_QUEUE_CLOSE, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_RESEARCH_QUEUE, selector.PNC_RESEARCH_QUEUE_GO, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_INSTITUTE, selector.PNC_INSTITUTE_DEVELOPMENT_BUTTON, frozenset({screen.PNC_RESEARCH_TREE})),
        NavigationEdge(screen.PNC_RESEARCH_TREE, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_INSTITUTE})),
        NavigationEdge(screen.PNC_TRIAL_APPLICABLE_STATS, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_TRIAL_CHALLENGE})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_COORDINATE_BAR, frozenset({screen.PNC_WORLD_COORDINATE_DIALOG})),
        NavigationEdge(screen.PNC_WORLD_COORDINATE_DIALOG, selector.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON, frozenset({screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_EXPAND_BUTTON, frozenset({screen.PNC_WORLD_MAP_OVERVIEW})),
        NavigationEdge(screen.PNC_WORLD_MAP_OVERVIEW, selector.PNC_WORLD_OVERVIEW_CLOSE_BUTTON, frozenset({screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_WORLD_MAP_OVERVIEW, selector.PNC_WORLD_OVERVIEW_WORLD_ICON, frozenset({screen.PNC_WORLD_KINGDOM_LIST})),
        NavigationEdge(screen.PNC_WORLD_KINGDOM_LIST, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_WORLD_MAP_OVERVIEW})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_HUD_TOGGLE, frozenset({screen.PNC_WORLD_MAP_EXPANDED})),
        NavigationEdge(screen.PNC_WORLD_MAP_EXPANDED, selector.PNC_WORLD_HUD_TOGGLE, frozenset({screen.PNC_WORLD_MAP})),
        # PW owns these measured inner controls; Home acquisition remains
        # with the shared building-navigation owner.
        NavigationEdge(screen.PNC_ILLUSORY_BEAST_MANOR, selector.PNC_ILLUSORY_BEAST_MANOR_PET_WORKSHOP_BUTTON, frozenset({screen.PNC_PET_WORKSHOP})),
        NavigationEdge(screen.PNC_PET_WORKSHOP, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_ILLUSORY_BEAST_MANOR})),
        NavigationEdge(screen.PNC_ILLUSORY_BEAST_MANOR, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_HOME_CITY})),
    ]
    # Back returns to the actual parent. Rank and the Settings hub can have
    # different parents; their measured destination is used for replanning.
    for source in (screen.PNC_CASTLE_SELECTION, screen.PNC_SETTINGS_PREFERENCES, screen.PNC_NOTIFICATIONS):
        edges.append(NavigationEdge(source, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_SETTINGS})))
    for source in (
        *sorted(quest, key=lambda value: value.name), screen.PNC_BAG,
        screen.PNC_INSTITUTE, screen.PNC_GODDESS_STATUE, screen.PNC_HALL_OF_WAR,
        screen.PNC_SACRED_TREE, screen.PNC_VERSUS_CENTER, screen.PNC_TRIAL_CHALLENGE,
        screen.PNC_WAREHOUSE, screen.PNC_HERO_HALL, screen.PNC_CASTLE,
        screen.PNC_BLACKSMITH, screen.PNC_WALL,
        # Only the captured voucher_mall producer qualifies this entry's
        # measured Back; other store contexts remain unreviewed.
        screen.PNC_CASH_MALL,
    ):
        edges.append(NavigationEdge(source, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_HOME_CITY})))
    return tuple(edges)
