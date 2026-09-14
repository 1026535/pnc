"""Home city semantic projection checks using offline OCR geometry."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_home_city_semantic_additions,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.spatial_query import _spatial_query
from tests.support.pnc.mail.build_observation import _build_observation


class HomeCityObservationTests(unittest.TestCase):
    """Proves the home-city parser after an explicit screen decision."""

    def test_observation_builder_classifies_home_city_from_bottom_nav_ocr(self) -> None:
        """Projects bottom navigation and home actions through the canonical parser."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(
                _ocr_line("Build", x=120, y=1180, width=90, height=30),
                _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                _ocr_line("More", x=740, y=1500, width=74, height=32),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_VIP_SHORTCUT))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_IMPROVE_MIGHT_SHORTCUT))
        self.assertIsNotNone(observation.spatial_surface)
        self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.HOME_CITY_SURFACE)

    def test_observation_builder_classifies_live_like_home_city_when_build_anchor_is_left_aligned(self) -> None:
        """Keeps a left-rail Build anchor in the canonical home action projection."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(
                _ocr_line("Build", x=27, y=354, width=65, height=28),
                _ocr_line("Hero", x=219, y=1567, width=62, height=25),
                _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                _ocr_line("Quest", x=333, y=1571, width=69, height=20),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT))
        self.assertIsNotNone(observation.spatial_surface)
        self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.HOME_CITY_SURFACE)

    def test_observation_builder_classifies_busy_builder_home_city_from_help_anchor(self) -> None:
        """Treats the occupied-builder Help label as the canonical build-slot signal."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(
                _ocr_line("Help", x=27, y=354, width=58, height=28),
                _ocr_line("(1/1)", x=20, y=389, width=76, height=26),
                _ocr_line("Research", x=121, y=1182, width=118, height=29),
                _ocr_line("Hero", x=219, y=1567, width=62, height=25),
                _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                _ocr_line("Quest", x=333, y=1571, width=69, height=20),
                _ocr_line("Mail", x=571, y=1568, width=57, height=24),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_RESEARCH_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_observation_builder_exposes_home_city_active_build_timer_and_building_level(self) -> None:
        """Preserves timer, building level, and current OCR geometry in the spatial surface."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(
                _ocr_line("Build", x=27, y=354, width=65, height=28),
                _ocr_line("Wall", x=455, y=918, width=81, height=28),
                _ocr_line("6", x=506, y=956, width=22, height=22),
                _ocr_line("00:48:33", x=404, y=872, width=140, height=24),
                _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertIsNotNone(observation.spatial_surface)
        assert observation.spatial_surface is not None
        self.assertEqual(observation.spatial_surface.metadata["active_build_timer_text"], "00:48:33")
        wall = observation.require_spatial_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="wall",
            )
        )
        self.assertEqual(wall.level, 6)
