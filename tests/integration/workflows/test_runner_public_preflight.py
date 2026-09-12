"""Runner public preflight: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
from pnc_automation.app.automation.engine.task import TaskPreflight
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
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


class RunnerPublicPreflightTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves runner public preflight."""

    def test_runner_public_preflight_helper_proves_world_map_for_external_callers(self) -> None:
        """Exposes the same runner-owned world-map preflight proof to live tools instead of forcing ad hoc loops."""

        registry = build_default_task_registry()
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

        result = runner.prove_preflight_state(
            self.account,
            TaskPreflight.WORLD_MAP,
            label_prefix="external_world_map_preflight",
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(fake_observer.requests[1], ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP))
        self.assertEqual(fake_session.taps, [])

    def test_runner_public_preflight_helper_recovers_unknown_world_map_surface_for_external_callers(self) -> None:
        """Keeps the external preflight helper on the same unknown-screen recovery path as the live smoke loop."""

        registry = build_default_task_registry()
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.UNKNOWN,
                    visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,),
                ),
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

        result = runner.prove_preflight_state(
            self.account,
            TaskPreflight.WORLD_MAP,
            label_prefix="external_world_map_unknown_preflight",
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(
            fake_observer.requests[1:3],
            [
                ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
                ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
            ],
        )
        self.assertEqual(fake_session.taps, [])

    def test_runner_public_preflight_helper_accepts_a_larger_external_step_budget(self) -> None:
        """Allows standalone live tools to request a larger preflight budget than the in-script task default."""

        registry = build_default_task_registry()
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.PNC_POPUP, visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,)),
                make_observation(ScreenType.UNKNOWN, visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,)),
                make_observation(ScreenType.PNC_WORLD_MAP_ROOT, visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_COORDINATE_BAR)),
                make_observation(ScreenType.PNC_WORLD_MAP_ROOT, visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_COORDINATE_BAR)),
                make_observation(ScreenType.PNC_WORLD_MAP_ROOT, visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_COORDINATE_BAR)),
                make_observation(ScreenType.PNC_WORLD_MAP_ROOT, visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_COORDINATE_BAR)),
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

        result = runner.prove_preflight_state(
            self.account,
            TaskPreflight.WORLD_MAP,
            label_prefix="external_world_map_extended_budget",
            max_steps=6,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(fake_session.taps, [(5, 5)])
