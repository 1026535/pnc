"""Home city readiness."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import KeyEventAction, TapAction, WaitAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class HomeCityReadinessTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city readiness."""

    def test_ensure_home_city_from_world_map_uses_world_home_nav(self) -> None:
        """Ensures the reusable flow maps world map back to city with one canonical selector."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_SEARCH_BUTTON),
        )

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_WORLD_HOME_NAV)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.home_city_follow_up(ScreenType.PNC_WORLD_MAP))

    def test_ensure_home_city_from_world_coordinate_dialog_closes_dialog_first(self) -> None:
        """Unwinds the coordinate dialog back to world map before any later city-return step."""

        observation = make_observation(
            ScreenType.PNC_WORLD_COORDINATE_DIALOG,
            visible_ids=(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON,),
        )

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_coordinate_jump_follow_up())

    def test_ensure_home_city_from_alliance_join_uses_back_navigation(self) -> None:
        """Treats the join-alliance landing as a back-navigable root-adjacent screen."""

        observation = make_observation(ScreenType.PNC_ALLIANCE_JOIN)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.home_city_follow_up(ScreenType.PNC_ALLIANCE_JOIN))

    def test_ensure_home_city_from_castle_selection_uses_back_navigation(self) -> None:
        """Treats the Manage Char roster as a back-navigable root-adjacent screen."""

        observation = make_observation(ScreenType.PNC_CASTLE_SELECTION)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_ensure_home_city_from_daily_to_do_uses_back_navigation(self) -> None:
        """Treats the Daily To-Do overlay as a dismissible back-navigable screen."""

        observation = make_observation(ScreenType.PNC_DAILY_TO_DO)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_ensure_home_city_from_build_queue_uses_back_navigation(self) -> None:
        """Treats the build queue overlay as a dismissible home-adjacent screen."""

        observation = make_observation(ScreenType.PNC_BUILD_QUEUE)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_ensure_home_city_waits_on_loading_instead_of_pressing_back(self) -> None:
        """Keeps launch/loading states from opening the exit-game confirmation during preflight."""

        actions = self.flows.ensure_home_city(make_observation(ScreenType.PNC_LOADING))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].reason, "wait_for_game_loading")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.full_runtime_default())

    def test_ensure_home_city_from_unknown_uses_in_game_recovery_without_relaunching(self) -> None:
        """Keeps ambiguous states inside the bounded in-game recovery path instead of bouncing through Android home."""

        actions = self.flows.ensure_home_city(make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")
        self.assertEqual(actions[0].reason, "recover_unknown_home_city")

    def test_ensure_home_city_proves_coarse_home_city_root_before_treating_it_as_ready(self) -> None:
        """Refreshes a coarse home-city root into an exact home-city proof instead of treating it as already ready."""

        actions = self.flows.ensure_home_city(
            make_observation(ScreenType.PNC_HOME_CITY_ROOT, visible_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,))
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY))
