"""Login observation: semantic parsers under explicit screen decisions."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    _build_account_switch_additions,
    _build_login_additions,
)

from tests.support.pnc.capture_vision.build_observation_from_ocr_lines import (
    _build_observation_from_ocr_lines,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class LoginObservationTests(unittest.TestCase):
    """Proves login semantic parsing after explicit identity acceptance."""

    def test_explicit_screen_decision_publishes_login_controls(self) -> None:
        """Publishes credential controls and the displayed account identifier."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Email", x=80, y=225, width=70, height=26),
                _ocr_line("user@example.com", x=92, y=276, width=188, height=22),
                _ocr_line("Password", x=82, y=365, width=110, height=26),
                _ocr_line("Log In", x=211, y=566, width=105, height=30),
            ),
            accepted_screen=ScreenType.PNC_LOGIN,
            image_size=(540, 960),
            semantic_parser=lambda image, lines: _build_login_additions(image=image, lines=lines),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_LOGIN)
        self.assertTrue(observation.has(UiElementId.PNC_LOGIN_USERNAME_FIELD))
        self.assertTrue(observation.has(UiElementId.PNC_LOGIN_PASSWORD_FIELD))
        self.assertTrue(observation.has(UiElementId.PNC_LOGIN_SUBMIT_BUTTON))
        self.assertEqual(observation.require(UiElementId.PNC_LOGIN_USERNAME_FIELD).bounds.x, 60)
        self.assertEqual(observation.require(UiElementId.PNC_LOGIN_PASSWORD_FIELD).bounds.y, 352)
        self.assertEqual(observation.require(UiElementId.PNC_LOGIN_SUBMIT_BUTTON).bounds.width, 210)
        self.assertEqual(observation.current_pnc_account_id, "user@example.com")

    def test_explicit_screen_decision_publishes_account_switch_controls(self) -> None:
        """Publishes account-switch continuation controls and the displayed account identifier."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Switch Account", x=134, y=42, width=180, height=28),
                _ocr_line("user@example.com", x=116, y=292, width=188, height=22),
                _ocr_line("Continue", x=210, y=576, width=102, height=28),
                _ocr_line("Change Account", x=165, y=654, width=170, height=28),
            ),
            accepted_screen=ScreenType.PNC_ACCOUNT_SWITCH,
            image_size=(540, 960),
            semantic_parser=lambda image, lines: _build_account_switch_additions(image=image, lines=lines),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ACCOUNT_SWITCH)
        self.assertTrue(observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON))
        self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON).bounds.x, 159)
        self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON).bounds.width, 340)
        self.assertEqual(observation.current_pnc_account_id, "user@example.com")


if __name__ == "__main__":
    unittest.main()
