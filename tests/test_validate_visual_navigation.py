"""The live proof must reject resource spending and target changes before execution."""

import unittest

from pnc_automation.app.pnc.domain.action_requests import (
    InputTextAction, KeyEventAction, TapAction, TapListEntryAction,
    TapPointAction, WaitAction,
)
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from tools.validate_visual_navigation import validate_probe_action


class VisualNavigationSafetyTests(unittest.TestCase):
    def test_navigation_and_bounded_wait_are_allowed(self) -> None:
        for action in (
            TapAction(selector_id=UiElementId.PNC_MORE_SETTINGS),
            KeyEventAction(key_code="KEYCODE_BACK"),
            WaitAction(milliseconds=1000),
        ):
            validate_probe_action(action)

    def test_spending_target_selection_and_unbounded_input_are_rejected(self) -> None:
        for action in (
            TapAction(selector_id=UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON),
            TapAction(selector_id=UiElementId.PNC_UPDATE_CONFIRM_BUTTON),
            TapListEntryAction(), TapPointAction(x=100, y=100),
            InputTextAction(text="message"), KeyEventAction(key_code="KEYCODE_ENTER"),
            WaitAction(milliseconds=1001), WaitAction(milliseconds=-1),
        ):
            with self.subTest(action=type(action).__name__):
                with self.assertRaises(ValueError):
                    validate_probe_action(action)


if __name__ == "__main__":
    unittest.main()
