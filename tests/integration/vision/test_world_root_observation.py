"""World-map semantic projection checks using offline OCR geometry."""

from __future__ import annotations

from functools import partial
import unittest

from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_world_map_semantic_additions,
    _build_world_map_status_semantic_additions,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.mail.build_observation import _build_observation


class WorldRootObservationTests(unittest.TestCase):
    """Proves the world-map parser after an explicit screen decision."""

    def test_observation_builder_classifies_world_map_from_coordinates_and_bottom_nav_ocr(self) -> None:
        """Projects coordinates and bottom navigation into the typed world-map surface."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_WORLD_MAP,
            semantic_parser=_build_world_map_semantic_additions,
            lines=(
                _ocr_line("X:253", x=73, y=67, width=71, height=24),
                _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                _ocr_line("Home", x=63, y=1563, width=76, height=28),
                _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_SEARCH_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_HOME_NAV))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
        self.assertTrue(observation.has(UiElementId.PNC_CHAT_SHORTCUT))
        self.assertIsNotNone(observation.spatial_surface)
        self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.WORLD_MAP)
        self.assertEqual(observation.spatial_surface.viewport.coordinate, (253, 447))
        self.assertLess(
            observation.require(UiElementId.PNC_WORLD_SEARCH_BUTTON).action_point[0],
            observation.require(UiElementId.PNC_WORLD_COORDINATE_BAR).bounds.x,
        )

    def test_observation_builder_preserves_world_map_invalid_coordinate_status_banner(self) -> None:
        """Preserves the invalid-coordinate banner alongside the typed world-map surface."""

        request = ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP)
        observation = _build_observation(
            request=request,
            accepted_screen=ScreenType.PNC_WORLD_MAP,
            semantic_parser=partial(_build_world_map_status_semantic_additions, request=request),
            lines=(
                _ocr_line("Invalid coordinates", x=288, y=180, width=326, height=38),
                _ocr_line("X:253", x=73, y=67, width=71, height=24),
                _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                _ocr_line("Home", x=63, y=1563, width=76, height=28),
                _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(observation.require(UiElementId.PNC_STATUS_BANNER).extracted_text, "Invalid coordinates")
        self.assertEqual(observation.spatial_surface.viewport.coordinate, (253, 447))
