"""Unknown root recovery."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import KeyEventAction, TapAction, WaitAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class UnknownRootRecoveryTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves unknown root recovery."""

    def test_recover_unknown_game_screen_refreshes_world_map_when_world_home_nav_is_visible(self) -> None:
        """Uses a safe re-observe instead of backing out when unknown state still exposes world-map chrome."""

        actions = self.flows.recover_unknown_game_screen(
            make_observation(ScreenType.UNKNOWN, visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,)),
            reason="recover_unknown_world_map",
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].milliseconds, 250)
        self.assertEqual(actions[0].reason, "refresh_unknown_world_map")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP))

    def test_recover_unknown_game_screen_refreshes_home_city_when_world_switch_is_visible(self) -> None:
        """Uses a safe re-observe instead of backing out when unknown state still exposes home-city chrome."""

        actions = self.flows.recover_unknown_game_screen(
            make_observation(ScreenType.UNKNOWN, visible_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,)),
            reason="recover_unknown_home_city",
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].milliseconds, 250)
        self.assertEqual(actions[0].reason, "refresh_unknown_home_city")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY))

    def test_recover_unknown_game_screen_refreshes_game_root_when_shared_bottom_nav_is_visible(self) -> None:
        """Uses a generic re-observe instead of backing out when the shared in-game root chrome is already visible."""

        actions = self.flows.recover_unknown_game_screen(
            make_observation(
                ScreenType.UNKNOWN,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_HOME, UiElementId.PNC_BOTTOM_NAV_MORE),
            ),
            reason="recover_unknown_root",
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].milliseconds, 250)
        self.assertEqual(actions[0].reason, "refresh_unknown_game_root")
        self.assertIsNone(actions[0].follow_up_request)

    def test_open_world_map_from_unknown_only_recovers_toward_home_city_first(self) -> None:
        """Plans a single recovery increment from unknown instead of bundling a stale world-switch tail action."""

        actions = self.flows.open_world_map(make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_open_chat_from_unknown_only_recovers_toward_home_city_first(self) -> None:
        """Plans a single recovery increment from unknown instead of assuming the chat shortcut is already reachable."""

        actions = self.flows.open_chat(make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_open_chat_from_world_map_uses_shared_shortcut(self) -> None:
        """Uses the shared chat shortcut instead of forcing a return to home city first."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )

        actions = self.flows.open_chat(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_SHORTCUT)
