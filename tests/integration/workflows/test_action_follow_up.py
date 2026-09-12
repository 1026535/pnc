"""Action follow up: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from pnc_automation.core.errors import SelectorResolutionError

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import (
    TapAction,
    TapSpatialObjectAction,
    WaitAction,
)
from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


class ActionFollowUpTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves action follow up."""

    def test_action_executor_retries_unknown_narrow_follow_up_with_full_runtime_observation(self) -> None:
        """Promotes transient unknown results from narrow follow-ups to one broad runtime observation before returning."""

        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.UNKNOWN),
                make_observation(ScreenType.PNC_WORLD_MAP),
            ]
        )
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        result = executor.execute_actions(
            (
                WaitAction(
                    milliseconds=0,
                    reason="probe_follow_up_retry",
                    observe_after=True,
                    follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
                ),
            ),
            make_observation(ScreenType.PNC_WORLD_MAP),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(
            fake_observer.requests,
            [
                ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
                ObservationRequest.full_runtime_default(),
            ],
        )

    def test_action_executor_retries_world_map_follow_up_when_surface_parse_is_missing(self) -> None:
        """Refreshes one coarse world-map follow-up when the parsed world-map viewport is still absent."""

        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.PNC_WORLD_MAP),
                make_observation(
                    ScreenType.PNC_WORLD_MAP,
                    spatial_surface=make_spatial_surface(SpatialSurfaceType.WORLD_MAP, x=274, y=540),
                ),
            ]
        )
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        result = executor.execute_actions(
            (
                WaitAction(
                    milliseconds=0,
                    reason="probe_world_map_surface_retry",
                    observe_after=True,
                    follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
                ),
            ),
            make_observation(ScreenType.PNC_WORLD_MAP),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertIsNotNone(result.spatial_surface)
        self.assertEqual(
            fake_observer.requests,
            [
                ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
                ObservationRequest.full_runtime_default(),
            ],
        )

    def test_action_executor_stops_gathering_chain_when_resource_tap_stays_on_world_map(self) -> None:
        """Does not continue to the gather-node selector when the node tap did not prove the node screen."""

        fake_session = FakeSession()
        fake_observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_WORLD_MAP)])
        executor = _make_observed_action_executor(fake_session)
        resource_node = make_spatial_object(
            SpatialObjectKind.RESOURCE_NODE,
            name_text="Food Farm",
            metadata={"resource_type": "food"},
            action_point=(44, 55),
        )

        result = executor.execute_actions(
            (
                TapSpatialObjectAction(
                    query=SpatialObjectQuery(
                        surface_type=SpatialSurfaceType.WORLD_MAP,
                        kind=SpatialObjectKind.RESOURCE_NODE,
                        metadata_key="resource_type",
                        metadata_value="food",
                    ),
                    target_point=(44, 55),
                    reason="open_gather_node",
                    observe_after=True,
                    follow_up_request=ObservationRequest.gather_node_follow_up(),
                ),
                TapAction(selector_id=UiElementId.PNC_GATHER_BUTTON, reason="open_gather_march"),
            ),
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                spatial_surface=make_spatial_surface(SpatialSurfaceType.WORLD_MAP, objects=(resource_node,)),
            ),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(fake_session.taps, [(44, 55)])

    def test_action_executor_stops_gathering_chain_when_gather_tap_stays_on_node_screen(self) -> None:
        """Does not continue to the march-confirm selector when gather did not prove the confirm screen."""

        fake_session = FakeSession()
        fake_observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_GATHER_NODE)])
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=fake_session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        with self.assertRaises(SelectorResolutionError):
            executor.execute_actions(
                (
                    TapAction(
                        selector_id=UiElementId.PNC_GATHER_BUTTON,
                        reason="open_gather_march",
                        observe_after=True,
                        follow_up_request=ObservationRequest.march_confirm_follow_up(),
                    ),
                    TapAction(selector_id=UiElementId.PNC_MARCH_CONFIRM_BUTTON, reason="confirm_gather_march"),
                ),
                make_observation(ScreenType.PNC_GATHER_NODE, visible_ids=(UiElementId.PNC_GATHER_BUTTON,)),
                observe=fake_observer.observe,
            )

        self.assertEqual(fake_session.taps, [])
