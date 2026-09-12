"""Coordinate dialog observation: verifies the named internal boundary with offline fixtures."""

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
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.paint_coordinate_dialog_zero_glyph import (
    _paint_coordinate_dialog_zero_glyph,
)


class CoordinateDialogObservationTests(unittest.TestCase):
    """Proves coordinate dialog observation."""

    def test_observation_builder_classifies_live_like_world_coordinate_dialog(self) -> None:
        """Recognizes the inline K/X/Y world-coordinate dialog layout and parses committed field values."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="live_like_world_coordinate_dialog",
                label="world_coordinate_dialog_live_like",
            )
            registry = build_default_selector_registry()
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("K:", x=76, y=398, width=26, height=26),
                            _ocr_line("226", x=132, y=400, width=38, height=24),
                            _ocr_line("X:", x=202, y=398, width=31, height=28),
                            _ocr_line("262", x=257, y=400, width=41, height=24),
                            _ocr_line("Y:", x=334, y=400, width=24, height=23),
                            _ocr_line("436", x=384, y=400, width=42, height=24),
                            _ocr_line("Go", x=253, y=532, width=36, height=26),
                        )
                    ),
                    selector_registry=registry,
                ),
            )

            observation = builder.build(
                screenshot,
                request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON))
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD).text, "226")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD).text, "262")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD).text, "436")

    def test_observation_builder_reads_coordinate_dialog_zero_fields_when_ocr_drops_zero_lines(self) -> None:
        """Keeps live coordinate-jump proof stable when OCR omits single zero-value X/Y field lines."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            registry = build_default_selector_registry()
            image = Image.new("RGB", (540, 960), (15, 28, 68))
            for selector_id in (
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
            ):
                relative_bounds = registry.require(selector_id).relative_bounds
                assert relative_bounds is not None
                _paint_coordinate_dialog_zero_glyph(
                    image,
                    bounds=relative_bounds.materialize_region(image_size=image.size),
                )
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="live_zero_world_coordinate_dialog",
                label="world_coordinate_dialog_zero_fallback",
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("K:", x=76, y=398, width=26, height=26),
                            _ocr_line("230", x=132, y=400, width=41, height=24),
                            _ocr_line("X:", x=202, y=397, width=30, height=29),
                            _ocr_line("Y:", x=332, y=399, width=27, height=25),
                            _ocr_line("Go", x=253, y=532, width=36, height=26),
                        )
                    ),
                    selector_registry=registry,
                ),
            )

            observation = builder.build(
                screenshot,
                request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON))
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD).text, "230")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD).text, "0")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD).text, "0")

    def test_observation_builder_uses_field_proof_when_coordinate_dialog_ocr_misses_one_label(self) -> None:
        """Classifies the coordinate dialog when field-region proof fills one missed full-screen label."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            registry = build_default_selector_registry()
            image = Image.new("RGB", (540, 960), (15, 28, 68))
            for selector_id in (
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
            ):
                relative_bounds = registry.require(selector_id).relative_bounds
                assert relative_bounds is not None
                _paint_coordinate_dialog_zero_glyph(
                    image,
                    bounds=relative_bounds.materialize_region(image_size=image.size),
                )
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="live_missing_y_label_world_coordinate_dialog",
                label="world_coordinate_dialog_missing_y_label",
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("K:", x=76, y=398, width=26, height=26),
                            _ocr_line("226", x=132, y=400, width=41, height=24),
                            _ocr_line("X:", x=202, y=397, width=30, height=29),
                            _ocr_line("Go", x=253, y=532, width=36, height=26),
                        )
                    ),
                    selector_registry=registry,
                ),
            )

            observation = builder.build(
                screenshot,
                request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD).text, "226")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD).text, "0")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD).text, "0")
