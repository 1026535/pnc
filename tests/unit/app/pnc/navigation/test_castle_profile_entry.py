"""Castle profile entry."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class CastleProfileEntryTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves castle profile entry."""

    def test_open_castle_selection_uses_more_then_settings_then_manage_char(self) -> None:
        """Uses the live More-overlay path through Settings before entering Manage Char."""

        home_observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
        )
        more_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
        )
        settings_observation = make_observation(
            ScreenType.PNC_SETTINGS,
            visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,),
        )

        home_actions = self.flows.open_castle_selection(home_observation)
        more_actions = self.flows.open_castle_selection(more_observation)
        settings_actions = self.flows.open_castle_selection(settings_observation)

        self.assertEqual(len(home_actions), 3)
        self.assertIsInstance(home_actions[0], TapAction)
        self.assertEqual(home_actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(home_actions[1], TapAction)
        self.assertEqual(home_actions[1].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(home_actions[2], TapAction)
        self.assertEqual(home_actions[2].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)
        self.assertEqual(len(more_actions), 2)
        self.assertIsInstance(more_actions[0], TapAction)
        self.assertEqual(more_actions[0].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(more_actions[1], TapAction)
        self.assertEqual(more_actions[1].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)
        self.assertEqual(len(settings_actions), 1)
        self.assertIsInstance(settings_actions[0], TapAction)
        self.assertEqual(settings_actions[0].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_open_lord_info_uses_home_shortcut_after_closing_more_overlay(self) -> None:
        """Uses the direct home shortcut and only closes overlays when the task starts from More."""

        home_observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,),
        )
        more_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS),
        )
        settings_observation = make_observation(
            ScreenType.PNC_SETTINGS,
            visible_ids=(
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                UiElementId.PNC_MORE_MANAGE_CHAR,
            ),
        )

        home_actions = self.flows.open_lord_info(home_observation)
        more_actions = self.flows.open_lord_info(more_observation)
        settings_actions = self.flows.open_lord_info(settings_observation)

        self.assertEqual(len(home_actions), 1)
        self.assertIsInstance(home_actions[0], TapAction)
        self.assertEqual(home_actions[0].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)
        self.assertEqual(len(more_actions), 2)
        self.assertIsInstance(more_actions[0], TapAction)
        self.assertEqual(more_actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(more_actions[1], TapAction)
        self.assertEqual(more_actions[1].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)
        self.assertEqual(len(settings_actions), 1)
        self.assertIsInstance(settings_actions[0], TapAction)
        self.assertEqual(settings_actions[0].selector_id, UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
