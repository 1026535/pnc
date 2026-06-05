"""World-map movement calibration tests."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldMapCardinalDirection
from pnc_automation.app.pnc.navigation.world_map_movement_calibration import (
    WorldMapLaneProbeRequest,
    WorldMapMovementCalibrationService,
    WorldMapSwipeProbeClassification,
    WorldMapSweepValidationRequest,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    TraversalStridePolicy,
    WorldMapBounds,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchService,
)
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.pnc.persistence.world_map_survey_debug_store import WorldMapSurveyDebugStore
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from tests.test_support import (
    FakeObservationService,
    FakeSession,
    build_logger,
    make_observation,
    make_spatial_surface,
)


class WorldMapMovementCalibrationTests(unittest.TestCase):
    """Validates the dedicated movement-calibration probe and sweep helpers."""

    def setUp(self) -> None:
        """Builds the shared flow planner and temp artifact root."""

        self.flows = ScreenFlowPlanner()
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)

    def test_probe_swipe_records_exact_swipe_points_and_delta(self) -> None:
        """Records one exact swipe probe with coordinate deltas, OCR evidence, and exact emitted swipe points."""

        service, _observer, session = self._build_service(
            observations=[
                _make_world_map_observation(10, 0),
            ]
        )

        result, after = service.probe_swipe(
            _make_world_map_observation(0, 0),
            direction=WorldMapCardinalDirection.LEFT,
            distance_ratio=0.20,
            label_prefix="probe_left",
        )

        self.assertEqual(result.classification, WorldMapSwipeProbeClassification.MOVED)
        self.assertEqual(result.delta, (10, 0))
        self.assertEqual(result.swipe_points, session.swipes[0][:4])
        self.assertEqual(result.before.coordinate_text, "X:0 Y:0")
        self.assertEqual(result.after.coordinate_text, "X:10 Y:0")
        self.assertEqual(after.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate, (10, 0))

    def test_probe_swipe_classifies_expected_boundary_stop(self) -> None:
        """Treats zero motion at the expected map edge as a boundary stop rather than an interior stall."""

        service, _observer, _session = self._build_service(
            observations=[
                _make_world_map_observation(20, 10),
            ]
        )

        result, _after = service.probe_swipe(
            _make_world_map_observation(20, 10),
            direction=WorldMapCardinalDirection.LEFT,
            distance_ratio=0.20,
            label_prefix="probe_boundary",
            boundary_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=20),
        )

        self.assertEqual(result.classification, WorldMapSwipeProbeClassification.EXPECTED_BOUNDARY_STOP)
        self.assertTrue(result.near_boundary)

    def test_probe_swipe_reports_moved_with_drift_when_primary_axis_succeeds(self) -> None:
        """Reports orthogonal drift separately from wrong-sign primary movement."""

        service, _observer, _session = self._build_service(
            observations=[
                _make_world_map_observation(6, 9),
            ]
        )

        result, _after = service.probe_swipe(
            _make_world_map_observation(0, 0),
            direction=WorldMapCardinalDirection.LEFT,
            distance_ratio=0.20,
            label_prefix="probe_left_drift",
        )

        self.assertEqual(result.classification, WorldMapSwipeProbeClassification.MOVED_WITH_DRIFT)
        self.assertEqual(result.delta, (6, 9))

    def test_probe_swipe_reports_wrong_sign_primary_axis_as_unexpected_delta(self) -> None:
        """Still fails the probe when the intended primary axis moves in the wrong direction."""

        service, _observer, _session = self._build_service(
            observations=[
                _make_world_map_observation(-4, 0),
            ]
        )

        result, _after = service.probe_swipe(
            _make_world_map_observation(0, 0),
            direction=WorldMapCardinalDirection.LEFT,
            distance_ratio=0.20,
            label_prefix="probe_left_wrong_sign",
        )

        self.assertEqual(result.classification, WorldMapSwipeProbeClassification.UNEXPECTED_DELTA)
        self.assertEqual(result.delta, (-4, 0))

    def test_run_dead_zone_verification_refocuses_anchor_before_every_direction(self) -> None:
        """Starts every directional dead-zone probe from the requested anchor instead of the prior probe result."""

        anchor = (50, 50)
        service, _observer, _session = self._build_service(
            observations=[
                _make_world_map_observation(60, 50),
                _make_world_map_observation(50, 50),
                _make_world_map_observation(40, 50),
                _make_world_map_observation(50, 50),
                _make_world_map_observation(50, 60),
                _make_world_map_observation(50, 50),
                _make_world_map_observation(50, 40),
            ]
        )

        report, _current = service.run_dead_zone_verification(
            _make_world_map_observation(*anchor),
            label_prefix="dead_zone_anchor",
            probe_coordinates=(anchor,),
            distance_ratio=0.20,
            bounds=WorldMapBounds(min_x=0, min_y=0, max_x=100, max_y=100),
        )

        self.assertEqual([result.before.coordinate for result in report.probe_results], [anchor, anchor, anchor, anchor])

    def test_probe_swipe_recovers_transient_unknown_follow_up_into_a_proven_world_map(self) -> None:
        """Re-proves the world-map surface when a live swipe follow-up briefly lands on an unknown OCR frame."""

        service, observer, _session = self._build_service(
            observations=[
                make_observation(ScreenType.UNKNOWN),
                _make_world_map_observation(10, 0),
            ]
        )

        result, after = service.probe_swipe(
            _make_world_map_observation(0, 0),
            direction=WorldMapCardinalDirection.LEFT,
            distance_ratio=0.20,
            label_prefix="probe_left_unknown_retry",
        )

        self.assertEqual(result.classification, WorldMapSwipeProbeClassification.MOVED)
        self.assertEqual(result.delta, (10, 0))
        self.assertEqual(after.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate, (10, 0))
        self.assertEqual(len(observer.labels), 2)

    def test_run_lane_probe_sequence_recenters_before_every_probe_on_the_requested_lane(self) -> None:
        """Keeps focused lane diagnostics anchored to one coordinate instead of chaining probe drift into later samples."""

        anchor = (50, 50)
        service, _observer, _session = self._build_service(
            observations=[
                _make_world_map_observation(60, 50),
                _make_world_map_observation(50, 50),
                _make_world_map_observation(40, 50),
            ]
        )

        report, _current = service.run_lane_probe_sequence(
            _make_world_map_observation(*anchor),
            request=WorldMapLaneProbeRequest(
                name="horizontal_lane",
                anchor_coordinate=anchor,
                probe_directions=(WorldMapCardinalDirection.LEFT, WorldMapCardinalDirection.RIGHT),
                distance_ratios=(0.20,),
                lane_center_ratios={
                    WorldMapCardinalDirection.LEFT: 0.72,
                    WorldMapCardinalDirection.RIGHT: 0.72,
                },
                boundary_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=100, max_y=100),
            ),
            label_prefix="horizontal_lane",
        )

        self.assertEqual(report.anchor_coordinate, anchor)
        self.assertEqual([result.before.coordinate for result in report.probe_results], [anchor, anchor])
        self.assertTrue(all(result.lane_center_ratio == 0.72 for result in report.probe_results))

    def test_run_cardinal_calibration_builds_matrix_entries_and_returns_to_origin(self) -> None:
        """Runs the formal calibration matrix from one stable origin and resets the viewport between trials."""

        service, _observer, _session = self._build_service(
            observations=[
                _make_world_map_observation(60, 50),
                _make_world_map_observation(50, 50),
                _make_world_map_observation(40, 50),
                _make_world_map_observation(50, 50),
                _make_world_map_observation(50, 60),
                _make_world_map_observation(50, 50),
                _make_world_map_observation(50, 40),
                _make_world_map_observation(50, 50),
            ]
        )

        report, current = service.run_cardinal_calibration(
            _make_world_map_observation(50, 50),
            label_prefix="cardinal_matrix",
            repeats_per_combination=1,
            ratios=(0.20,),
            lane_candidates={
                WorldMapCardinalDirection.LEFT: (0.60,),
                WorldMapCardinalDirection.RIGHT: (0.60,),
                WorldMapCardinalDirection.UP: (0.46,),
                WorldMapCardinalDirection.DOWN: (0.46,),
            },
        )

        self.assertEqual(len(report.canonical_profiles), 4)
        self.assertEqual(len(report.entries), 4)
        self.assertEqual(current.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate, (50, 50))

    def test_validate_sweep_records_usable_checkpoint_observations_without_recapture(self) -> None:
        """Validates sweep traversal by ingesting the already-proven post-move frames instead of forcing duplicate captures."""

        service, observer, _session = self._build_service(
            observations=[
                _make_world_map_observation(10, 0),
                _make_world_map_observation(10, 10),
            ]
        )

        result, _current = service.validate_sweep(
            _make_world_map_observation(0, 0),
            request=WorldMapSweepValidationRequest(
                name="row_major_segment",
                pattern=WorldMapSearchPattern.row_major_sweep(),
                traversal_stride_policy=TraversalStridePolicy.symmetric(10),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 10)),
            ),
            label_prefix="row_major_segment",
        )

        self.assertEqual(result.stop_reason, "route_exhausted")
        self.assertEqual(len(result.checkpoint_results), 2)
        self.assertTrue(all(checkpoint.usable_observation for checkpoint in result.checkpoint_results))
        self.assertTrue(all(checkpoint.within_tolerance for checkpoint in result.checkpoint_results))
        self.assertEqual([checkpoint.delta_from_checkpoint for checkpoint in result.checkpoint_results], [(0, 0), (0, 0)])
        self.assertEqual(len(observer.labels), 2)

    def test_validate_sweep_uses_shared_search_checkpoint_mover_runtime_state(self) -> None:
        """Routes sweep validation through the search service mover with one shared runtime state across checkpoints."""

        observer = FakeObservationService(observations=[])
        recorder = WorldMapSurveyRecorder(
            observation_service=observer,
            debug_store=WorldMapSurveyDebugStore(root=Path(self.temp_directory.name)),
        )
        mover = _RecordingCoordinateMover()
        search_service = WorldMapSearchService(
            screen_flows=self.flows,
            observation_service=observer,
            action_executor=None,
            survey_recorder=recorder,
            coordinate_mover=mover,
        )
        service = WorldMapMovementCalibrationService(
            screen_flows=self.flows,
            observation_service=observer,
            action_executor=None,
            survey_recorder=recorder,
            search_service=search_service,
        )

        result, _current = service.validate_sweep(
            _make_world_map_observation(0, 0),
            request=WorldMapSweepValidationRequest(
                name="shared_mover",
                pattern=WorldMapSearchPattern.row_major_sweep(),
                traversal_stride_policy=TraversalStridePolicy.symmetric(10),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(20, 0)),
            ),
            label_prefix="shared_mover",
        )

        self.assertEqual([checkpoint.checkpoint.coordinate for checkpoint in result.checkpoint_results], [(10, 0), (20, 0)])
        self.assertEqual(mover.target_coordinates, [(10, 0), (20, 0)])
        self.assertEqual(len({id(runtime_state) for runtime_state in mover.runtime_states}), 1)

    def test_validate_sweep_flushes_buffered_logs_when_a_later_checkpoint_fails(self) -> None:
        """Flushes already-buffered checkpoint movement logs even when sweep validation fails mid-route."""

        logger, records = _build_recording_logger("world_map_sweep_flush")
        service, _observer, _session = self._build_service(
            observations=[
                _make_world_map_observation(10, 0),
            ],
            logger=logger,
        )

        with self.assertRaises(AssertionError):
            service.validate_sweep(
                _make_world_map_observation(0, 0),
                request=WorldMapSweepValidationRequest(
                    name="flush_on_failure",
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    traversal_stride_policy=TraversalStridePolicy.symmetric(10),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(20, 0)),
                ),
                label_prefix="flush_on_failure",
            )

        self.assertTrue(any(record.msg == "World-map movement step completed." for record in records))

    def _build_service(
        self,
        *,
        observations: list[object],
        logger: logging.LoggerAdapter | None = None,
    ) -> tuple[WorldMapMovementCalibrationService, FakeObservationService, FakeSession]:
        """Builds one fully wired calibration service plus the fake runtime services backing it."""

        runtime_logger = build_logger() if logger is None else logger
        observer = FakeObservationService(observations=observations)
        session = FakeSession()
        recorder = WorldMapSurveyRecorder(
            observation_service=observer,
            debug_store=WorldMapSurveyDebugStore(root=Path(self.temp_directory.name)),
        )
        search_service = WorldMapSearchService(
            screen_flows=self.flows,
            observation_service=observer,
            action_executor=ObservedActionExecutor(
                selector_registry=build_default_selector_registry(),
                action_executor=ActionExecutor(
                    session=session,
                    stable_click_delay_ms=0,
                    post_action_observe_delay_ms=0,
                    chat_stable_click_delay_ms=0,
                    chat_post_action_observe_delay_ms=0,
                    logger=runtime_logger,
                    sleep=lambda _: None,
                ),
                logger=runtime_logger,
                sleep=lambda _: None,
            ),
            survey_recorder=recorder,
        )
        service = WorldMapMovementCalibrationService(
            screen_flows=self.flows,
            observation_service=observer,
            action_executor=search_service.action_executor,
            survey_recorder=recorder,
            search_service=search_service,
        )
        return service, observer, session


class _RecordingCoordinateMover:
    """Records coordinate-mover calls while returning exact target-coordinate observations."""

    def __init__(self) -> None:
        """Initializes the call log and exposes a navigator-like focus tolerance."""

        self.navigator = type("Navigator", (), {"focus_tolerance": 1})()
        self.target_coordinates: list[tuple[int, int]] = []
        self.runtime_states: list[object] = []

    def move_to_coordinate(
        self,
        observation: object,
        *,
        target_coordinate: tuple[int, int],
        label_prefix: str,
        runtime_state: dict[str, object] | None = None,
        boundary_bounds: object = None,
        coordinate_domain: object = None,
        movement_family: object = None,
        arrival_observation_request: object = None,
        movement_proof_artifact_selection: object = None,
        arrival_artifact_selection: object = None,
        logging_mode: object = None,
    ) -> object:
        """Records the requested movement and returns a world-map observation at the target."""

        del (
            observation,
            label_prefix,
            boundary_bounds,
            coordinate_domain,
            movement_family,
            arrival_observation_request,
            movement_proof_artifact_selection,
            arrival_artifact_selection,
            logging_mode,
        )
        self.target_coordinates.append(target_coordinate)
        self.runtime_states.append(runtime_state)
        return _make_world_map_observation(*target_coordinate)


def _make_world_map_observation(x: int, y: int) -> object:
    """Builds one synthetic world-map observation with coordinate OCR evidence."""

    return make_observation(
        ScreenType.PNC_WORLD_MAP,
        visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_SEARCH_BUTTON),
        spatial_surface=make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=x,
            y=y,
            metadata={"coordinate_text": f"X:{x} Y:{y}"},
        ),
    )


def _build_recording_logger(name: str) -> tuple[logging.LoggerAdapter, list[logging.LogRecord]]:
    """Builds one in-memory logger adapter plus the structured records it emits."""

    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(f"pnc_automation.tests.{name}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(_ListHandler())
    return logging.LoggerAdapter(logger, extra={}), records


if __name__ == "__main__":
    unittest.main()
