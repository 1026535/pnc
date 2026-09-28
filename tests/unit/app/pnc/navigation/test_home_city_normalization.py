"""Deterministic operation-lifetime checks for widest-first Home navigation."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pnc_automation.app.automation.engine.core_runtime import _sanitize_trace_entry
from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore, NavigationPolicy, _HomeCityOperation, reviewed_navigation_edges,
)
from pnc_automation.app.pnc.domain.action_requests import (
    SwipeAction, SwipePurpose, TapSpatialObjectAction, WheelAction,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof, HomeCityCameraStatus, HomeCityViewEvidence,
    HomeCityZoomAnchor, HomeCityZoomStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.home_city_scan import HomeCityScanError, HomeCityScanStopReason
from pnc_automation.app.pnc.navigation.spatial_navigation import HomeCityCameraPanStep
from pnc_automation.app.pnc.vision.home_city_camera import home_city_camera_target
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds
from tests.unit.app.pnc.navigation.test_navigation_core import (
    Actuator, camera_home_frame, mail_frame as frame, measured_building_object,
)

_NOW = datetime(2026, 9, 28, tzinfo=UTC)
_TARGET = HomeCityObjectId.ILLUSORY_BEAST_MANOR
_BODY = measured_building_object(
    _TARGET, bounds=Bounds(400, 700, 100, 200), action_point=(450, 800),
    action_bounds=Bounds(430, 780, 40, 40),
)


def home(index, *, status=HomeCityZoomStatus.AT_ENDPOINT, zoom=.75,
         objects=(), anchor=True, localized=True, translation=(-288, 44)):
    """Publish a deliberately controlled producer verdict on a distinct frame."""
    result = camera_home_frame(
        objects, image_size=(900, 1600), zoom=zoom, translation=translation,
        captured_at=_NOW + timedelta(seconds=index),
    )
    proof = result.spatial_surface.camera_proof if localized else HomeCityCameraProof(
        HomeCityCameraStatus.INSUFFICIENT, "test_missing", frame_size=(900, 1600),
    )
    view = HomeCityViewEvidence(
        status, "test", "test_endpoint", HomeCityZoomAnchor(
            (450, 500), Bounds(430, 480, 40, 40), "test_wheel_only",
        ) if anchor else None, (900, 1600),
    )
    return replace(result, spatial_surface=replace(
        result.spatial_surface, camera_proof=proof, home_city_view=view,
    ))


def operation(frames, *, policy=None, actuator=None, clock=lambda: 0.0):
    """Construct the real operation over a finite passive observation sequence."""
    observations = iter(frames)
    core = NavigationCore(
        actuator or Actuator(), lambda _: next(observations), reviewed_navigation_edges(),
        policy=policy or NavigationPolicy(), sleep=lambda _: None, clock=clock,
    )
    return _HomeCityOperation(core, (home_city_camera_target(_TARGET),),
                              core.observe, "test_home", clock())


class HomeNormalizationTests(unittest.TestCase):
    def test_endpoint_needs_two_fresh_frames_without_wheel(self):
        op = operation([home(0), home(1)])
        self.assertEqual(home(1), op.normalize())
        self.assertEqual([], op.core.actuator.actions)
        self.assertEqual(0, op.state.zoom_inputs)

    def test_closer_view_uses_one_outward_detent_and_fresh_anchor_per_step(self):
        op = operation([
            home(0, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, zoom=1),
            home(1, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, zoom=.9),
            home(2), home(3),
        ])
        self.assertEqual(home(3), op.normalize())
        self.assertEqual([1, 1], [action.vertical_detent for action in op.core.actuator.actions])
        self.assertEqual(2, op.state.zoom_inputs)

    def test_unchanged_nonendpoint_is_not_endpoint_proof(self):
        op = operation([home(i, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, zoom=1) for i in range(4)])
        with self.assertRaises(HomeCityScanError) as error:
            op.normalize()
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.ZOOM_INEFFECTIVE)
        self.assertEqual(1, error.exception.result.zoom_inputs)

    def test_missing_anchor_never_dispatches(self):
        op = operation([home(0, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, anchor=False)])
        with self.assertRaises(HomeCityScanError) as error:
            op.normalize()
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.ZOOM_ANCHOR_UNRESOLVED)
        self.assertEqual([], op.core.actuator.actions)

    def test_unsupported_view_does_not_wheel_even_with_anchor(self):
        op = operation([home(0, status=HomeCityZoomStatus.UNSUPPORTED)])
        with self.assertRaises(HomeCityScanError) as error:
            op.normalize()
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.ZOOM_UNRESOLVED)
        self.assertEqual([], op.core.actuator.actions)

    def test_unresolved_postwheel_cannot_be_replayed(self):
        op = operation([home(0, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, zoom=1)] + [
            home(i, status=HomeCityZoomStatus.UNRESOLVED, localized=False) for i in (1, 2, 3)
        ])
        with self.assertRaises(HomeCityScanError) as error:
            op.normalize()
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.ZOOM_UNRESOLVED)
        self.assertEqual(1, len(op.core.actuator.actions))

    def test_uncertain_input_consumes_allowance_and_never_retries(self):
        actuator = SimpleNamespace(execute_action=lambda action, observation: False)
        op = operation([home(0, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, zoom=1)], actuator=actuator)
        with self.assertRaises(HomeCityScanError) as error:
            op.normalize()
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.INPUT_UNCERTAIN)
        self.assertEqual(1, error.exception.result.zoom_inputs)

    def test_transport_exception_keeps_original_type(self):
        def fail(*_):
            raise ConnectionError("test_transport")
        op = operation([home(0, status=HomeCityZoomStatus.NOT_AT_ENDPOINT)],
                       actuator=SimpleNamespace(execute_action=fail))
        with self.assertRaises(ConnectionError):
            op.normalize()
        self.assertEqual(1, op.state.zoom_inputs)

    def test_single_wheel_budget_does_not_reset_on_progress(self):
        op = operation([
            home(0, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, zoom=1),
            home(1, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, zoom=.9),
        ], policy=NavigationPolicy(max_home_zoom_inputs=1))
        with self.assertRaises(HomeCityScanError) as error:
            op.normalize()
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.ZOOM_BUDGET_EXHAUSTED)
        self.assertEqual(1, len(op.core.actuator.actions))

    def test_stale_endpoint_confirmation_is_a_hard_error(self):
        op = operation([home(0), home(0)])
        with self.assertRaisesRegex(RuntimeError, "stale capture"):
            op.normalize()

    def test_view_from_another_frame_is_a_hard_error(self):
        stale = home(0)
        view = replace(stale.spatial_surface.home_city_view,
                       frame_ref=FrameRef("foreign", 1, 1, 0, _NOW))
        stale = replace(stale, spatial_surface=replace(stale.spatial_surface, home_city_view=view))
        op = operation([stale])
        with self.assertRaisesRegex(RuntimeError, "current frame"):
            op.normalize()

    def test_blocking_observation_cannot_overrun_operation_deadline(self):
        elapsed = [0.0]
        op = operation([], policy=NavigationPolicy(max_home_seconds=45), clock=lambda: elapsed[0])
        def capture(_):
            elapsed[0] = 46.0
            return home(1)
        op.observe_content = capture
        with self.assertRaises(HomeCityScanError) as error:
            op.normalize()
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.DEADLINE_EXHAUSTED)
        self.assertEqual([], op.core.actuator.actions)

    def test_measured_six_detent_normalization_fits_default_home_lifetime(self):
        elapsed = [0.0]
        op = operation([], clock=lambda: elapsed[0])
        frames = iter([
            home(i, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, zoom=zoom)
            for i, zoom in enumerate((1.0, .94, .88, .83, .79, .75))
        ] + [home(6, objects=(_BODY,)), home(7, objects=(_BODY,))])

        def capture(_):
            elapsed[0] += 6.25
            return next(frames)

        op.observe_content = capture
        normalized = op.normalize()
        self.assertEqual(home(7, objects=(_BODY,)), normalized)
        self.assertEqual(50, elapsed[0])
        self.assertEqual(6, op.state.zoom_inputs)
        self.assertEqual(6, len(op.core.actuator.actions))
        self.assertEqual(90, op.core.policy.max_home_seconds)
        self.assertEqual(45, op.core.policy.max_seconds)

        arrivals = iter((8, 9))

        def destination(_):
            elapsed[0] += 1
            return frame(ScreenType.PNC_ILLUSORY_BEAST_MANOR,
                         captured_at=home(next(arrivals)).captured_at)

        op.core.observe = destination
        result = op.core._open_reacquired_building(
            target=_TARGET, source=normalized, operation=op, on_target_acquired=None,
        )
        self.assertIs(result.screen_type, ScreenType.PNC_ILLUSORY_BEAST_MANOR)
        self.assertEqual(52, elapsed[0])
        self.assertEqual(7, len(op.core.actuator.actions))

        # A later phase shares the original start. It cannot replenish the
        # consumed normalization time merely because a pan or tap comes next.
        elapsed[0] = 90
        with self.assertRaises(HomeCityScanError) as error:
            op.localized_after(normalized, "later_pan")
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.DEADLINE_EXHAUSTED)
        self.assertEqual(6, error.exception.result.zoom_inputs)
        self.assertEqual(7, len(op.core.actuator.actions))

    def test_home_lifetime_requires_a_positive_bounded_budget(self):
        for seconds in (0, -1, 121):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                NavigationPolicy(max_home_seconds=seconds)

    def test_postpan_uses_first_current_pose_without_two_frame_delay(self):
        op = operation([home(1, translation=(-288, 100))])
        op.calibration_id = "test_endpoint"
        self.assertEqual((-288, 100), op.localized_after(home(0), "pan").spatial_surface.camera_proof.translation)

    def test_postpan_passive_reacquisition_is_bounded(self):
        op = operation([home(i, status=HomeCityZoomStatus.UNRESOLVED, localized=False) for i in (1, 2, 3)])
        op.calibration_id = "test_endpoint"
        with self.assertRaises(HomeCityScanError) as error:
            op.localized_after(home(0), "pan")
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.LOCALIZATION_UNRESOLVED)
        self.assertEqual([], op.core.actuator.actions)

    def test_postpan_rounded_zoom_does_not_hide_measured_departure(self):
        op = operation([home(1, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, zoom=.75)])
        op.calibration_id = "test_endpoint"
        with self.assertRaises(HomeCityScanError) as error:
            op.localized_after(home(0), "pan")
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.ZOOM_CHANGED)

    def test_postpan_recovery_can_localize_on_last_permitted_capture(self):
        op = operation([home(i, status=HomeCityZoomStatus.UNRESOLVED, localized=False) for i in (1, 2)]
                       + [home(3)])
        op.calibration_id = "test_endpoint"
        self.assertEqual(home(3), op.localized_after(home(0), "pan"))

    def test_ambiguous_postpan_fit_can_recover_passively_without_another_input(self):
        ambiguous = home(1, status=HomeCityZoomStatus.UNRESOLVED, localized=False)
        ambiguous = replace(ambiguous, spatial_surface=replace(
            ambiguous.spatial_surface,
            camera_proof=HomeCityCameraProof(HomeCityCameraStatus.AMBIGUOUS, "test"),
        ))
        op = operation([ambiguous, home(2)])
        op.calibration_id = "test_endpoint"
        self.assertEqual(home(2), op.localized_after(home(0), "pan"))
        self.assertEqual([], op.core.actuator.actions)

    def test_slow_current_pose_does_not_trigger_redundant_stable_content_capture(self):
        elapsed = [0.0]
        op = operation([], clock=lambda: elapsed[0])
        op.calibration_id = "test_endpoint"
        calls = []
        def capture(label):
            calls.append(label)
            elapsed[0] += 24.0
            return home(len(calls))
        op.observe_content = capture
        self.assertEqual(home(1), op.localized_after(home(0), "pan"))
        self.assertEqual(1, len(calls))
        self.assertEqual(45.0, op.core.policy.max_seconds)


class HomeEntryTests(unittest.TestCase):
    def core(self, homes, destinations=None):
        content = iter(homes)
        arrival = iter(destinations or [frame(ScreenType.PNC_ILLUSORY_BEAST_MANOR,
                                            captured_at=_NOW + timedelta(seconds=i)) for i in (10, 11)])
        actuator = Actuator()
        core = NavigationCore(actuator, lambda _: next(arrival), reviewed_navigation_edges(),
                              sleep=lambda _: None, clock=lambda: 0)
        return core, lambda _: next(content), actuator

    def test_visible_and_acquisition_each_normalize_then_tap_fresh_exact_body_once(self):
        for method in ("open_visible_building", "open_building"):
            with self.subTest(method=method):
                core, observe, actuator = self.core([home(i, objects=(_BODY,)) for i in range(3)])
                result = getattr(core, method)(_TARGET, observe_content=observe)
                self.assertIs(result.screen_type, ScreenType.PNC_ILLUSORY_BEAST_MANOR)
                self.assertEqual(1, len(actuator.actions))
                self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
                self.assertTrue(actuator.actions[0].exact_geometry)
                self.assertEqual(_BODY, actuator.actions[0].expected_object)

    def test_callback_requires_new_body_proof_before_tap(self):
        moved = replace(_BODY, action_point=(455, 805))
        core, observe, actuator = self.core([home(i, objects=(_BODY,)) for i in range(2)] + [home(2, objects=(moved,))])
        notified = []
        core.open_visible_building(_TARGET, observe_content=observe, on_target_acquired=notified.append)
        self.assertEqual([_BODY], notified)
        self.assertEqual(moved, actuator.actions[0].expected_object)
        self.assertEqual((455, 805), actuator.actions[0].target_point)

    def test_body_lost_after_callback_stops_without_tap(self):
        core, observe, actuator = self.core([home(i, objects=(_BODY,)) for i in range(2)] + [home(2)])
        with self.assertRaises(HomeCityScanError):
            core.open_visible_building(_TARGET, observe_content=observe, on_target_acquired=lambda _: None)
        self.assertEqual([], actuator.actions)

    def test_unexpected_destination_does_not_repeat_building_tap(self):
        core, observe, actuator = self.core([home(i, objects=(_BODY,)) for i in range(3)],
                                           [frame(ScreenType.PNC_BAG, captured_at=_NOW + timedelta(seconds=4))])
        with self.assertRaises(HomeCityScanError) as error:
            core.open_visible_building(_TARGET, observe_content=observe)
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.UNEXPECTED_DESTINATION)
        self.assertEqual(1, len(actuator.actions))

    def test_legacy_pan_is_rejected_before_dispatch(self):
        core, observe, actuator = self.core([home(0), home(1)])
        legacy = HomeCityCameraPanStep(SwipeAction(direction="down"), "y", (1000, 2000))
        with patch("pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step", return_value=legacy):
            with self.assertRaises(HomeCityScanError) as error:
                core.open_building(_TARGET, observe_content=observe)
        self.assertIs(error.exception.result.stop_reason, HomeCityScanStopReason.NO_SAFE_GESTURE)
        self.assertEqual([], actuator.actions)

    def test_qualified_pan_relocalizes_then_reacquires_body_without_renormalizing(self):
        core, observe, actuator = self.core([home(0), home(1)] + [
            home(i, translation=(-288, 100), objects=(_BODY,)) for i in (2, 3)
        ])
        action = SwipeAction(
            direction="down", purpose=SwipePurpose.HOME_CITY_CAMERA, exact_geometry=True,
            start_x_ratio=.5, end_x_ratio=.5, start_y_ratio=.5, end_y_ratio=.6,
            safe_bounds=Bounds(440, 790, 30, 180), duration_ms=425,
        )
        step = HomeCityCameraPanStep(action, "y", (1000, 500))
        with patch("pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step", return_value=step):
            core.open_building(_TARGET, observe_content=observe)
        self.assertEqual([SwipeAction, TapSpatialObjectAction], [type(item) for item in actuator.actions])

    def test_visible_only_does_not_start_offscreen_search(self):
        core, observe, actuator = self.core([home(i) for i in range(3)])
        with self.assertRaises(HomeCityScanError):
            core.open_visible_building(_TARGET, observe_content=observe)
        self.assertEqual([], actuator.actions)

    def test_discovery_returns_normalization_stop_without_tap(self):
        core, observe, actuator = self.core([home(0, status=HomeCityZoomStatus.NOT_AT_ENDPOINT, anchor=False)])
        result = core.discover_home_city(observe_content=observe)
        self.assertIs(result.stop_reason, HomeCityScanStopReason.ZOOM_ANCHOR_UNRESOLVED)
        self.assertEqual(54, len(result.remaining_slots))
        self.assertEqual([], actuator.actions)

    def test_home_trace_retains_typed_counts_and_strips_unlisted_values(self):
        record = _sanitize_trace_entry({
            "event": "home_city_navigation_step", "zoom_inputs": 2, "gestures": 1,
            "translation": (-288, 100), "group_ids": ["fountain"],
            "artifact": "private/directory/frame.png", "account_secret": "must_drop",
        })
        self.assertEqual(2, record["zoom_inputs"])
        self.assertEqual([-288, 100], record["translation"])
        self.assertEqual("frame.png", record["artifact"])
        self.assertNotIn("account_secret", record)
