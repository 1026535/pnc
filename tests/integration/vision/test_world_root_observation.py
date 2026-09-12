"""World root observation: verifies the named internal boundary with offline fixtures."""

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
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class WorldRootObservationTests(unittest.TestCase):
    """Proves world root observation."""

    def test_observation_builder_classifies_world_map_from_coordinates_and_bottom_nav_ocr(self) -> None:
        """Recognizes the live root-map layout so root navigation does not fall back to KEYCODE_BACK."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_world_map",
                label="world_map_live_like",
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
                            _ocr_line("Y:447", x=177, y=67, width=69, height=24),
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
        """Carries the magnifier invalid-coordinate banner with the proven world-map observation."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_world_map_invalid_coordinate",
                label="world_map_invalid_coordinate",
            )
            registry = build_default_selector_registry()
            ocr_service = _FakeOcrService(
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
                )
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=ocr_service,
                    selector_registry=registry,
                ),
            )

            observation = builder.build(screenshot, request=ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP))

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertEqual(observation.require(UiElementId.PNC_STATUS_BANNER).extracted_text, "Invalid coordinates")
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (253, 447))
