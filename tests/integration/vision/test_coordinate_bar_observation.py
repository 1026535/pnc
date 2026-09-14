"""Coordinate-bar semantic projection checks using typed OCR geometry."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.pnc_observation_enricher import _build_world_map_additions
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.text_anchors import TextAnchorDetector
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult

from tests.support.pnc.capture_vision.coordinate_bar_filtering_full_ocr_service import (
    _CoordinateBarFilteringFullOcrService,
)
from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_world_map_semantic_additions,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.mail.build_observation import _build_observation


def _build_filtered_world_map_semantic_additions(
    *, image: Image.Image, lines: tuple[OcrLine, ...]
) -> ObservationAdditions:
    """Run the canonical world parser with the fixture's coordinate crop filter."""

    registry = build_default_selector_registry()
    ocr_service = _CoordinateBarFilteringFullOcrService(
        raw_text="X:230-kV.958",
        filtered_text="X:230 Y:958",
        full_lines=lines,
    )
    context = ObservationOcrContext(image, ocr_service, None, "synthetic-coordinate-bar")
    context.require_bounded_regions()
    additions = _build_world_map_additions(
        image=image,
        lines=lines,
        anchors=TextAnchorDetector().detect(OcrResult(lines=lines, words=())),
        selector_registry=registry,
        ocr_context=context,
    )
    return additions or ObservationAdditions()


class CoordinateBarObservationTests(unittest.TestCase):
    """Proves coordinate-bar parsing after explicit world-map acceptance."""

    def test_observation_builder_classifies_world_map_from_coordinates_and_bottom_nav_ocr_at_alternate_resolution(self) -> None:
        """Projects the smaller reviewed viewport into a typed world-map surface."""

        image = Image.new("RGB", (540, 960), (15, 28, 68))
        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_WORLD_MAP,
            semantic_parser=_build_world_map_semantic_additions,
            image=image,
            image_size=image.size,
            lines=(
                _ocr_line("X:253", x=44, y=41, width=42, height=18),
                _ocr_line("Y:447", x=102, y=41, width=42, height=18),
                _ocr_line("Home", x=38, y=937, width=46, height=17),
                _ocr_line("Hero", x=126, y=938, width=38, height=17),
                _ocr_line("Quest", x=200, y=939, width=45, height=15),
                _ocr_line("Mail", x=321, y=939, width=35, height=16),
                _ocr_line("Alliance", x=402, y=938, width=74, height=17),
                _ocr_line("More", x=479, y=938, width=41, height=17),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_HOME_NAV))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
        self.assertIsNotNone(observation.spatial_surface)
        self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.WORLD_MAP)
        self.assertEqual(observation.spatial_surface.viewport.coordinate, (253, 447))

    def test_observation_builder_uses_filtered_coordinate_bar_for_world_map_spatial_surface(self) -> None:
        """Keeps the blue-filtered coordinate read authoritative for viewport coordinates."""

        image = Image.new("RGB", (540, 960), (15, 28, 68))
        registry = build_default_selector_registry()
        coordinate_region = registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR).relative_bounds
        assert coordinate_region is not None
        bounds = coordinate_region.materialize_region(image_size=image.size)
        for x in range(bounds.x + 8, bounds.x + bounds.width - 8):
            for y in range(bounds.y + 8, bounds.y + bounds.height - 8):
                image.putpixel((x, y), (42, 198, 224))
        lines = (
            _ocr_line("X: 2,736,039", x=185, y=42, width=123, height=30),
            _ocr_line("Y:958", x=286, y=89, width=55, height=18),
            _ocr_line("Home", x=38, y=937, width=46, height=17),
            _ocr_line("Hero", x=126, y=938, width=38, height=17),
            _ocr_line("Quest", x=200, y=939, width=45, height=15),
            _ocr_line("Mail", x=321, y=939, width=35, height=16),
            _ocr_line("Alliance", x=402, y=938, width=74, height=17),
            _ocr_line("More", x=479, y=938, width=41, height=17),
        )
        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_WORLD_MAP,
            semantic_parser=_build_filtered_world_map_semantic_additions,
            image=image,
            image_size=image.size,
            lines=lines,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertIsNotNone(observation.spatial_surface)
        assert observation.spatial_surface is not None
        self.assertEqual(observation.require(UiElementId.PNC_WORLD_COORDINATE_BAR).extracted_text, "X:230 Y:958")
        self.assertEqual(observation.spatial_surface.viewport.coordinate, (230, 958))
        self.assertEqual(observation.spatial_surface.metadata["coordinate_text"], "X:230 Y:958")
