"""Settings and profile observation: semantic parsers under explicit decisions."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _build_lord_info_additions,
    _build_more_menu_additions,
    _build_more_settings_menu_additions,
)
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.text_anchors import TextAnchorDetector
from pnc_automation.core.vision.ocr.ocr_service import OcrLine

from tests.support.pnc.capture_vision.build_observation_from_ocr_lines import (
    _build_observation_from_ocr_lines,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


def _build_more_menu_semantics(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> ObservationAdditions:
    """Run the More-menu parser with canonical OCR anchor detection."""

    additions = _build_more_menu_additions(
        image=image,
        lines=lines,
        anchors=TextAnchorDetector().detect(lines),
    )
    return additions or ObservationAdditions()


class SettingsProfileObservationTests(unittest.TestCase):
    """Proves settings/profile semantic parsing under accepted identity."""

    def test_explicit_screen_decision_publishes_more_menu_actions(self) -> None:
        """Publishes More overlay actions after the caller accepts its identity."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Manage Char", x=78, y=1330, width=178, height=34),
                _ocr_line("Lord Info", x=315, y=1332, width=154, height=34),
                _ocr_line("VIP", x=562, y=1333, width=58, height=34),
                _ocr_line("Improve Might", x=690, y=1330, width=184, height=34),
                _ocr_line("Rank", x=105, y=1444, width=72, height=31),
                _ocr_line("Friend", x=318, y=1444, width=88, height=31),
                _ocr_line("Guides", x=520, y=1444, width=91, height=31),
                _ocr_line("Settings", x=742, y=1444, width=112, height=31),
                _ocr_line("More", x=794, y=1567, width=71, height=27),
            ),
            accepted_screen=ScreenType.PNC_MORE_MENU,
            semantic_parser=_build_more_menu_semantics,
            materialize_geometry=False,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MORE_MENU)
        self.assertTrue(observation.has(UiElementId.PNC_MORE_SETTINGS))
        self.assertTrue(observation.has(UiElementId.PNC_MORE_OVERLAY_MANAGE_CHAR))
        self.assertFalse(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))
        self.assertTrue(observation.has(UiElementId.PNC_MORE_LORD_INFO))
        self.assertTrue(observation.has(UiElementId.PNC_MORE_VIP))
        self.assertTrue(observation.has(UiElementId.PNC_MORE_IMPROVE_MIGHT))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_explicit_screen_decision_publishes_settings_submenu(self) -> None:
        """Publishes the Settings submenu while keeping unrelated More controls absent."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Settings", x=112, y=20, width=128, height=28),
                _ocr_line("Account", x=120, y=94, width=102, height=24),
                _ocr_line("Manage Char.", x=304, y=94, width=134, height=24),
                _ocr_line("Search", x=122, y=188, width=88, height=24),
                _ocr_line("Rank", x=344, y=188, width=64, height=24),
                _ocr_line("Blacklist", x=320, y=374, width=104, height=24),
            ),
            accepted_screen=ScreenType.PNC_SETTINGS,
            image_size=(540, 960),
            semantic_parser=lambda image, lines: _build_more_settings_menu_additions(image=image, lines=lines),
            materialize_geometry=False,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_SETTINGS)
        self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
        self.assertTrue(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))
        self.assertFalse(observation.has(UiElementId.PNC_MORE_SETTINGS))
        self.assertFalse(observation.has(UiElementId.PNC_MORE_OVERLAY_MANAGE_CHAR))
        self.assertFalse(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_explicit_screen_decision_publishes_lord_info_name(self) -> None:
        """Publishes the OCR-backed lord name after the caller accepts the profile screen."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Lord Info", x=184, y=20, width=208, height=48),
                _ocr_line("Gear", x=52, y=111, width=83, height=42),
                _ocr_line("K304554ca2797", x=240, y=1048, width=210, height=27),
                _ocr_line("Talent", x=68, y=1560, width=82, height=28),
                _ocr_line("Lord Info", x=220, y=1559, width=114, height=30),
                _ocr_line("Boost Info", x=386, y=1561, width=124, height=27),
                _ocr_line("Alliance Info", x=561, y=1561, width=120, height=26),
                _ocr_line("Achievements", x=731, y=1567, width=115, height=17),
            ),
            accepted_screen=ScreenType.PNC_LORD_INFO,
            semantic_parser=lambda image, lines: _build_lord_info_additions(image=image, lines=lines),
            materialize_geometry=False,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_LORD_INFO)
        self.assertTrue(observation.has(UiElementId.PNC_LORD_INFO_HEADER))
        self.assertEqual(
            observation.require(UiElementId.PNC_LORD_INFO_NAME_LABEL).extracted_text,
            "K304554ca2797",
        )
        self.assertEqual(observation.current_castle_name, "K304554ca2797")


if __name__ == "__main__":
    unittest.main()
