"""Opt-in live smoke tests for spatial-surface world-map navigation."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from pnc_automation.app import build_application_runner
from pnc_automation.app.pnc.domain.observation import Observation, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldCoordinate
from tests.live_smoke_support import build_live_automation_runner, execute_live_flow_until


def _live_smoke_enabled() -> bool:
    """Returns whether the explicit live-smoke opt-in flag is enabled."""

    return os.getenv("PNC_RUN_LIVE_SMOKE") == "1"


@unittest.skipUnless(_live_smoke_enabled(), "Set PNC_RUN_LIVE_SMOKE=1 to run live smoke tests.")
class LiveSpatialSurfaceSmokeTests(unittest.TestCase):
    """Runs minimal live smoke coverage for the world-map spatial-surface slice."""

    @classmethod
    def setUpClass(cls) -> None:
        """Prepares the configured live account session and builds one automation runner for direct flow execution."""

        cls.config_path = Path(os.getenv("PNC_LIVE_SMOKE_CONFIG", "config/accounts.yaml"))
        cls.account_id = os.getenv("PNC_LIVE_SMOKE_ACCOUNT", "testing")
        cls.world_delta_x = int(os.getenv("PNC_LIVE_SMOKE_WORLD_DELTA_X", "12"))
        cls.application = build_application_runner(cls.config_path)
        cls.script_runner = cls.application.script_runner
        cls.account = cls.script_runner.config.require_account(cls.account_id)
        cls.prepare_result = cls.script_runner.prepare_account_session(account_id=cls.account_id)
        cls.runner = build_live_automation_runner(
            config_account=cls.account,
            script_runner=cls.script_runner,
        )

    def test_live_spatial_smoke_preparation_reports_success(self) -> None:
        """Verifies the shared account-session preparation path completed without task failures."""

        self.assertTrue(all(step.status.value == "success" for step in self.prepare_result.steps), self.prepare_result.steps)

    def test_live_spatial_smoke_round_trips_home_city_world_map_home_city(self) -> None:
        """Verifies the live runtime can enter the world map with a readable spatial surface and return home safely."""

        home_before = self._ensure_home_city("live_spatial_round_trip_home_before")
        world_map = self._ensure_world_map("live_spatial_round_trip_world")
        home_after = execute_live_flow_until(
            runner=self.runner,
            start_observation=world_map,
            label_prefix="live_spatial_round_trip_home_after",
            planner=self.runner.flow_planner.return_home_city_from_world_map,
            done=lambda observation: observation.screen_type == ScreenType.PNC_HOME_CITY,
        )

        self.assertEqual(home_before.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertTrue(self._is_world_map_ready(world_map), world_map)
        self.assertEqual(home_after.screen_type, ScreenType.PNC_HOME_CITY)

    def test_live_spatial_smoke_coordinate_navigation_moves_the_world_viewport(self) -> None:
        """Verifies one flow-planned coordinate-navigation increment changes the observed world viewport."""

        world_before = self._ensure_world_map("live_spatial_coordinate_before")
        surface_before = world_before.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        before_coordinate = surface_before.viewport.coordinate
        self.assertIsNotNone(before_coordinate)
        assert before_coordinate is not None
        target = WorldCoordinate(x=before_coordinate[0] + self.world_delta_x, y=before_coordinate[1])
        runtime_state: dict[str, object] = {}
        world_after = execute_live_flow_until(
            runner=self.runner,
            start_observation=world_before,
            label_prefix="live_spatial_coordinate_move",
            planner=lambda observation: self.runner.flow_planner.focus_world_coordinate(
                observation,
                target,
                runtime_state=runtime_state,
            ),
            done=lambda observation: self._is_world_map_ready(observation)
            and observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate != before_coordinate,
            max_steps=4,
        )
        after_coordinate = world_after.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate

        self.assertIsNotNone(after_coordinate)
        self.assertNotEqual(after_coordinate, before_coordinate)
        self._ensure_home_city("live_spatial_coordinate_cleanup")

    def _ensure_home_city(self, label_prefix: str) -> Observation:
        """Returns a fresh home-city observation using the canonical shared root-navigation flow."""

        return execute_live_flow_until(
            runner=self.runner,
            label_prefix=label_prefix,
            planner=self.runner.flow_planner.ensure_home_city,
            done=lambda observation: observation.screen_type == ScreenType.PNC_HOME_CITY,
        )

    def _ensure_world_map(self, label_prefix: str) -> Observation:
        """Returns a fresh world-map observation whose spatial viewport parsed successfully."""

        return execute_live_flow_until(
            runner=self.runner,
            label_prefix=label_prefix,
            planner=self.runner.flow_planner.ensure_world_map_ready,
            done=self._is_world_map_ready,
        )

    @staticmethod
    def _is_world_map_ready(observation: Observation) -> bool:
        """Returns whether the observation is a parsed world-map surface with a readable coordinate viewport."""

        if observation.screen_type != ScreenType.PNC_WORLD_MAP or observation.spatial_surface is None:
            return False
        return (
            observation.spatial_surface.surface_type == SpatialSurfaceType.WORLD_MAP
            and observation.spatial_surface.viewport.coordinate is not None
        )


if __name__ == "__main__":
    unittest.main()
