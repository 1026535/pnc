"""Runner preflight: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_surface
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)
from tests.support.automation.engine.home_city_preflight_task import _HomeCityPreflightTask
from tests.support.automation.engine.trivial_tap_task import _TrivialTapTask
from tests.support.automation.engine.world_map_preflight_task import _WorldMapPreflightTask
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


class RunnerPreflightTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves runner preflight."""

    def test_runner_executes_observe_click_reobserve_verify_loop_for_trivial_task(self) -> None:
        """Exercises the minimal generic runner loop with one synthetic tap task."""

        registry = TaskRegistry(tasks=(_TrivialTapTask(),))
        script = registry.prepare_script(
            RunScript(
                name="trivial",
                path=Path("trivial.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,)),
                make_observation(ScreenType.PNC_BUILDING_DETAILS),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=_make_observed_action_executor(fake_session),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        result = runner.run(self.account, script)

        self.assertEqual(result.steps[0].status.value, "success")
        self.assertEqual(fake_observer.labels, ["ensure_game_running_before", "ensure_game_running_post_action_1"])
        self.assertEqual(fake_session.taps, [(5, 5)])

    def test_runner_proves_home_city_preflight_before_task_body_starts(self) -> None:
        """Uses the shared runner preflight to prove home city before the task body executes."""

        registry = TaskRegistry(tasks=(_HomeCityPreflightTask(),))
        script = registry.prepare_script(
            RunScript(
                name="home_city_preflight",
                path=Path("home_city_preflight.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.PNC_WORLD_MAP, visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,)),
                make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,)),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=_make_observed_action_executor(fake_session),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        result = runner.run(self.account, script)

        self.assertEqual(result.steps[0].status.value, "success")
        self.assertEqual(fake_observer.labels, ["ensure_game_running_before", "ensure_game_running_post_action_1"])
        self.assertEqual(fake_session.taps, [(5, 5)])

    def test_runner_recovers_required_update_before_proving_task_preflight(self) -> None:
        """Makes required-update recovery available to every runner task before task planning."""

        registry = TaskRegistry(tasks=(_HomeCityPreflightTask(),))
        script = registry.prepare_script(
            RunScript(
                name="update_before_preflight",
                path=Path("update_before_preflight.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_POPUP,
                    visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
                    blocking_popup=True,
                ),
                make_observation(ScreenType.PNC_LOADING),
                make_observation(ScreenType.PNC_HOME_CITY),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=_make_observed_action_executor(fake_session),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        result = runner.run(self.account, script)

        self.assertEqual(result.steps[0].status.value, "success")
        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(
            fake_observer.labels,
            [
                "ensure_game_running_before",
                "ensure_game_running_ensure_game_running_preflight_update_wait_1",
                "ensure_game_running_ensure_game_running_preflight_update_wait_2",
            ],
        )

    def test_runner_does_not_replay_task_action_interrupted_by_required_update(self) -> None:
        """Returns Home but fails an ambiguous task increment instead of replaying its action."""

        registry = TaskRegistry(tasks=(_TrivialTapTask(),))
        script = registry.prepare_script(
            RunScript(
                name="update_after_action",
                path=Path("update_after_action.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                ),
                make_observation(
                    ScreenType.PNC_POPUP,
                    visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
                    blocking_popup=True,
                ),
                make_observation(ScreenType.PNC_LOADING),
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    artifact_path=Path("update-recovered-home.png"),
                ),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=_make_observed_action_executor(fake_session),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        with self.assertRaisesRegex(TaskVerificationError, "will not be replayed"):
            runner.run(self.account, script)

        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])

    def test_runner_proves_world_map_preflight_from_coarse_world_root_before_task_body_starts(self) -> None:
        """Uses the shared runner preflight to refine one coarse world-map root into an exact world map."""

        registry = TaskRegistry(tasks=(_WorldMapPreflightTask(),))
        script = registry.prepare_script(
            RunScript(
                name="world_map_preflight",
                path=Path("world_map_preflight.yaml"),
                steps=(ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),),
            )
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_WORLD_MAP_ROOT,
                    visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_COORDINATE_BAR),
                ),
                make_observation(
                    ScreenType.PNC_WORLD_MAP,
                    spatial_surface=make_spatial_surface(SpatialSurfaceType.WORLD_MAP, x=292, y=540),
                ),
            ]
        )
        fake_session = FakeSession()
        runner = AutomationRunner(
            defaults=self.defaults,
            observation_service=fake_observer,
            action_executor=_make_observed_action_executor(fake_session),
            task_registry=registry,
            flow_planner=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        result = runner.run(self.account, script)

        self.assertEqual(result.steps[0].status.value, "success")
        self.assertEqual(fake_observer.labels, ["ensure_game_running_before", "ensure_game_running_post_action_1"])
        self.assertEqual(fake_observer.requests[1], ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP))
        self.assertEqual(fake_session.taps, [])
