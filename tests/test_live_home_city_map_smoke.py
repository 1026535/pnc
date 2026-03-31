"""Opt-in live smoke tests for atlas-backed home-city building opening."""

from __future__ import annotations

import os
import random
import unittest
from pathlib import Path

from pnc_automation.app import build_application_runner
from pnc_automation.automation.task import TaskStatus
from pnc_automation.automation.tasks.open_building_support import (
    home_city_object_query,
    requested_home_city_object_observation_matches,
)
from pnc_automation.pnc.building_catalog import HomeCityMapCoordinate, HomeCityObjectId, home_city_map_atlas
from pnc_automation.config.models import CastleIdentity
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_type import ScreenType
from tests.live_smoke_support import build_live_automation_runner, execute_live_flow_until


def _live_home_city_map_smoke_enabled() -> bool:
    """Returns whether the explicit atlas-backed live smoke coverage was enabled by the operator."""

    return os.getenv("PNC_RUN_LIVE_HOME_CITY_MAP_SMOKE") == "1"


@unittest.skipUnless(
    _live_home_city_map_smoke_enabled(),
    "Set PNC_RUN_LIVE_HOME_CITY_MAP_SMOKE=1 to run home-city atlas smoke tests.",
)
class LiveHomeCityMapSmokeTests(unittest.TestCase):
    """Verifies the static home-city atlas can reopen known buildings from randomized viewport starts."""

    @classmethod
    def setUpClass(cls) -> None:
        """Builds the shared live runtime services once for the smoke suite."""

        cls.config_path = Path(os.getenv("PNC_LIVE_SMOKE_CONFIG", "config/accounts.yaml"))
        cls.random_seed = int(os.getenv("PNC_LIVE_HOME_CITY_MAP_SMOKE_SEED", "29"))
        cls.application = build_application_runner(cls.config_path)
        cls.script_runner = cls.application.script_runner

    def test_live_home_city_map_preparation_reports_success(self) -> None:
        """Verifies each requested live account can complete the shared preparation flow."""

        for account_id in self._live_account_ids():
            with self.subTest(account_id=account_id):
                _, prepare_result = self._prepare_runtime(account_id)
                self.assertTrue(all(step.status == TaskStatus.SUCCESS for step in prepare_result.steps), prepare_result.steps)

    def test_live_home_city_map_can_open_each_recorded_building_from_randomized_starts(self) -> None:
        """Moves to randomized atlas centers, then proves each requested building can still be opened cleanly."""

        for account_index, account_id in enumerate(self._live_account_ids()):
            with self.subTest(account_id=account_id):
                runner, prepare_result = self._prepare_runtime(account_id)
                self.assertTrue(all(step.status == TaskStatus.SUCCESS for step in prepare_result.steps), prepare_result.steps)
                rng = random.Random(self.random_seed + account_index)
                current = self._ensure_home_city(runner=runner, label_prefix=f"{account_id}_live_home_city_atlas_start")
                runtime_state: dict[str, object] = {}
                for target in self._smoke_targets():
                    with self.subTest(account_id=account_id, building=target.value):
                        runtime_state.clear()
                        current = self._randomize_home_city_view(
                            runner=runner,
                            observation=current,
                            rng=rng,
                            runtime_state=runtime_state,
                            label_prefix=f"{account_id}_live_home_city_atlas_random_{target.value}",
                        )
                        current = self._open_requested_home_city_object(
                            runner=runner,
                            observation=current,
                            target=target,
                            runtime_state=runtime_state,
                            label_prefix=f"{account_id}_live_home_city_atlas_open_{target.value}",
                        )
                        current = self._ensure_home_city(
                            runner=runner,
                            label_prefix=f"{account_id}_live_home_city_atlas_cleanup_{target.value}",
                        )

    def _ensure_home_city(self, *, runner: object, label_prefix: str) -> Observation:
        """Returns a fresh home-city observation using the shared root-navigation flow."""

        return execute_live_flow_until(
            runner=runner,
            label_prefix=label_prefix,
            planner=runner.flow_planner.ensure_home_city,
            done=lambda observation: observation.screen_type == ScreenType.PNC_HOME_CITY,
        )

    def _randomize_home_city_view(
        self,
        *,
        runner: object,
        observation: Observation,
        rng: random.Random,
        runtime_state: dict[str, object],
        label_prefix: str,
    ) -> Observation:
        """Moves to one random atlas-backed viewport center so the next open-building proof starts from a non-root view."""

        target_coordinate = self._random_home_city_coordinate(rng)
        actions = runner.flow_planner.focus_home_city_coordinate(
            observation,
            target_coordinate,
            runtime_state=runtime_state,
        )
        if not actions:
            return observation
        execution = runner.action_executor.execute_actions(
            actions,
            observation,
            observe=lambda label, request=None: runner.observation_service.observe(
                f"{label_prefix}_{label}",
                request,
            ),
        )
        current = execution.observation
        if current.screen_type != ScreenType.PNC_HOME_CITY or current.blocking_popup:
            return self._ensure_home_city(
                runner=runner,
                label_prefix=f"{label_prefix}_recover",
            )
        return current

    def _open_requested_home_city_object(
        self,
        *,
        runner: object,
        observation: Observation,
        target: HomeCityObjectId,
        runtime_state: dict[str, object],
        label_prefix: str,
    ) -> Observation:
        """Opens one requested home-city building using the shared atlas flow while preserving the known viewport center."""

        return execute_live_flow_until(
            runner=runner,
            label_prefix=label_prefix,
            start_observation=observation,
            planner=lambda current: runner.flow_planner.open_home_city_object(
                current,
                home_city_object_query(target),
                reason=f"open_{target.value}_for_live_smoke",
                runtime_state=runtime_state,
            ),
            done=lambda current: requested_home_city_object_observation_matches(current, target),
            max_steps=10,
        )

    @classmethod
    def _prepare_runtime(cls, account_id: str) -> tuple[object, object]:
        """Builds one live runner and prepares the account at its authored main castle when available."""

        account = cls.script_runner.config.require_account(account_id)
        runner = build_live_automation_runner(
            config_account=account,
            script_runner=cls.script_runner,
        )
        prepare_result = cls.application.prepare_account_session(
            account_id=account_id,
            castle=cls._main_castle_target(account_id),
        )
        return runner, prepare_result

    @classmethod
    def _main_castle_target(cls, account_id: str) -> CastleIdentity | None:
        """Returns the authored main-castle target for one live smoke account when it exists."""

        castle_targets = cls.script_runner.config.find_castle_targets(account_id)
        return None if castle_targets is None else castle_targets.find("main")

    @staticmethod
    def _live_account_ids() -> tuple[str, ...]:
        """Returns the explicit live accounts requested for the smoke run."""

        raw_value = os.getenv("PNC_LIVE_HOME_CITY_MAP_SMOKE_ACCOUNTS", "testing,mega_old_acc")
        return tuple(account_id.strip() for account_id in raw_value.split(",") if account_id.strip())

    @staticmethod
    def _random_home_city_coordinate(rng: random.Random) -> HomeCityMapCoordinate:
        """Returns one random valid atlas center used to start one building-open smoke from a non-root viewport."""

        atlas = home_city_map_atlas()
        half_viewport_width = atlas.viewport_width_units // 2
        half_viewport_height = atlas.viewport_height_units // 2
        return HomeCityMapCoordinate(
            x=rng.randint(half_viewport_width, atlas.width_units - half_viewport_width),
            y=rng.randint(half_viewport_height, atlas.height_units - half_viewport_height),
        )

    @staticmethod
    def _smoke_targets() -> tuple[HomeCityObjectId, ...]:
        """Returns the exact authored building list that must open from randomized home-city starts."""

        default_targets = (
            HomeCityObjectId.CASTLE,
            HomeCityObjectId.WALL,
            HomeCityObjectId.INSTITUTE,
            HomeCityObjectId.WAREHOUSE,
            HomeCityObjectId.TRAP_WORKSHOP,
            HomeCityObjectId.WATCHTOWER,
            HomeCityObjectId.SAUROI_LAIR,
            HomeCityObjectId.CAMPAIGN,
            HomeCityObjectId.ARENA,
            HomeCityObjectId.ALLIANCE_HALL,
            HomeCityObjectId.BLACKSMITH,
            HomeCityObjectId.MARKET,
            HomeCityObjectId.GODDESS_STATUE,
            HomeCityObjectId.TOWER_OF_TRIAL,
            HomeCityObjectId.BANK,
            HomeCityObjectId.SANCTUM,
            HomeCityObjectId.RANGED_BARRACKS,
            HomeCityObjectId.INFANTRY_BARRACKS,
            HomeCityObjectId.CAVALRY_BARRACKS,
            HomeCityObjectId.SIEGE_FACTORY,
            HomeCityObjectId.HERO_HALL,
            HomeCityObjectId.HALL_OF_WAR,
            HomeCityObjectId.SACRED_TREE,
            HomeCityObjectId.PIT,
            HomeCityObjectId.DRAGONDOM_CONQUEST,
        )
        raw_value = os.getenv("PNC_LIVE_HOME_CITY_MAP_SMOKE_TARGETS")
        if raw_value is None:
            return default_targets
        requested_targets = tuple(HomeCityObjectId(item.strip()) for item in raw_value.split(",") if item.strip())
        return requested_targets


if __name__ == "__main__":
    unittest.main()
