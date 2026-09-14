"""Focused checks for typed screen-family OCR content strategies."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.pnc_ocr_capabilities import (
    can_attempt_screen_family_ocr,
    runtime_screen_family_ocr_types,
)


class PncOcrCapabilitiesTests(unittest.TestCase):
    """Keep content strategy declarations derived from the canonical family registry."""

    def test_only_the_exact_accepted_family_can_read_content(self) -> None:
        for family in runtime_screen_family_ocr_types():
            self.assertTrue(can_attempt_screen_family_ocr(request_screen=family, observed_screen=family))
            self.assertFalse(can_attempt_screen_family_ocr(request_screen=family, observed_screen=ScreenType.UNKNOWN))
        self.assertFalse(can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_SETTINGS, observed_screen=ScreenType.PNC_HOME_CITY,
        ))
        self.assertFalse(
            can_attempt_screen_family_ocr(
                request_screen=ScreenType.PNC_CHAT,
                observed_screen=ScreenType.PNC_BAG,
            )
        )
        self.assertFalse(
            can_attempt_screen_family_ocr(
                request_screen=ScreenType.PNC_HOME_CITY,
                observed_screen=ScreenType.PNC_CHAT,
            )
        )

    def test_unregistered_family_is_denied_by_runtime_gate(self) -> None:
        self.assertFalse(
            can_attempt_screen_family_ocr(
                request_screen=ScreenType.PNC_LOADING,
                observed_screen=ScreenType.PNC_LOADING,
            )
        )


if __name__ == "__main__":
    unittest.main()
