"""Home city observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
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
from tests.support.pnc.capture_vision.spatial_query import _spatial_query


class HomeCityObservationTests(unittest.TestCase):
    """Proves home city observation."""

    def test_observation_builder_classifies_home_city_from_bottom_nav_ocr(self) -> None:
        """Recognizes home city from bottom navigation OCR when templates are unavailable."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home",
                label="home_city",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Build", x=120, y=1180, width=90, height=30),
                            _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                            _ocr_line("More", x=740, y=1500, width=74, height=32),
                        )
                    )
                )

            observation = builder.build(screenshot)

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
        """Recognizes home city when the live Build button sits on the left rail instead of the lower action band."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k313_live_like_home",
                label="home_city_left_build",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Build", x=27, y=354, width=65, height=28),
                            _ocr_line("Hero", x=219, y=1567, width=62, height=25),
                            _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("Quest", x=333, y=1571, width=69, height=20),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))
            self.assertTrue(observation.has(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT))
            self.assertIsNotNone(observation.spatial_surface)
            self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.HOME_CITY_SURFACE)

    def test_observation_builder_classifies_busy_builder_home_city_from_help_anchor(self) -> None:
        """Treats the occupied-builder Help label as the same canonical home-city build-slot signal."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_busy_builder_home",
                label="home_city_help_anchor",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
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
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_HOME_RESEARCH_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_observation_builder_exposes_home_city_active_build_timer_and_building_level(self) -> None:
        """Adds the shared home-city timer proof plus building-level enrichment used by upgrade verification."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home_city_active_build",
                label="home_city_active_build",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Build", x=27, y=354, width=65, height=28),
                            _ocr_line("Wall", x=455, y=918, width=81, height=28),
                            _ocr_line("6", x=506, y=956, width=22, height=22),
                            _ocr_line("00:48:33", x=404, y=872, width=140, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                )

            observation = builder.build(screenshot)

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
