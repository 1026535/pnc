"""World search readiness: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.observation import (
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.world_map_analysis import WorldMapViewportAnalyzer
from pnc_automation.app.pnc.navigation.world_map_index import WorldMapCastleQuery
from pnc_automation.app.pnc.navigation.world_map_search import (
    ObservationBackedWorldMapCastleInspector,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchService,
)
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.pnc.persistence.world_map_survey_debug_store import WorldMapSurveyDebugStore
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.counting_screen_flow_planner import _CountingScreenFlowPlanner
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchReadinessTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search readiness."""

    def test_execute_search_does_not_run_screen_flow_world_map_readiness_per_checkpoint(self) -> None:
        """Keeps checkpoint traversal inside the world-map surface after the caller supplies the entry proof."""

        flows = _CountingScreenFlowPlanner()
        observer = FakeObservationService(
            observations=[
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 0),
            ]
        )
        session = FakeSession()
        recorder = WorldMapSurveyRecorder(
            observation_service=observer,
            debug_store=WorldMapSurveyDebugStore(root=Path(self.temp_directory.name)),
        )

        def build_p2_observation(screenshot: object, _request: ObservationRequest) -> Observation:
            """Builds a distinct rich fixture observation from the exact fake P1 screenshot."""

            for capture in observer.captures:
                if capture.screenshot is screenshot:
                    return replace(capture.observation)
            raise AssertionError("P2 received a screenshot that P1 did not capture.")

        service = WorldMapSearchService(
            screen_flows=flows,
            observation_service=observer,
            action_executor=ObservedActionExecutor(
                selector_registry=build_default_selector_registry(),
                action_executor=ActionExecutor(
                    session=session,
                    stable_click_delay_ms=0,
                    post_action_observe_delay_ms=0,
                    chat_stable_click_delay_ms=0,
                    chat_post_action_observe_delay_ms=0,
                    logger=build_logger(),
                    sleep=lambda _: None,
                ),
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            survey_recorder=recorder,
            viewport_analyzer=WorldMapViewportAnalyzer(observation_builder=build_p2_observation),
        )

        service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
            ),
            label_prefix="no_checkpoint_readiness",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(flows.ensure_world_map_ready_calls, 0)

    def test_execute_search_fails_fast_when_start_observation_is_not_proven_world_map(self) -> None:
        """Requires callers to enter and prove world map before invoking the reusable search engine."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0),
            ]
        )

        with self.assertRaises(SelectorResolutionError):
            service.execute_search(
                _search_request(
                    matcher=WorldMapCastleQuery(player_name="Alice"),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    checkpoint_spacing=10,
                ),
                label_prefix="castle_search_requires_world_map",
                start_observation=make_observation(ScreenType.PNC_HOME_CITY),
            )

        self.assertEqual(len(observer.observations), 1)

    def test_castle_inspector_ensure_world_map_closes_popup_before_reentering_world_map(self) -> None:
        """Uses the shared popup-dismissal flow before attempting world-map recovery during castle inspection."""

        popup = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
        )
        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(10, 0),
            ]
        )
        inspector = ObservationBackedWorldMapCastleInspector(
            screen_flows=self.flows,
            action_executor=service.action_executor,
            observation_service=observer,
            survey_recorder=service.survey_recorder,
        )

        result = inspector._ensure_world_map(
            popup,
            label_prefix="popup_return_world",
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)

    def test_castle_inspector_ensure_world_map_recovers_unknown_world_map_chrome_before_proving_surface(self) -> None:
        """Uses the shared unknown-screen recovery flow before proving a world-map observation for castle inspection."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(12, 34),
            ]
        )
        inspector = ObservationBackedWorldMapCastleInspector(
            screen_flows=self.flows,
            action_executor=service.action_executor,
            observation_service=observer,
            survey_recorder=service.survey_recorder,
        )

        result = inspector._ensure_world_map(
            make_observation(
                ScreenType.UNKNOWN,
                visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,),
            ),
            label_prefix="unknown_return_world",
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(observer.requests, [ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP)])
