"""Noisy coordinate semantic projection checks using typed OCR lines."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_world_map_semantic_additions,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.mail.build_observation import _build_observation


class NoisyCoordinateObservationTests(unittest.TestCase):
    """Proves coordinate parsing after explicit world-map acceptance."""

    def test_observation_builder_keeps_partial_world_coordinates_unknown(self) -> None:
        """Rejects partial coordinates when no complete world-map proof is supplied."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            lines=(
                _ocr_line("X:253", x=73, y=67, width=71, height=24),
                _ocr_line("Home", x=63, y=1563, width=76, height=28),
                _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertIsNone(observation.spatial_surface)

    def test_observation_builder_classifies_world_map_when_coordinate_bar_omits_the_x_colon(self) -> None:
        """Preserves coordinate parsing when OCR omits the X colon."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_WORLD_MAP,
            semantic_parser=_build_world_map_semantic_additions,
            lines=(
                _ocr_line("X292Y:540", x=346, y=140, width=223, height=39),
                _ocr_line("[LFG]Mr_Zero", x=249, y=307, width=126, height=23),
                _ocr_line("18km", x=594, y=296, width=77, height=31),
                _ocr_line("Home", x=63, y=1563, width=76, height=28),
                _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                _ocr_line("Alliance", x=666, y=1568, width=100, height=26),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertIsNotNone(observation.spatial_surface)
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_HOME))

    def test_observation_builder_classifies_world_map_from_noisy_merged_coordinate_line(self) -> None:
        """Preserves exact coordinates when OCR fuses extra digits on one line."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_WORLD_MAP,
            semantic_parser=_build_world_map_semantic_additions,
            lines=(
                _ocr_line("X:99287Y:707414", x=371, y=141, width=222, height=38),
                _ocr_line("Venom Spider", x=447, y=379, width=135, height=25),
                _ocr_line("Home", x=63, y=1563, width=76, height=28),
                _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                _ocr_line("Alliance", x=666, y=1568, width=100, height=26),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertIsNotNone(observation.spatial_surface)
        assert observation.spatial_surface is not None
        self.assertEqual(observation.spatial_surface.viewport.coordinate, (287, 707))

    def test_observation_builder_classifies_world_map_from_whitespace_split_coordinate_fragment(self) -> None:
        """Preserves exact coordinates when OCR splits an X fragment before Y."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_WORLD_MAP,
            semantic_parser=_build_world_map_semantic_additions,
            lines=(
                _ocr_line("X:101 4Y:695", x=371, y=146, width=197, height=30),
                _ocr_line("Enchanted Reptilian", x=194, y=582, width=192, height=25),
                _ocr_line("Home", x=63, y=1563, width=76, height=28),
                _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                _ocr_line("Alliance", x=666, y=1568, width=100, height=26),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertIsNotNone(observation.spatial_surface)
        assert observation.spatial_surface is not None
        self.assertEqual(observation.spatial_surface.viewport.coordinate, (101, 695))
