"""Coordinate dialog local fixtures: verifies the named internal boundary with offline fixtures."""

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
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


class CoordinateDialogLocalFixturesTests(unittest.TestCase):
    """Proves coordinate dialog local fixtures."""

    def test_observation_builder_classifies_live_coordinate_dialog_zero_field_fixture(self) -> None:
        """Replays the live coordinate-jump dialog screenshot where RapidOCR omitted X/Y zero lines."""

        fixture_path = require_local_fixture_artifact(
            "world_coordinate_dialog_zero_fields_live_20260613",
            default_repo_relative_path="tests/data/world_map/world_coordinate_dialog_zero_fields_live_20260613.png",
        )
        ocr_service = _require_rapid_ocr_service(self)
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.open(fixture_path).convert("RGB")
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="live_coordinate_dialog_zero_fixture",
                label="world_coordinate_dialog_zero_fixture",
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

            observation = builder.build(
                screenshot,
                request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD).text, "230")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD).text, "0")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD).text, "0")

    def test_observation_builder_classifies_live_coordinate_dialog_missing_label_fixture(self) -> None:
        """Replays the English live coordinate dialog where one full-screen label was unstable."""

        fixture_path = require_local_fixture_artifact(
            "world_coordinate_dialog_missing_y_label_live_20260614",
            default_repo_relative_path="tests/data/world_map/world_coordinate_dialog_missing_y_label_live_20260614.png",
        )
        ocr_service = _require_rapid_ocr_service(self)
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.open(fixture_path).convert("RGB")
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="live_coordinate_dialog_missing_label_fixture",
                label="world_coordinate_dialog_missing_label_fixture",
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

            observation = builder.build(
                screenshot,
                request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD).text, "226")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD).text, "0")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD).text, "0")
