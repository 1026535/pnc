"""Coordinate bar local fixtures: verifies the named internal boundary with offline fixtures."""

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
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


class CoordinateBarLocalFixturesTests(unittest.TestCase):
    """Proves coordinate bar local fixtures."""

    def test_observation_builder_recovers_live_world_coordinate_bar_when_filtered_crop_drops_y_axis(self) -> None:
        """Keeps world-map proof on the reviewed live edge-case screenshot by falling back to raw OCR inside the canonical bar crop."""

        fixture_path = require_local_fixture_artifact(
            "world_coordinate_bar_live_edge_failure_20260606",
            default_repo_relative_path="tests/data/world_map/world_coordinate_bar_live_edge_failure_20260606.png",
        )
        ocr_service = _require_rapid_ocr_service(self)
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.open(fixture_path).convert("RGB")
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="world_map_live_coordinate_bar_edge",
                label="world_map_live_coordinate_bar_edge",
            )
            registry = build_default_selector_registry()
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                    selector_registry=registry,
                ),
            ocr_service=ocr_service)

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            assert observation.spatial_surface is not None
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (0, 4))
            self.assertEqual(observation.require(UiElementId.PNC_WORLD_COORDINATE_BAR).extracted_text, "X:0 Y:4")
            search_action_point = observation.require(UiElementId.PNC_WORLD_SEARCH_BUTTON).action_point
            assert search_action_point is not None
            self.assertLess(
                search_action_point[0],
                observation.require(UiElementId.PNC_WORLD_COORDINATE_BAR).bounds.x,
            )

    def test_observation_builder_keeps_live_three_digit_y_inside_world_coordinate_bar_crop(self) -> None:
        """Keeps the canonical coordinate-bar crop wide enough for live three-digit Y values near the HUD edge."""

        fixture_path = require_local_fixture_artifact(
            "world_coordinate_bar_live_y_truncation_20260607",
            default_repo_relative_path="tests/data/world_map/world_coordinate_bar_live_y_truncation_20260607.png",
        )
        ocr_service = _require_rapid_ocr_service(self)
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.open(fixture_path).convert("RGB")
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="world_map_live_coordinate_bar_y_truncation",
                label="world_map_live_coordinate_bar_y_truncation",
            )
            registry = build_default_selector_registry()
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                    selector_registry=registry,
                ),
            ocr_service=ocr_service)

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            assert observation.spatial_surface is not None
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (341, 663))
            self.assertEqual(observation.require(UiElementId.PNC_WORLD_COORDINATE_BAR).extracted_text, "X:341 Y:663")
            search_action_point = observation.require(UiElementId.PNC_WORLD_SEARCH_BUTTON).action_point
            assert search_action_point is not None
            self.assertLess(
                search_action_point[0],
                observation.require(UiElementId.PNC_WORLD_COORDINATE_BAR).bounds.x,
            )
