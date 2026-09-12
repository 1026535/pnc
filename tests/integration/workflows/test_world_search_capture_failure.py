"""World search capture failure: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

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


class WorldSearchCaptureFailureTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search capture failure."""

    def test_production_search_propagates_p2_worker_failure(self) -> None:
        """Surfaces a worker failure instead of returning a partially parsed survey."""

        service, _observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 0),
            ]
        )

        def fail_p2(_screenshot: object, request: ObservationRequest) -> Observation:
            """Raises a deterministic rich-analysis failure for the second viewport."""

            if request.expected_world_coordinate == (10, 0):
                raise RuntimeError("synthetic P2 failure")
            return _make_world_map_observation(0, 0)

        service.viewport_analyzer = WorldMapViewportAnalyzer(observation_builder=fail_p2)

        with self.assertRaisesRegex(RuntimeError, "synthetic P2 failure"):
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(
                        surface_type=SpatialSurfaceType.WORLD_MAP,
                        kind=SpatialObjectKind.RESOURCE_NODE,
                    ),
                    pattern=WorldMapSearchPattern.serpentine_row_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                    sweep_policy=WorldMapSweepPolicy.production_full_map(max_pending_p2_items=2),
                ),
                label_prefix="production_p2_failure",
                start_observation=_make_world_map_observation(0, 0),
            )

    def test_p1_fallback_capture_counts_missing_capture_recapture(self) -> None:
        """Counts recapture when movement returned an observation without exposing its P1 capture."""

        service, observer = self._build_runtime_service(
            observations=[_make_world_map_observation(0, 0)]
        )
        profile_state: dict[str, object] = {}

        _observation, capture = service._resolve_p1_movement_proof_capture(
            _make_world_map_observation(0, 0),
            p1_captures=(),
            label="missing_capture",
            profile_state=profile_state,
        )

        self.assertIs(capture, observer.captures[0])
        self.assertEqual(profile_state["p1_fallback_capture_count"], 1)
        self.assertEqual(profile_state["p1_missing_capture_count"], 1)
        self.assertNotIn("p1_mismatched_capture_count", profile_state)
