"""World search checkpoint capture: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchStopReason,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.spatial import make_spatial_object
from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchCheckpointCaptureTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search checkpoint capture."""

    def test_execute_search_builds_p2_from_narrow_p1_checkpoint_capture(self) -> None:
        """Captures once in P1 when a caller-supplied start observation has no owned screenshot."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(
                    10,
                    0,
                    objects=(make_spatial_object(SpatialObjectKind.MONSTER, estimated_world_coordinate=(10, 0)),),
                ),
            ]
        )
        start = _make_world_map_observation(
            10,
            0,
            objects=(make_spatial_object(SpatialObjectKind.MONSTER, estimated_world_coordinate=(10, 0)),),
        )

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.MONSTER),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
            ),
            label_prefix="p1_p2",
            start_observation=start,
        )

        self.assertEqual(result.stop_reason, WorldMapSearchStopReason.BOUNDARY_EXHAUSTED)
        self.assertEqual(observer.labels, ["p1_p2_checkpoint_0_p1_capture"])
        self.assertEqual(observer.requests, [ObservationRequest.world_map_movement_proof_follow_up()])
        assert result.execution_profile is not None
        self.assertGreaterEqual(result.execution_profile.checkpoint_profiles[0].p2_analysis_elapsed_ms, 0.0)
        self.assertEqual(len(result.survey_index.sightings), 1)

    def test_execute_search_submits_live_landing_inside_movement_arrival_tolerance(self) -> None:
        """Uses the mover's canonical arrival tolerance again at the P1-to-P2 boundary."""

        service, _observer = self._build_runtime_service(
            observations=[_make_world_map_observation(0, 8)]
        )

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                ),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 10), max_coordinate=(0, 10)),
                checkpoint_spacing=10,
            ),
            label_prefix="arrival_tolerance_p2",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(result.visited_checkpoints[0].coordinate, (0, 10))

    def test_execute_search_submits_crossed_target_inside_movement_overshoot_band(self) -> None:
        """Preserves a mover-accepted crossed-target landing at the P1-to-P2 boundary."""

        service, _observer = self._build_runtime_service(
            observations=[_make_world_map_observation(0, 14)]
        )

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                ),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 10), max_coordinate=(0, 10)),
                checkpoint_spacing=10,
            ),
            label_prefix="overshoot_tolerance_p2",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(result.visited_checkpoints[0].coordinate, (0, 10))
