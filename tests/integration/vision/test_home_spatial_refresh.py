"""Home spatial refresh: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
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


class HomeSpatialRefreshTests(unittest.TestCase):
    """Proves home spatial refresh."""

    def test_home_city_spatial_objects_rebuild_from_each_viewport_observation(self) -> None:
        """Rebuilds home-city building targets from current OCR geometry instead of any fixed building coordinate."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
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
                            _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                            _ocr_line("More", x=740, y=1500, width=74, height=32),
                            _ocr_line("Castle", x=310, y=610, width=120, height=28),
                        )
                    )
                )
            shifted_builder = ObservationBuilder(
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
                            _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                            _ocr_line("More", x=740, y=1500, width=74, height=32),
                            _ocr_line("Castle", x=528, y=744, width=120, height=28),
                        )
                    )
                )
            initial_screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home_viewport_initial",
                label="home_city_initial",
            )
            shifted_screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home_viewport_shifted",
                label="home_city_shifted",
            )

            initial_observation = builder.build(initial_screenshot)
            shifted_observation = shifted_builder.build(shifted_screenshot)
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
