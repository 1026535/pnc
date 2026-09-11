"""Opt-in live smoke tests for spatial-surface world-map navigation."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.script_runner import require_successful_preparation
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.authoring.config.models import LiveAutomationRole
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
        cls.account.require_live_role(LiveAutomationRole.SMOKE_TEST)
        cls.lease_bundle = cls.script_runner.reserve_accounts((cls.account_id,))
        cls.addClassCleanup(cls.lease_bundle.close)
        cls.prepare_result = require_successful_preparation(
            cls.script_runner.prepare_account_session(
                account_id=cls.account_id,
                required_role=LiveAutomationRole.SMOKE_TEST,
            )
        )
        cls.runner = build_live_automation_runner(
            config_account=cls.account,
            script_runner=cls.script_runner,
        )
        cls.addClassCleanup(cls.runner.close)

    @classmethod
    def tearDownClass(cls) -> None:
        """Releases the shared automation runner after the smoke suite."""

        runner = getattr(cls, "runner", None)
        if runner is not None:
            runner.close()

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
            planner=lambda observation: self.runner.flow_planner.world_map_navigator.plan_focus_coordinate(
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


@unittest.skipIf(_live_smoke_enabled(), "Offline smoke setup proofs are disabled during live smoke runs.")
class SpatialSurfaceSmokeSetupTests(unittest.TestCase):
    """Proves smoke setup gates role and preparation before dependent runtime construction."""

    def test_wrong_role_is_rejected_before_reservation_or_preparation(self) -> None:
        """A role mismatch must not acquire a lease or prepare the account."""

        self.addCleanup(LiveSpatialSurfaceSmokeTests.doClassCleanups)
        account = SimpleNamespace(require_live_role=Mock(side_effect=PermissionError("wrong role")))
        config = SimpleNamespace(require_account=Mock(return_value=account))
        script_runner = SimpleNamespace(
            config=config,
            reserve_accounts=Mock(),
            prepare_account_session=Mock(),
        )
        application = SimpleNamespace(script_runner=script_runner)

        with tempfile.TemporaryDirectory() as directory:
            missing_config = Path(directory) / "deliberately-missing-accounts.yaml"
            with (
                patch.dict(os.environ, {"PNC_LIVE_SMOKE_CONFIG": str(missing_config)}),
                patch.object(sys.modules[__name__], "build_application_runner", return_value=application) as build,
            ):
                with self.assertRaises(PermissionError):
                    LiveSpatialSurfaceSmokeTests.setUpClass()
            build.assert_called_once_with(missing_config)

        script_runner.reserve_accounts.assert_not_called()
        script_runner.prepare_account_session.assert_not_called()

    def test_failed_preparation_runs_class_cleanup_for_reservation(self) -> None:
        """A preparation RunResult failure closes the class reservation immediately."""

        self.addCleanup(LiveSpatialSurfaceSmokeTests.doClassCleanups)
        class TrackedReservation:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        reservation = TrackedReservation()
        account = SimpleNamespace(require_live_role=Mock())
        config = SimpleNamespace(require_account=Mock(return_value=account))
        failed_result = RunResult(
            account_id="testing",
            script_name="prepare",
            steps=(
                StepRunResult(
                    task_id=TaskId.LOGIN,
                    status=TaskStatus.FAILED,
                    attempts=1,
                    message="offline fixture failure",
                ),
            ),
            started_at=datetime.now(tz=UTC),
            finished_at=datetime.now(tz=UTC),
        )
        script_runner = SimpleNamespace(
            config=config,
            reserve_accounts=Mock(return_value=reservation),
            prepare_account_session=Mock(return_value=failed_result),
        )
        application = SimpleNamespace(script_runner=script_runner)

        with tempfile.TemporaryDirectory() as directory:
            missing_config = Path(directory) / "deliberately-missing-accounts.yaml"
            with (
                patch.dict(os.environ, {"PNC_LIVE_SMOKE_CONFIG": str(missing_config)}),
                patch.object(sys.modules[__name__], "build_application_runner", return_value=application) as build,
            ):
                with self.assertRaises(RuntimeError):
                    LiveSpatialSurfaceSmokeTests.setUpClass()
            build.assert_called_once_with(missing_config)
            LiveSpatialSurfaceSmokeTests.doClassCleanups()

        self.assertTrue(reservation.closed)
        script_runner.prepare_account_session.assert_called_once()


if __name__ == "__main__":
    unittest.main()
