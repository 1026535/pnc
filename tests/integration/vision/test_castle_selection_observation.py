"""Castle-selection semantic projection checks using offline OCR geometry."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import ListEntryKind, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_castle_selection_semantic_additions,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.mail.build_observation import _build_observation


class CastleSelectionObservationTests(unittest.TestCase):
    """Proves Manage Char roster parsing after explicit screen acceptance."""

    def test_observation_builder_does_not_promote_home_city_to_world_map_from_region_noise(self) -> None:
        """Keeps a home-city footer from becoming world-map evidence when coordinates are absent."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            image_size=(540, 960),
            lines=(
                _ocr_line("Build", x=18, y=47, width=46, height=14),
                _ocr_line("Hero", x=124, y=938, width=40, height=16),
                _ocr_line("Quest", x=198, y=938, width=45, height=16),
                _ocr_line("Mail", x=320, y=938, width=35, height=16),
                _ocr_line("Alliance", x=401, y=938, width=73, height=16),
                _ocr_line("More", x=478, y=938, width=40, height=16),
            ),
        )

        self.assertNotEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertFalse(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
        self.assertFalse(observation.has(UiElementId.PNC_WORLD_HOME_NAV))

    def test_observation_builder_parses_castle_selection_from_manage_char_ocr(self) -> None:
        """Projects exact Manage Char rows and selected-castle state through the canonical parser."""

        image = Image.new("RGB", (540, 960), (15, 28, 68))
        for x in range(410, 470):
            for y in range(520, 590):
                image.putpixel((x, y), (40, 200, 70))
        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_CASTLE_SELECTION,
            semantic_parser=_build_castle_selection_semantic_additions,
            image=image,
            image_size=image.size,
            lines=(
                _ocr_line("Manage Char.", x=132, y=18, width=152, height=24),
                _ocr_line("K304 Kingdom", x=99, y=97, width=127, height=18),
                _ocr_line("K304caf8305606", x=99, y=124, width=148, height=18),
                _ocr_line("Castle Level 4", x=98, y=151, width=125, height=18),
                _ocr_line("K230 Kingdom", x=98, y=494, width=128, height=18),
                _ocr_line("Lv.5 Hellhound", x=99, y=522, width=139, height=19),
                _ocr_line("Castle Level 9", x=98, y=549, width=126, height=18),
            ),
        )
        castle_entries = observation.entries(ListEntryKind.CASTLE)

        self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE_SELECTION)
        self.assertEqual(len(castle_entries), 2)
        self.assertEqual(castle_entries[1].title_text, "Lv.5 Hellhound")
        self.assertEqual(castle_entries[1].metadata["kingdom"], "K230")
        self.assertEqual(castle_entries[1].metadata["castle_level"], 9)
        self.assertTrue(castle_entries[1].selected)
        self.assertEqual(observation.current_castle_name, "Lv.5 Hellhound")
        self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
        self.assertEqual(
            VisibleElementSourceKind.GEOMETRY,
            observation.visible_elements[UiElementId.PNC_BACK_BUTTON_TOP_LEFT].source_kind,
        )

    def test_observation_builder_parses_single_castle_manage_char_from_ocr(self) -> None:
        """Recognizes Manage Char with one visible castle row while preserving exact names."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_CASTLE_SELECTION,
            semantic_parser=_build_castle_selection_semantic_additions,
            image_size=(540, 960),
            lines=(
                _ocr_line("Manage Char.", x=132, y=18, width=152, height=24),
                _ocr_line("K230 Kingdom", x=98, y=494, width=128, height=18),
                _ocr_line("Lv.5 Hellhound", x=99, y=522, width=139, height=19),
                _ocr_line("Castle Level 9", x=98, y=549, width=126, height=18),
            ),
        )
        castle_entries = observation.entries(ListEntryKind.CASTLE)

        self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE_SELECTION)
        self.assertEqual(len(castle_entries), 1)
        self.assertEqual(castle_entries[0].title_text, "Lv.5 Hellhound")
