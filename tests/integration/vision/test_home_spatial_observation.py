"""Home spatial semantic projection checks using offline OCR geometry."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_home_city_semantic_additions,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.spatial_query import _spatial_query
from tests.support.pnc.mail.build_observation import _build_observation


class HomeSpatialObservationTests(unittest.TestCase):
    """Proves the home-city spatial parser after explicit screen acceptance."""

    def test_observation_builder_builds_home_city_spatial_surface_objects(self) -> None:
        """Projects supplied OCR geometry into typed buildings and empty slots."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(
                _ocr_line("Build", x=27, y=354, width=65, height=28),
                _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                _ocr_line("More", x=740, y=1500, width=74, height=32),
                _ocr_line("Castle", x=310, y=610, width=120, height=28),
                _ocr_line("Academy", x=520, y=690, width=150, height=28),
                _ocr_line("Build", x=450, y=840, width=90, height=28),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertIsNotNone(observation.spatial_surface)
        self.assertEqual(
            observation.require_spatial_object(
                _spatial_query(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_BUILDING,
                    name_text="Castle",
                )
            ).metadata["home_city_object_id"],
            "castle",
        )
        self.assertEqual(
            observation.require_spatial_object(
                _spatial_query(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_BUILDING,
                    name_text="Academy",
                )
            ).metadata["home_city_object_id"],
            "institute",
        )
        self.assertIsNotNone(
            observation.find_spatial_object(
                _spatial_query(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_EMPTY_SLOT,
                )
            )
        )
