"""World search sweep segments: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import threading
import time
import unittest

from pnc_automation.app.pnc.domain.observation import (
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_analysis import WorldMapViewportAnalyzer
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
)
from pnc_automation.app.pnc.navigation.world_map_sweep import WorldMapSweepPolicy
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchSweepSegmentsTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search sweep segments."""

    def test_production_search_overlaps_actual_p1_samples_with_movement(self) -> None:
        """Runs bounded P2 workers from narrow P1 sample screenshots while movement continues."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 0),
                _make_world_map_observation(20, 0),
            ]
        )
        worker_threads: list[str] = []
        work_has_observation: list[bool] = []
        screenshot_ids: list[int] = []

        def analyze_screenshot(screenshot: object, request: ObservationRequest) -> Observation:
            """Simulates rich OCR long enough to prove movement/P2 overlap."""

            worker_threads.append(threading.current_thread().name)
            screenshot_ids.append(id(screenshot))
            time.sleep(0.02)
            if request.expected_world_coordinate is None:
                raise AssertionError("P2 production samples must carry a projected coordinate.")
            return _make_world_map_observation(*request.expected_world_coordinate)

        analyzer = WorldMapViewportAnalyzer(observation_builder=analyze_screenshot)

        class RecordingAnalyzer:
            """Records queued work-item shape before delegating rich analysis."""

            @staticmethod
            def analyze(work_item: object):
                """Records that no Observation crossed into P2 and analyzes its screenshot."""

                work_has_observation.append(hasattr(work_item, "observation"))
                return analyzer.analyze(work_item)

        service.viewport_analyzer = RecordingAnalyzer()

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                ),
                pattern=WorldMapSearchPattern.serpentine_row_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(20, 0)),
                checkpoint_spacing=10,
                sweep_policy=WorldMapSweepPolicy.production_full_map(max_pending_p2_items=2),
            ),
            label_prefix="production_p2_overlap",
            start_observation=_make_world_map_observation(0, 0),
        )

        assert result.execution_profile is not None
        self.assertEqual(result.execution_profile.p2_queue_submission_count, 3)
        self.assertGreaterEqual(result.execution_profile.p2_queue_peak_depth, 2)
        self.assertGreaterEqual(result.execution_profile.p2_movement_overlap_count, 1)
        self.assertEqual(work_has_observation, [False, False, False])
        self.assertEqual(len(set(screenshot_ids)), 3)
        self.assertEqual(observer.requests.count(ObservationRequest.world_map_movement_proof_follow_up()), 3)
        self.assertTrue(all(name.startswith("world-map-p2") for name in worker_threads))

    def test_production_segment_keeps_actual_trajectory_samples_when_no_coverage_gap(self) -> None:
        """Avoids correcting planned-coordinate drift when actual sampled viewports preserve continuous coverage."""

        service, observer, session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 8),
                _make_world_map_observation(20, 8),
            ]
        )

        def analyze_screenshot(_screenshot: object, request: ObservationRequest) -> Observation:
            """Builds a rich observation at the P2 work item's coordinate."""

            if request.expected_world_coordinate is None:
                raise AssertionError("P2 production samples must carry a projected coordinate.")
            return _make_world_map_observation(*request.expected_world_coordinate)

        service.viewport_analyzer = WorldMapViewportAnalyzer(observation_builder=analyze_screenshot)

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                ),
                pattern=WorldMapSearchPattern.serpentine_row_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(20, 0)),
                checkpoint_spacing=10,
                sweep_policy=WorldMapSweepPolicy.production_full_map(max_pending_p2_items=2),
            ),
            label_prefix="production_endpoint_correction",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual([checkpoint.coordinate for checkpoint in result.visited_checkpoints], [(0, 0), (10, 0), (20, 0)])
        self.assertFalse(any("coverage_correction" in label for label in observer.labels))
        self.assertTrue(all(start_y == end_y for _start_x, start_y, _end_x, end_y, _duration in session.swipes))
        assert result.execution_profile is not None
        self.assertEqual(result.execution_profile.p2_queue_submission_count, 3)

    def test_production_segment_start_aligns_anchor_when_only_coverage_is_contiguous(self) -> None:
        """Moves to the planned lane start when the current viewport covers it but is outside movement tolerance."""

        service, observer, session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 0),
                _make_world_map_observation(20, 0),
            ]
        )
        analyzed_coordinates: list[tuple[int, int]] = []

        def analyze_screenshot(_screenshot: object, request: ObservationRequest) -> Observation:
            """Records the actual-coordinate P2 anchor used for each sampled screenshot."""

            if request.expected_world_coordinate is None:
                raise AssertionError("P2 production samples must carry an actual coordinate.")
            analyzed_coordinates.append(request.expected_world_coordinate)
            return _make_world_map_observation(*request.expected_world_coordinate)

        service.viewport_analyzer = WorldMapViewportAnalyzer(observation_builder=analyze_screenshot)

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                ),
                pattern=WorldMapSearchPattern.serpentine_row_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(20, 0)),
                checkpoint_spacing=10,
                sweep_policy=WorldMapSweepPolicy.production_full_map(max_pending_p2_items=2),
            ),
            label_prefix="production_segment_start_covered",
            start_observation=_make_world_map_observation(5, 5),
        )

        self.assertEqual([checkpoint.coordinate for checkpoint in result.visited_checkpoints], [(0, 0), (10, 0), (20, 0)])
        self.assertEqual(analyzed_coordinates, [(0, 0), (10, 0), (20, 0)])
        self.assertTrue(any("anchor_alignment" in label for label in observer.labels))
        self.assertEqual(len(session.swipes), 3)
        assert result.execution_profile is not None
        self.assertEqual(
            [
                (sample.planned_coordinate, sample.actual_coordinate)
                for sample in result.execution_profile.production_samples
            ],
            [((0, 0), (0, 0)), ((10, 0), (10, 0)), ((20, 0), (20, 0))],
        )

    def test_production_segment_transition_aligns_next_row_before_lane_swipes(self) -> None:
        """Moves to the next row start even when the previous row endpoint is still inside scan footprint."""

        service, _observer, session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 0),
                _make_world_map_observation(20, 0),
                _make_world_map_observation(20, 10),
                _make_world_map_observation(10, 10),
                _make_world_map_observation(0, 10),
            ]
        )

        def analyze_screenshot(_screenshot: object, request: ObservationRequest) -> Observation:
            """Builds a rich observation at the actual sampled coordinate."""

            if request.expected_world_coordinate is None:
                raise AssertionError("P2 production samples must carry an actual coordinate.")
            return _make_world_map_observation(*request.expected_world_coordinate)

        service.viewport_analyzer = WorldMapViewportAnalyzer(observation_builder=analyze_screenshot)

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                ),
                pattern=WorldMapSearchPattern.serpentine_row_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(20, 10)),
                checkpoint_spacing=10,
                sweep_policy=WorldMapSweepPolicy.production_full_map(max_pending_p2_items=2),
            ),
            label_prefix="production_two_row_anchor",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(
            [checkpoint.coordinate for checkpoint in result.visited_checkpoints],
            [(0, 0), (10, 0), (20, 0), (20, 10), (10, 10), (0, 10)],
        )
        self.assertGreaterEqual(len(session.swipes), 5)
        self.assertNotEqual(session.swipes[2][1], session.swipes[2][3])
        self.assertEqual(session.swipes[3][1], session.swipes[3][3])
        assert result.execution_profile is not None
        self.assertEqual(
            [
                (sample.planned_coordinate, sample.actual_coordinate)
                for sample in result.execution_profile.production_samples
            ],
            [
                ((0, 0), (0, 0)),
                ((10, 0), (10, 0)),
                ((20, 0), (20, 0)),
                ((20, 10), (20, 10)),
                ((10, 10), (10, 10)),
                ((0, 10), (0, 10)),
            ],
        )
