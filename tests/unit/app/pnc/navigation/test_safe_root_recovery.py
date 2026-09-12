"""Safe root recovery."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import KeyEventAction, TapAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class SafeRootRecoveryTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves safe root recovery."""

    def test_return_to_safe_root_screen_unwinds_build_speedup_confirmation(self) -> None:
        """Dismisses an unconfirmed speedup popup with Android Back without consuming inventory."""

        actions = self.flows.return_to_safe_root_screen(
            make_observation(ScreenType.PNC_BUILD_SPEEDUP_CONFIRM)
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_return_to_safe_root_screen_closes_more_overlay_without_triggering_exit_popup(self) -> None:
        """Closes the live More overlay with its own toggle instead of using Android back."""

        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS),
        )

        actions = self.flows.return_to_safe_root_screen(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)

    def test_return_to_safe_root_screen_closes_more_settings_submenu_with_toggle(self) -> None:
        """Uses the More toggle to exit the live submenu state that back turns into a popup loop."""

        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(
                UiElementId.PNC_BOTTOM_NAV_MORE,
                UiElementId.PNC_MORE_SETTINGS,
                UiElementId.PNC_MORE_OVERLAY_MANAGE_CHAR,
            ),
        )

        actions = self.flows.return_to_safe_root_screen(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)

    def test_return_to_safe_root_screen_uses_top_left_back_for_fullscreen_more_settings(self) -> None:
        """Uses the visible top-left back target when the full-screen Settings page hides the More toggle."""

        observation = make_observation(
            ScreenType.PNC_SETTINGS,
            visible_ids=(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_MORE_MANAGE_CHAR),
        )

        actions = self.flows.return_to_safe_root_screen(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
