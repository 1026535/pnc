"""Opt-in live smoke tests for world-map movement calibration on a real account."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.script_runner import configure_world_map_movement_budget
from pnc_automation.app.pnc.domain.observation import Observation, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.automation.engine.task import TaskPreflight
from pnc_automation.app.pnc.navigation.world_map_movement_calibration import (
    WorldMapLaneProbeRequest,
    WorldMapSwipeProbeClassification,
    WorldMapSweepValidationRequest,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapBounds,
    WorldMapCoordinateDomain,
    WorldMapEdge,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchRequest,
    WorldMapSearchStopPolicy,
)
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldMapCardinalDirection
from tests.live_smoke_support import build_live_runtime_bundle

_WORLD_MAP_PREFLIGHT_MAX_STEPS = 20


def _live_world_map_movement_calibration_enabled() -> bool:
    """Returns whether the explicit live movement-calibration smoke flag is enabled."""

    return os.getenv("PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION") == "1"


@unittest.skipUnless(
    _live_world_map_movement_calibration_enabled(),
    "Set PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION=1 to run live world-map movement calibration smoke tests.",
)
class LiveWorldMapMovementCalibrationSmokeTests(unittest.TestCase):
    """Runs a bounded live smoke pass across the new movement-calibration service on a real account."""

    @classmethod
    def setUpClass(cls) -> None:
        """Prepares the selected live account and builds the shared runtime services once for the suite."""

        cls.config_path = Path(os.getenv("PNC_LIVE_WORLD_MAP_MOVEMENT_CONFIG", "config/accounts.yaml"))
        cls.account_id = os.getenv("PNC_LIVE_WORLD_MAP_MOVEMENT_ACCOUNT", "mega_old_acc")
        cls.application = build_application_runner(cls.config_path)
        cls.script_runner = cls.application.script_runner
        cls.account = cls.script_runner.config.require_account(cls.account_id)
        cls.prepare_result = cls.script_runner.prepare_account_session(account_id=cls.account_id)
        connected = build_live_runtime_bundle(
            config_account=cls.account,
            script_runner=cls.script_runner,
        )
        cls.runtime = connected.runtime
        configure_world_map_movement_budget(cls.runtime, movement_step_budget=12)
        cls.runner = connected.runner

    def test_live_world_map_movement_preparation_reports_success(self) -> None:
        """Verifies the shared preparation flow succeeded before calibration smoke begins."""

        self.assertTrue(all(step.status.value == "success" for step in self.prepare_result.steps), self.prepare_result.steps)

    def test_live_world_map_movement_calibration_smoke_runs_probe_and_sweeps(self) -> None:
        """Executes one live probe plus bounded row-major, expanding-ring, and edge-band sweeps without parser collapse."""

        world_map = self._ensure_world_map("live_world_map_movement_start")
        start_coordinate = world_map.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate
        self.assertIsNotNone(start_coordinate)
        assert start_coordinate is not None
        local_bounds = self._local_bounds_from_coordinate(start_coordinate, radius=12)
        first_checkpoint = self._first_row_major_checkpoint(
            observation=world_map,
            start_coordinate=start_coordinate,
            local_bounds=local_bounds,
        )
        current = world_map
        current = self._move_to_coordinate(current, first_checkpoint, label_prefix="live_fresh_first_checkpoint")
        current = self._move_to_coordinate(current, start_coordinate, label_prefix="live_fresh_first_checkpoint_recenter")
        lane_probe_report, current = self.runtime.world_map_movement_calibration_service.run_lane_probe_sequence(
            current,
            request=WorldMapLaneProbeRequest(
                name="live_horizontal_lane",
                anchor_coordinate=start_coordinate,
                probe_directions=(WorldMapCardinalDirection.LEFT, WorldMapCardinalDirection.RIGHT),
                distance_ratios=(0.10, 0.20),
                boundary_bounds=local_bounds,
            ),
            label_prefix="live_horizontal_lane",
        )
        probe_results = list(lane_probe_report.probe_results)
        self.assertTrue(
            all(
                result.classification
                not in {
                    WorldMapSwipeProbeClassification.PARSER_UNCERTAIN,
                    WorldMapSwipeProbeClassification.UNEXPECTED_DELTA,
                }
                for result in probe_results
            )
        )
        current = self._move_to_coordinate(current, first_checkpoint, label_prefix="live_post_probe_first_checkpoint")
        current = self._move_to_coordinate(current, start_coordinate, label_prefix="live_row_major_recenter")
        row_major, current = self.runtime.world_map_movement_calibration_service.validate_sweep(
            current,
            request=WorldMapSweepValidationRequest(
                name="live_row_major",
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.explicit_coordinate(start_coordinate),
                boundary=WorldMapSearchBoundary.rectangle(
                    min_coordinate=(local_bounds.min_x, local_bounds.min_y),
                    max_coordinate=(local_bounds.max_x, local_bounds.max_y),
                ),
                checkpoint_spacing=6,
                max_checkpoints=4,
            ),
            label_prefix="live_row_major",
        )
        current = self._move_to_coordinate(current, start_coordinate, label_prefix="live_ring_recenter")
        ring, current = self.runtime.world_map_movement_calibration_service.validate_sweep(
            current,
            request=WorldMapSweepValidationRequest(
                name="live_ring",
                pattern=WorldMapSearchPattern.expanding_ring(),
                origin=WorldMapSearchOrigin.explicit_coordinate(start_coordinate),
                boundary=WorldMapSearchBoundary.radius_from_origin(12),
                checkpoint_spacing=6,
                max_checkpoints=4,
            ),
            label_prefix="live_ring",
        )
        current = self._move_to_coordinate(current, start_coordinate, label_prefix="live_edge_recenter")
        edge, _current = self.runtime.world_map_movement_calibration_service.validate_sweep(
            current,
            request=WorldMapSweepValidationRequest(
                name="live_edge",
                pattern=WorldMapSearchPattern.edge_band_sweep(),
                origin=WorldMapSearchOrigin.map_edge_reference(WorldMapEdge.LEFT),
                boundary=WorldMapSearchBoundary.edge_band(
                    map_bounds=local_bounds,
                    band_width_units=6,
                    edges=(WorldMapEdge.LEFT, WorldMapEdge.TOP),
                ),
                checkpoint_spacing=6,
                max_checkpoints=4,
            ),
            label_prefix="live_edge",
        )

        self.assertTrue(all(result.usable_observation for result in row_major.checkpoint_results))
        self.assertTrue(all(result.usable_observation for result in ring.checkpoint_results))
        self.assertTrue(all(result.usable_observation for result in edge.checkpoint_results))
        self.assertTrue(all(result.within_tolerance for result in row_major.checkpoint_results))
        self.assertTrue(all(result.within_tolerance for result in ring.checkpoint_results))
        self.assertTrue(all(result.within_tolerance for result in edge.checkpoint_results))

    def _ensure_world_map(self, label_prefix: str) -> Observation:
        """Returns a fresh world-map observation whose spatial viewport parsed successfully."""

        return self.runner.prove_preflight_state(
            self.account,
            TaskPreflight.WORLD_MAP,
            label_prefix=label_prefix,
            max_steps=_WORLD_MAP_PREFLIGHT_MAX_STEPS,
        )

    @staticmethod
    def _is_world_map_ready(observation: Observation) -> bool:
        """Returns whether the observation is a parsed world-map surface with a usable coordinate viewport."""

        if observation.screen_type != ScreenType.PNC_WORLD_MAP or observation.spatial_surface is None:
            return False
        return (
            observation.spatial_surface.surface_type == SpatialSurfaceType.WORLD_MAP
            and observation.spatial_surface.viewport.coordinate is not None
        )

    def _move_to_coordinate(
        self,
        observation: Observation,
        coordinate: tuple[int, int],
        *,
        label_prefix: str,
    ) -> Observation:
        """Moves back to the canonical local test origin before starting the next sweep phase."""

        return self.runtime.world_map_search_service.coordinate_mover_for_runtime().move_to_coordinate(
            observation,
            target_coordinate=coordinate,
            label_prefix=label_prefix,
            runtime_state={},
        )

    @staticmethod
    def _local_bounds_from_coordinate(coordinate: tuple[int, int], *, radius: int) -> WorldMapBounds:
        """Builds one local rectangle around the original viewport for bounded sweep validation."""

        return WorldMapCoordinateDomain.puzzles_and_conquest().local_bounds_around(coordinate, radius=radius)

    def _first_row_major_checkpoint(
        self,
        *,
        observation: Observation,
        start_coordinate: tuple[int, int],
        local_bounds: WorldMapBounds,
    ) -> tuple[int, int]:
        """Returns the first bounded row-major checkpoint used for the state-sensitive live movement repro."""

        plan = self.runtime.world_map_search_service.resolve_plan(
            WorldMapSearchRequest(
                matcher=lambda _object: False,
                stop_policy=WorldMapSearchStopPolicy(max_checkpoints=4),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                checkpoint_spacing=6,
                origin=WorldMapSearchOrigin.explicit_coordinate(start_coordinate),
                boundary=WorldMapSearchBoundary.rectangle(
                    min_coordinate=(local_bounds.min_x, local_bounds.min_y),
                    max_coordinate=(local_bounds.max_x, local_bounds.max_y),
                ),
            ),
            observation,
        )
        return plan.route[0].coordinate


if __name__ == "__main__":
    unittest.main()
