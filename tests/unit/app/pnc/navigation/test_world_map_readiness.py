"""World map readiness."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import KeyEventAction, TapAction, WaitAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class WorldMapReadinessTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves world map readiness."""

    def test_ensure_world_map_ready_refreshes_when_world_map_surface_parse_is_temporarily_missing(self) -> None:
        """Requests one bounded re-observation instead of failing when the coarse world-map screen is visible but the parsed viewport is absent."""

        actions = self.flows.ensure_world_map_ready(make_observation(ScreenType.PNC_WORLD_MAP))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].milliseconds, 250)
        self.assertEqual(actions[0].reason, "refresh_world_map_surface")
        self.assertTrue(actions[0].observe_after)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP))

    def test_ensure_world_map_ready_proves_coarse_world_map_root_before_treating_it_as_ready(self) -> None:
        """Refreshes a coarse world-map root into an exact viewport proof instead of treating it as already ready."""

        actions = self.flows.ensure_world_map_ready(
            make_observation(
                ScreenType.PNC_WORLD_MAP_ROOT,
                visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_COORDINATE_BAR),
            )
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP))

    def test_ensure_world_map_ready_closes_coordinate_dialog_before_retrying_entry(self) -> None:
        """Returns to the map from the live coordinate dialog instead of bouncing through home-city recovery."""

        observation = make_observation(
            ScreenType.PNC_WORLD_COORDINATE_DIALOG,
            visible_ids=(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON,),
        )

        actions = self.flows.ensure_world_map_ready(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_coordinate_jump_follow_up())

    def test_ensure_world_map_ready_closes_overview_before_retrying_entry(self) -> None:
        """Treats world-map overview as a transient overlay on the way back to a proven map surface."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP_OVERVIEW,
            visible_ids=(UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON,),
        )

        actions = self.flows.ensure_world_map_ready(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_overview_exit_follow_up())

    def test_ensure_world_map_ready_leaves_kingdom_list_with_back_before_retrying_entry(self) -> None:
        """Treats kingdom list as an overview child state that must unwind back toward world map first."""

        observation = make_observation(ScreenType.PNC_WORLD_KINGDOM_LIST)

        actions = self.flows.ensure_world_map_ready(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_overview_exit_follow_up())
