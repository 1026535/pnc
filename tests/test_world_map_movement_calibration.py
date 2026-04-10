"""World-map movement calibration tests."""

from __future__ import annotations

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
    WorldMapMovementCalibrationService,
    WorldMapSwipeProbeClassification,
    WorldMapSweepValidationRequest,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
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
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 10)),
                checkpoint_spacing=10,
            ),
            label_prefix="row_major_segment",
        )

        self.assertEqual(result.stop_reason, "route_exhausted")
        self.assertEqual(len(result.checkpoint_results), 2)
        self.assertTrue(all(checkpoint.usable_observation for checkpoint in result.checkpoint_results))
        self.assertEqual(len(observer.labels), 2)

    def _build_service(
        self,
        *,
        observations: list[object],
    ) -> tuple[WorldMapMovementCalibrationService, FakeObservationService, FakeSession]:
        """Builds one fully wired calibration service plus the fake runtime services backing it."""

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
                    logger=build_logger(),
                    sleep=lambda _: None,
                ),
                logger=build_logger(),
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


if __name__ == "__main__":
    unittest.main()
