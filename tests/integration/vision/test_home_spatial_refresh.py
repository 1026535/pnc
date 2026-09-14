"""Home spatial refresh checks using two explicit parser-boundary observations."""

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


class HomeSpatialRefreshTests(unittest.TestCase):
    """Proves the home-city spatial parser refreshes from current OCR geometry."""

    def test_home_city_spatial_objects_rebuild_from_each_viewport_observation(self) -> None:
        """Rebuilds building targets from each supplied viewport instead of fixed coordinates."""

        common_lines = (
            _ocr_line("Build", x=27, y=354, width=65, height=28),
            _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
            _ocr_line("More", x=740, y=1500, width=74, height=32),
        )
        initial_observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(*common_lines, _ocr_line("Castle", x=310, y=610, width=120, height=28)),
        )
        shifted_observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(*common_lines, _ocr_line("Castle", x=528, y=744, width=120, height=28)),
        )

        initial_castle = initial_observation.require_spatial_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                name_text="Castle",
            )
        )
        shifted_castle = shifted_observation.require_spatial_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                name_text="Castle",
            )
        )

        self.assertNotEqual(initial_castle.bounds, shifted_castle.bounds)
        self.assertNotEqual(initial_castle.action_point, shifted_castle.action_point)
        self.assertEqual(initial_castle.viewport_offset, (-80, -176))
        self.assertAlmostEqual(initial_castle.viewport_offset_ratio[0], -80 / 900)
        self.assertAlmostEqual(initial_castle.viewport_offset_ratio[1], -176 / 1600)
        self.assertEqual(shifted_castle.viewport_offset, (138, -42))
        self.assertAlmostEqual(shifted_castle.viewport_offset_ratio[0], 138 / 900)
        self.assertAlmostEqual(shifted_castle.viewport_offset_ratio[1], -42 / 1600)
        self.assertEqual(initial_castle.metadata["home_city_object_id"], "castle")
        self.assertEqual(shifted_castle.metadata["home_city_object_id"], "castle")
