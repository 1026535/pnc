"""Noisy coordinate observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
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

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class NoisyCoordinateObservationTests(unittest.TestCase):
    """Proves noisy coordinate observation."""

    def test_observation_builder_keeps_partial_world_coordinates_unknown(self) -> None:
        """Rejects partial world-coordinate OCR instead of classifying world map from weak evidence."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_world_partial",
                label="world_map_partial_coordinate",
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
                            _ocr_line("X:253", x=73, y=67, width=71, height=24),
                            _ocr_line("Home", x=63, y=1563, width=76, height=28),
                            _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                            _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                            _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertIsNone(observation.spatial_surface)

    def test_observation_builder_classifies_world_map_when_coordinate_bar_omits_the_x_colon(self) -> None:
        """Builds the exact world-map surface when OCR keeps both axes even if the X token loses its colon."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_world_root",
                label="world_map_root_like",
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
                            _ocr_line("X292Y:540", x=346, y=140, width=223, height=39),
                            _ocr_line("[LFG]Mr_Zero", x=249, y=307, width=126, height=23),
                            _ocr_line("18km", x=594, y=296, width=77, height=31),
                            _ocr_line("Home", x=63, y=1563, width=76, height=28),
                            _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                            _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                            _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_HOME))

    def test_observation_builder_classifies_world_map_from_noisy_merged_coordinate_line(self) -> None:
        """Keeps exact world-map proof when the coordinate bar OCR fuses extra digits into both axes on one line."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_world_map_noisy_merged_coordinate",
                label="world_map_noisy_merged_coordinate",
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
                            _ocr_line("X:99287Y:707414", x=371, y=141, width=222, height=38),
                            _ocr_line("Venom Spider", x=447, y=379, width=135, height=25),
                            _ocr_line("Home", x=63, y=1563, width=76, height=28),
                            _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                            _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                            _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            assert observation.spatial_surface is not None
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (287, 707))

    def test_observation_builder_classifies_world_map_from_whitespace_split_coordinate_fragment(self) -> None:
        """Keeps exact world-map proof when OCR splits one X fragment across whitespace before the Y label."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_world_map_split_coordinate",
                label="world_map_split_coordinate",
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
                            _ocr_line("X:101 4Y:695", x=371, y=146, width=197, height=30),
                            _ocr_line("Enchanted Reptilian", x=194, y=582, width=192, height=25),
                            _ocr_line("Home", x=63, y=1563, width=76, height=28),
                            _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                            _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                            _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            assert observation.spatial_surface is not None
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (101, 695))
