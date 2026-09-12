"""Home spatial observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
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


class HomeSpatialObservationTests(unittest.TestCase):
    """Proves home spatial observation."""

    def test_observation_builder_builds_home_city_spatial_surface_objects(self) -> None:
        """Parses home-city buildings and empty slots as spatial objects rather than list rows."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home_objects",
                label="home_city_objects",
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
                            _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                            _ocr_line("More", x=740, y=1500, width=74, height=32),
                            _ocr_line("Castle", x=310, y=610, width=120, height=28),
                            _ocr_line("Academy", x=520, y=690, width=150, height=28),
                            _ocr_line("Build", x=450, y=840, width=90, height=28),
                        )
                    )
                )

            observation = builder.build(screenshot)

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
