"""World overview marker projection checks using explicit OCR screen input."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Bounds, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapCoordinateDomain
from pnc_automation.app.pnc.navigation.world_map_overview_projection import (
    project_world_coordinate_to_overview_point,
)
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapOverviewNavigator
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_world_overview_semantic_parser,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.paint_overview_false_positive_blob import (
    _paint_overview_false_positive_blob,
)
from tests.support.pnc.capture_vision.paint_overview_viewport_marker import (
    _paint_overview_viewport_marker,
)
from tests.support.pnc.capture_vision.paint_synthetic_world_overview_map import (
    _paint_synthetic_world_overview_map,
)
from tests.support.pnc.mail.build_observation import _build_observation


class OverviewMarkerObservationTests(unittest.TestCase):
    """Proves overview marker geometry after explicit overview acceptance."""

    def test_observation_builder_detects_world_overview_marker_without_hint_near_map_edge(self) -> None:
        """Selects the border-touching warm cluster when no coordinate hint is supplied."""

        registry = build_default_selector_registry()
        image = Image.new("RGB", (540, 960), (15, 28, 68))
        map_region = registry.require(UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION).relative_bounds
        assert map_region is not None
        map_region_bounds = map_region.materialize_region(image_size=image.size)
        _paint_synthetic_world_overview_map(image, map_region_bounds=map_region_bounds)
        _paint_overview_false_positive_blob(
            image,
            bounds=Bounds(
                x=map_region_bounds.x + 84,
                y=map_region_bounds.y + 57,
                width=47,
                height=41,
            ),
        )
        marker_point = project_world_coordinate_to_overview_point(
            coordinate=(20, 20),
            bounds=WorldMapCoordinateDomain.puzzles_and_conquest().bounds,
            map_region_bounds=Bounds(
                x=map_region_bounds.x,
                y=map_region_bounds.y,
                width=map_region_bounds.width,
                height=map_region_bounds.height,
            ),
        )
        _paint_overview_viewport_marker(image, marker_point=marker_point)
        request = ObservationRequest.world_map_overview_follow_up()
        observation = _build_observation(
            request=request,
            accepted_screen=ScreenType.PNC_WORLD_MAP_OVERVIEW,
            semantic_parser=_build_world_overview_semantic_parser(request=request),
            image=image,
            image_size=image.size,
            lines=(_ocr_line("K:226 Reset", x=228, y=22, width=144, height=32),),
        )
        context = WorldMapOverviewNavigator().parse_context(observation)

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP_OVERVIEW)
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER))
        self.assertEqual(
            observation.require(UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )
        self.assertLessEqual(abs(context.current_viewport_coordinate[0] - 20), 4)
        self.assertLessEqual(abs(context.current_viewport_coordinate[1] - 20), 4)

    def test_observation_builder_detects_world_overview_marker_with_coordinate_hint(self) -> None:
        """Uses the expected coordinate to prefer the correct marker over a warm distractor."""

        registry = build_default_selector_registry()
        image = Image.new("RGB", (540, 960), (15, 28, 68))
        map_region = registry.require(UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION).relative_bounds
        assert map_region is not None
        map_region_bounds = map_region.materialize_region(image_size=image.size)
        _paint_synthetic_world_overview_map(image, map_region_bounds=map_region_bounds)
        _paint_overview_false_positive_blob(
            image,
            bounds=Bounds(
                x=map_region_bounds.x + 83,
                y=map_region_bounds.y + 57,
                width=47,
                height=41,
            ),
        )
        marker_point = project_world_coordinate_to_overview_point(
            coordinate=(256, 512),
            bounds=WorldMapCoordinateDomain.puzzles_and_conquest().bounds,
            map_region_bounds=Bounds(
                x=map_region_bounds.x,
                y=map_region_bounds.y,
                width=map_region_bounds.width,
                height=map_region_bounds.height,
            ),
        )
        _paint_overview_viewport_marker(image, marker_point=marker_point)
        request = ObservationRequest.world_map_overview_follow_up(expected_coordinate=(256, 512))
        observation = _build_observation(
            request=request,
            accepted_screen=ScreenType.PNC_WORLD_MAP_OVERVIEW,
            semantic_parser=_build_world_overview_semantic_parser(request=request),
            image=image,
            image_size=image.size,
            lines=(_ocr_line("K:226 Reset", x=228, y=22, width=144, height=32),),
        )
        context = WorldMapOverviewNavigator().parse_context(observation)

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP_OVERVIEW)
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER))
        self.assertEqual(context.current_viewport_coordinate, (256, 512))
