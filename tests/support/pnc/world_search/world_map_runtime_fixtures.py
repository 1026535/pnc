"""WorldMapRuntimeFixtures internal-boundary setup."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.navigation.world_map_analysis import WorldMapViewportAnalyzer
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapSearchService
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.pnc.persistence.world_map_survey_debug_store import WorldMapSurveyDebugStore
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures


class WorldMapRuntimeFixtures(WorldMapSearchFixtures):
    """Offline workflow fixture; deliberately not a TestCase."""

    def _build_runtime_service(self, *, observations: list[object]) -> tuple[WorldMapSearchService, FakeObservationService]:
        """Builds one fully wired search service backed by fake observation and action services."""

        service, observer, _session = self._build_runtime_service_bundle(observations=observations)
        return service, observer

    def _build_runtime_service_bundle(
        self,
        *,
        observations: list[object],
        logger: logging.LoggerAdapter | None = None,
    ) -> tuple[WorldMapSearchService, FakeObservationService, FakeSession]:
        """Builds one fully wired search service plus the fake session used to execute its actions."""

        runtime_logger = build_logger() if logger is None else logger
        observer = FakeObservationService(observations=observations)
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
            screen_flows=self.flows,
            observation_service=observer,
            action_executor=ObservedActionExecutor(
                selector_registry=build_default_selector_registry(),
                action_executor=ActionExecutor(
                    session=session,
                    stable_click_delay_ms=0,
                    post_action_observe_delay_ms=0,
                    chat_stable_click_delay_ms=0,
                    chat_post_action_observe_delay_ms=0,
                    logger=runtime_logger,
                    sleep=lambda _: None,
                ),
                logger=runtime_logger,
                sleep=lambda _: None,
            ),
            survey_recorder=recorder,
            viewport_analyzer=WorldMapViewportAnalyzer(observation_builder=build_p2_observation),
        )
        return service, observer, session
