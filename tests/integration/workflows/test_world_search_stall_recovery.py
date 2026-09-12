"""World search stall recovery: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchStallRecoveryTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search stall recovery."""

    def test_execute_search_recovers_from_one_interior_stall_before_reaching_the_checkpoint(self) -> None:
        """Lets the shared mover widen one stagnant swipe attempt instead of aborting before the next calibrated retry."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 0),
            ]
        )

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
            ),
            label_prefix="one_stall_then_success",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual([checkpoint.coordinate for checkpoint in result.visited_checkpoints], [(10, 0)])
        self.assertEqual(
            observer.labels,
            [
                "one_stall_then_success_move_0_0_post_action_1",
                "one_stall_then_success_move_0_1_post_action_1",
            ],
        )

    def test_execute_search_reports_bounded_interior_stall_retry_exhaustion_with_swipe_diagnostics(self) -> None:
        """Fails once the shared mover exhausts stagnant retries and preserves the exact swipe evidence for live diagnosis."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0, artifact_path=Path("artifacts/stall_1.png")),
                _make_world_map_observation(0, 0, artifact_path=Path("artifacts/stall_2.png")),
                _make_world_map_observation(0, 0, artifact_path=Path("artifacts/stall_3.png")),
                _make_world_map_observation(0, 0, artifact_path=Path("artifacts/stall_failure.png")),
            ]
        )

        with self.assertRaises(SelectorResolutionError) as error:
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                ),
                label_prefix="zero_delta_reactive",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["classification"], "interior_stall")
        self.assertEqual(error.exception.details["artifact_path"], str(Path("artifacts/stall_3.png")))
        self.assertEqual(len(error.exception.details["swipe_points"]), 4)
        self.assertIn("stagnant_retry_failure", error.exception.details)
        self.assertEqual(
            observer.labels,
            [
                "zero_delta_reactive_move_0_0_post_action_1",
                "zero_delta_reactive_move_0_1_post_action_1",
                "zero_delta_reactive_move_0_2_post_action_1",
                "zero_delta_reactive_move_0_failure_3",
            ],
        )

    def test_execute_search_supports_explicitly_larger_coordinate_focus_budget_for_long_sweeps(self) -> None:
        """Allows long-running sweep traversal to keep advancing past the default bounded leg budget when configured."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(10, 0),
                _make_world_map_observation(20, 0),
                _make_world_map_observation(30, 0),
                _make_world_map_observation(40, 0),
                _make_world_map_observation(50, 0),
                _make_world_map_observation(60, 0),
                _make_world_map_observation(70, 0),
                _make_world_map_observation(80, 0),
                _make_world_map_observation(90, 0),
            ]
        )
        service.movement_step_budget = 10

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(90, 0), max_coordinate=(90, 0)),
                checkpoint_spacing=10,
            ),
            label_prefix="extended_coordinate_focus_budget",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual([checkpoint.coordinate for checkpoint in result.visited_checkpoints], [(90, 0)])
        self.assertEqual(len(observer.labels), 9)
        self.assertEqual(service.coordinate_mover_for_runtime().movement_step_budget, 10)
