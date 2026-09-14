"""Canonical building speedup parser qualifications."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    _add_shared_building_speedup_control,
    _build_build_speedup_additions,
    _build_speedup_confirm_additions,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


VIEWPORT = (900, 1600)


def _line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    """Create one localized OCR line for an accepted speedup surface."""

    return OcrLine(text=text, bounds=Bounds(x, y, width, height), confidence=1.0)


class BuildingSpeedupParserTests(unittest.TestCase):
    """Prove speedup and confirmation parsing after visual screen ownership."""

    def test_parser_adds_shared_speedup_to_upgradeable_building(self) -> None:
        """The common Speedup action is parsed only on an upgradeable building screen."""

        visible_elements = {}
        _add_shared_building_speedup_control(
            image=Image.new("RGB", VIEWPORT),
            lines=(_line("Speedup", x=675, y=438, width=145, height=41),),
            screen_type=ScreenType.PNC_WAREHOUSE,
            visible_elements=visible_elements,
        )

        speedup = visible_elements[UiElementId.PNC_BUILDING_SPEEDUP_BUTTON]
        self.assertEqual(speedup.extracted_text, "Speedup")
        self.assertEqual(speedup.source_kind, VisibleElementSourceKind.OCR)

    def test_parser_separates_auto_speedup_and_premium_build_now(self) -> None:
        """The inventory surface exposes Auto Speedup and the premium action independently."""

        additions = _build_build_speedup_additions(
            image=Image.new("RGB", VIEWPORT),
            lines=(
                _line("Build Speedup", x=182, y=18, width=280, height=50),
                _line("Build Now", x=178, y=1510, width=180, height=45),
                _line("Auto Speedup", x=520, y=1510, width=230, height=45),
            ),
        )

        self.assertIsNotNone(additions)
        assert additions is not None
        self.assertIn(UiElementId.PNC_BUILD_SPEEDUP_AUTO_BUTTON, additions.visible_elements)
        self.assertIn(
            UiElementId.PNC_BUILD_SPEEDUP_PREMIUM_BUILD_NOW_BUTTON,
            additions.visible_elements,
        )

    def test_parser_requires_auto_speedup_before_accepting_inventory_surface(self) -> None:
        """A Build Speedup title alone cannot establish the inventory action surface."""

        additions = _build_build_speedup_additions(
            image=Image.new("RGB", VIEWPORT),
            lines=(_line("Build Speedup", x=182, y=18, width=280, height=50),),
        )

        self.assertIsNone(additions)

    def test_parser_exposes_speedup_consumption_confirmation_separately(self) -> None:
        """The final Confirm action is owned by the explicit speedup confirmation parser."""

        additions = _build_speedup_confirm_additions(
            image=Image.new("RGB", VIEWPORT),
            lines=(
                _line("Build Speedup", x=305, y=420, width=290, height=50),
                _line("Confirm", x=362, y=1165, width=180, height=45),
            ),
        )

        self.assertIsNotNone(additions)
        assert additions is not None
        self.assertEqual(
            additions.screen_evidence[0].screen_type,
            ScreenType.PNC_BUILD_SPEEDUP_CONFIRM,
        )
        self.assertIn(UiElementId.PNC_BUILD_SPEEDUP_CONFIRM_HEADER, additions.visible_elements)
        self.assertIn(UiElementId.PNC_BUILD_SPEEDUP_CONFIRM_BUTTON, additions.visible_elements)


if __name__ == "__main__":
    unittest.main()
