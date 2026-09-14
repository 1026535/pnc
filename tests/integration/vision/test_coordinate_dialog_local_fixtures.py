"""Coordinate dialog local fixtures: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from pnc_automation.core.vision.ocr.ocr_service import OcrReadPurpose

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


def _wire_fake_ocr() -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire both perception paths to the captured visual recognizer and empty OCR."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    recognizer = load_visual_screen_recognizer(matcher=matcher)
    enricher = PncObservationEnricher(selector_registry=registry)
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(template_matcher=matcher),
        screen_classifier=ScreenClassifier(),
        visual_recognizer=recognizer,
        enricher=enricher,
        ocr_service=_FakeOcrService(lines=()),
    )
    return builder, NavigationPerception(
        recognizer,
        enricher,
        ScreenClassifier(),
        builder.create_ocr_context,
    )


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
                visual_recognizer=load_visual_screen_recognizer(),
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

    def test_zero_field_fixture_has_builder_navigation_content_parity_and_no_passive_field_reads(self) -> None:
        """The accepted dialog owns the same K/X/Y content in both paths."""

        fixture_path = require_local_fixture_artifact(
            "world_coordinate_dialog_zero_fields_live_20260613",
            default_repo_relative_path="tests/data/world_map/world_coordinate_dialog_zero_fields_live_20260613.png",
        )
        ocr_service = _require_rapid_ocr_service(self)
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            image = Image.open(fixture_path).convert("RGB")
            screenshot = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts")).capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="coordinate_dialog_parity",
                label="zero_fields",
            )
            builder, _ = _wire_fake_ocr()
            builder.ocr_service = ocr_service
            contexts = []

            def context_factory(capture):
                context = builder.create_ocr_context(capture)
                contexts.append(context)
                return context

            assert builder.visual_recognizer is not None
            navigation = NavigationPerception(
                builder.visual_recognizer,
                builder.enricher,
                builder.screen_classifier,
                context_factory,
            )
            built = builder.build(
                screenshot,
                request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            )
            perceived = navigation.build(screenshot, include_content=True)
            for observation in (built, perceived):
                self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)
                self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON))
                self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON))
            self.assertEqual(built.decision.layout_id, perceived.decision.layout_id)
            selectors = (
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
            )
            self.assertEqual(
                tuple(built.require_text_field_state(selector).text for selector in selectors),
                ("230", "0", "0"),
            )
            self.assertEqual(
                tuple(perceived.require_text_field_state(selector).text for selector in selectors),
                ("230", "0", "0"),
            )
            passive = navigation.build(screenshot, include_content=False)
            self.assertEqual(passive.text_field_states, {})
            self.assertEqual(
                [read.purpose for read in contexts[-1].read_diagnostics],
                [OcrReadPurpose.GUARD],
            )

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
                visual_recognizer=load_visual_screen_recognizer(),
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

    def test_missing_modal_identity_abstains_on_both_perception_paths(self) -> None:
        """A frame without the captured modal identity cannot expose dialog controls."""

        source = Image.open(
            TEST_DATA_ROOT
            / "world_map"
            / "world_coordinate_dialog_zero_fields_live_20260613.png"
        ).convert("RGB")
        draw = ImageDraw.Draw(source)
        # Remove every independently reviewed identity patch, including the
        # legacy profile's close-button patch.  The remaining frame is not a
        # coordinate-dialog identity and must not acquire modal controls.
        for bounds in (
            (20, 307, 464, 350),
            (71, 394, 106, 428),
            (199, 394, 234, 428),
            (327, 394, 362, 428),
            (467, 307, 510, 351),
        ):
            draw.rectangle(bounds, fill=(15, 28, 68))
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts")).capture(
                _FakeScreenshotSession(_encode_png(source)),
                artifact_directory="coordinate_dialog_missing_identity",
                label="coordinate_dialog_missing_identity",
            )
            for path in ("builder", "navigation"):
                with self.subTest(path=path):
                    builder, _ = _wire_fake_ocr()
                    # Even plausible OCR must not replace the erased visual identity.
                    builder.ocr_service = _FakeOcrService(lines=(
                        _ocr_line("K:", x=76, y=398, width=26, height=26),
                        _ocr_line("230", x=132, y=400, width=38, height=24),
                        _ocr_line("X:", x=202, y=398, width=31, height=28),
                        _ocr_line("262", x=257, y=400, width=41, height=24),
                        _ocr_line("Y:", x=334, y=398, width=24, height=23),
                        _ocr_line("436", x=384, y=400, width=42, height=24),
                        _ocr_line("Go", x=253, y=532, width=36, height=26),
                    ))
                    context = builder.create_ocr_context(screenshot)
                    navigation = NavigationPerception(
                        builder.visual_recognizer,
                        builder.enricher,
                        builder.screen_classifier,
                        lambda capture: context,
                    )
                    observation = (
                        builder.build(
                            screenshot,
                            request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
                            ocr_context=context,
                        )
                        if path == "builder"
                        else navigation.build(screenshot, include_content=True)
                    )
                    self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
                    self.assertEqual(observation.text_field_states, {})
                    self.assertEqual(
                        [read.purpose for read in context.read_diagnostics],
                        [OcrReadPurpose.GUARD],
                    )
                    self.assertFalse(
                        observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON)
                    )
                    self.assertFalse(
                        observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON)
                    )

    def test_missing_field_keeps_independent_dialog_identity_and_other_fields(self) -> None:
        """A blank X field cannot erase the accepted dialog or invent a zero."""

        source = Image.open(
            TEST_DATA_ROOT / "world_map/world_coordinate_dialog_zero_fields_live_20260613.png"
        ).convert("RGB")
        ImageDraw.Draw(source).rectangle((235, 389, 328, 436), fill=(15, 28, 68))
        with tempfile.TemporaryDirectory() as temp_directory:
            screenshot = ScreenshotService(
                artifact_store=ArtifactStore(root=Path(temp_directory) / "artifacts"),
            ).capture(
                _FakeScreenshotSession(_encode_png(source)),
                artifact_directory="coordinate_dialog_missing_x",
                label="missing_x",
            )
            for path in ("builder", "navigation"):
                with self.subTest(path=path):
                    builder, navigation = _wire_fake_ocr()
                    builder.ocr_service = _FakeOcrService(lines=(
                        _ocr_line("K:", x=76, y=398, width=26, height=26),
                        _ocr_line("230", x=132, y=400, width=38, height=24),
                        _ocr_line("X:", x=202, y=398, width=31, height=28),
                        _ocr_line("Y:", x=334, y=398, width=24, height=23),
                        _ocr_line("0", x=384, y=400, width=16, height=24),
                        _ocr_line("Go", x=253, y=532, width=36, height=26),
                    ))
                    observation = (
                        builder.build(
                            screenshot,
                            request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
                        )
                        if path == "builder"
                        else navigation.build(screenshot, include_content=True)
                    )
                    self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)
                    self.assertEqual(
                        observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD).text,
                        "230",
                    )
                    self.assertEqual(
                        observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD).text,
                        "0",
                    )
                    self.assertNotIn(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD, observation.text_field_states)
                    self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON))
                    self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON))

    def test_missing_go_button_never_gets_a_synthetic_point_on_both_paths(self) -> None:
        """The captured dialog identity survives a missing Go button without publishing it."""

        source = Image.open(
            TEST_DATA_ROOT
            / "world_map"
            / "world_coordinate_dialog_missing_y_label_live_20260614.png"
        ).convert("RGB")
        ImageDraw.Draw(source).rectangle((178, 520, 361, 572), fill=(15, 28, 68))
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts")).capture(
                _FakeScreenshotSession(_encode_png(source)),
                artifact_directory="coordinate_dialog_missing_go",
                label="coordinate_dialog_missing_go",
            )
            for path in ("builder", "navigation"):
                with self.subTest(path=path):
                    builder, navigation = _wire_fake_ocr()
                    observation = (
                        builder.build(
                            screenshot,
                            request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
                        )
                        if path == "builder"
                        else navigation.build(screenshot, include_content=False)
                    )
                    self.assertEqual(
                        observation.screen_type,
                        ScreenType.PNC_WORLD_COORDINATE_DIALOG,
                    )
                    self.assertFalse(
                        observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON)
                    )
                    self.assertTrue(
                        observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON)
                    )
