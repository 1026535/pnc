"""Coordinate bar observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.coordinate_bar_filtering_full_ocr_service import (
    _CoordinateBarFilteringFullOcrService,
)
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class CoordinateBarObservationTests(unittest.TestCase):
    """Proves coordinate bar observation."""

    def test_observation_builder_classifies_world_map_from_coordinates_and_bottom_nav_ocr_at_alternate_resolution(self) -> None:
        """Recognizes the world map from OCR at the smaller supported live resolution too."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_world_map_small",
                label="world_map_live_like_small",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("X:253", x=44, y=41, width=42, height=18),
                            _ocr_line("Y:447", x=102, y=41, width=42, height=18),
                            _ocr_line("Home", x=38, y=937, width=46, height=17),
                            _ocr_line("Hero", x=126, y=938, width=38, height=17),
                            _ocr_line("Quest", x=200, y=939, width=45, height=15),
                            _ocr_line("Mail", x=321, y=939, width=35, height=16),
                            _ocr_line("Alliance", x=402, y=938, width=74, height=17),
                            _ocr_line("More", x=479, y=938, width=41, height=17),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_HOME_NAV))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertIsNotNone(observation.spatial_surface)
            self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.WORLD_MAP)
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (253, 447))

    def test_observation_builder_uses_filtered_coordinate_bar_for_world_map_spatial_surface(self) -> None:
        """Uses the same blue-filtered coordinate OCR for both world-map proof and viewport coordinates."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (540, 960), (15, 28, 68))
            registry = build_default_selector_registry()
            coordinate_region = registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR).relative_bounds
            assert coordinate_region is not None
            bounds = coordinate_region.materialize_region(image_size=image.size)
            for x in range(bounds.x + 8, bounds.x + bounds.width - 8):
                for y in range(bounds.y + 8, bounds.y + bounds.height - 8):
                    image.putpixel((x, y), (42, 198, 224))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="k230_world_map_filtered_coordinate",
                label="world_map_filtered_coordinate",
            )
            ocr_service = _CoordinateBarFilteringFullOcrService(
                raw_text="X:230-kV.958",
                filtered_text="X:230 Y:958",
                full_lines=(
                    _ocr_line("X: 2,736,039", x=185, y=42, width=123, height=30),
                    _ocr_line("Y:958", x=286, y=89, width=55, height=18),
                    _ocr_line("Home", x=38, y=937, width=46, height=17),
                    _ocr_line("Hero", x=126, y=938, width=38, height=17),
                    _ocr_line("Quest", x=200, y=939, width=45, height=15),
                    _ocr_line("Mail", x=321, y=939, width=35, height=16),
                    _ocr_line("Alliance", x=402, y=938, width=74, height=17),
                    _ocr_line("More", x=479, y=938, width=41, height=17),
                ),
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=ocr_service,
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=ocr_service,
                    selector_registry=registry,
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            assert observation.spatial_surface is not None
            self.assertEqual(observation.require(UiElementId.PNC_WORLD_COORDINATE_BAR).extracted_text, "X:230 Y:958")
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (230, 958))
            self.assertEqual(observation.spatial_surface.metadata["coordinate_text"], "X:230 Y:958")
