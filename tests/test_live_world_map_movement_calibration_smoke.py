"""Opt-in live smoke tests for world-map movement calibration on a real account."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from pnc_automation.app import build_application_runner
from pnc_automation.app.pnc.domain.observation import Observation, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.automation.engine.task import TaskPreflight
from pnc_automation.app.pnc.navigation.world_map_movement_calibration import (
    WorldMapSwipeProbeClassification,
    WorldMapSweepValidationRequest,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapEdge,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
)
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldMapCardinalDirection
from tests.live_smoke_support import build_live_automation_runner

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
        cls.runtime = cls.script_runner.build_connected_runtime(account=cls.account)
        cls.runtime.world_map_movement_calibration_service.movement_step_budget = 12
        cls.runner = build_live_automation_runner(
            config_account=cls.account,
            script_runner=cls.script_runner,
        )

    def test_live_world_map_movement_preparation_reports_success(self) -> None:
        """Verifies the shared preparation flow succeeded before calibration smoke begins."""

        self.assertTrue(all(step.status.value == "success" for step in self.prepare_result.steps), self.prepare_result.steps)

    def test_live_world_map_movement_calibration_smoke_runs_probe_and_sweeps(self) -> None:
        """Executes one live probe plus bounded row-major, expanding-ring, and edge-band sweeps without parser collapse."""

        world_map = self._ensure_world_map("live_world_map_movement_start")
        probe_results: list[object] = []
        current = world_map
        for ratio in (0.10, 0.20):
            probe_result, current = self.runtime.world_map_movement_calibration_service.probe_swipe(
                current,
                direction=WorldMapCardinalDirection.LEFT,
                distance_ratio=ratio,
                label_prefix=f"live_world_map_probe_left_{str(ratio).replace('.', '_')}",
            )
            probe_results.append(probe_result)
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
        row_major, current = self.runtime.world_map_movement_calibration_service.validate_sweep(
            current,
            request=WorldMapSweepValidationRequest(
                name="live_row_major",
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.radius_from_origin(12),
                checkpoint_spacing=6,
                max_checkpoints=4,
            ),
            label_prefix="live_row_major",
        )
        ring, current = self.runtime.world_map_movement_calibration_service.validate_sweep(
            current,
            request=WorldMapSweepValidationRequest(
                name="live_ring",
                pattern=WorldMapSearchPattern.expanding_ring(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.radius_from_origin(12),
                checkpoint_spacing=6,
                max_checkpoints=4,
            ),
            label_prefix="live_ring",
        )
        edge, _current = self.runtime.world_map_movement_calibration_service.validate_sweep(
            current,
            request=WorldMapSweepValidationRequest(
                name="live_edge",
                pattern=WorldMapSearchPattern.edge_band_sweep(),
                origin=WorldMapSearchOrigin.map_edge_reference(WorldMapEdge.LEFT),
                boundary=WorldMapSearchBoundary.edge_band(
                    map_bounds=self._local_bounds(current, radius=12),
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

    @staticmethod
    def _local_bounds(observation: Observation, *, radius: int) -> object:
        """Builds one local rectangle around the current viewport for bounded edge-band validation."""

        coordinate = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate
        assert coordinate is not None
        from pnc_automation.app.pnc.navigation.world_map_search import WorldMapBounds

        return WorldMapBounds(
            min_x=max(0, coordinate[0] - radius),
            min_y=max(0, coordinate[1] - radius),
            max_x=coordinate[0] + radius,
            max_y=coordinate[1] + radius,
        )


if __name__ == "__main__":
    unittest.main()
