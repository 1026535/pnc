"""Visual identity, scope independence, and topmost-overlay regression coverage."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageEnhance

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.test_capture_and_vision import _RecordingOcrService


FIXTURES = Path(__file__).parent / "data" / "screen_recognition"


def _capture(name: str) -> CapturedScreenshot:
    """Load a committed frame into the canonical ephemeral capture model."""
    with Image.open(FIXTURES / name) as source:
        image = source.convert("RGB")
    return CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))


def _builder(ocr: _RecordingOcrService) -> ObservationBuilder:
    """Wire deterministic OCR into the existing observation and visual components."""
    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        ocr_service=ocr,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )


class VisualScreenRecognizerTests(unittest.TestCase):
    """Require distinct tabs, conservative matches, and intact global guard ordering."""

    def test_reviewed_reference_profiles_and_separate_day_positives(self) -> None:
        recognizer = load_visual_screen_recognizer()
        manifest = json.loads((FIXTURES / "manifest.json").read_text())
        excluded = {"home_negative.png", "store_negative.png", "disconnect_negative.png", "update_over_bag.png"}
        for sample in manifest["samples"]:
            if sample["image"] in excluded:
                continue
            with self.subTest(image=sample["image"]):
                result = recognizer.recognize(_capture(sample["image"]).image)
                expected_visual_screens = sample.get("expected_visual_screens")
                self.assertIsInstance(expected_visual_screens, list)
                self.assertEqual(
                    {item.screen_type.name for item in result.evidence},
                    set(expected_visual_screens),
                )

    def test_unknown_blank_dimmed_and_wrong_aspect_frames_abstain(self) -> None:
        recognizer = load_visual_screen_recognizer()
        hero = _capture("hero_hall.png").image
        for image in (
            Image.new("RGB", (540, 960)),
            ImageEnhance.Brightness(hero).enhance(0.45),
            hero.resize((700, 960)),
            _capture("store_negative.png").image,
            _capture("disconnect_negative.png").image,
        ):
            self.assertEqual(recognizer.recognize(image).evidence, ())

    def test_city_profiles_scale_and_require_description_as_well_as_header(self) -> None:
        recognizer = load_visual_screen_recognizer()
        for name, screen in (
            ("institute", ScreenType.PNC_INSTITUTE),
            ("goddess_statue", ScreenType.PNC_GODDESS_STATUE),
            ("warehouse", ScreenType.PNC_WAREHOUSE),
        ):
            with self.subTest(screen=screen):
                source = _capture(f"{name}_audit.png").image
                for size in ((540, 960), (900, 1600)):
                    recognition = recognizer.recognize(source.resize(size))
                    self.assertEqual({item.screen_type for item in recognition.evidence}, {screen})
                obscured = source.copy()
                obscured.paste((0, 0, 0), (280, 140, 535, 187))
                self.assertEqual(recognizer.recognize(obscured).evidence, ())

    def test_scope_cannot_hide_hero_hall_and_identity_does_not_invent_recruit(self) -> None:
        ocr = _RecordingOcrService(lines=())
        observation = _builder(ocr).build(_capture("hero_hall.png"), request=ObservationRequest.daily_quest_follow_up())
        self.assertEqual(observation.screen_type, ScreenType.PNC_HERO_HALL)
        self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
        self.assertFalse(observation.has(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON))
        self.assertGreater(ocr.read_result_calls, 0, "Visual evidence must still run the global popup guard.")

    def test_hero_hall_back_click_is_inside_manually_reviewed_arrow(self) -> None:
        # At 540x960 the gold arrow occupies x=20..80, y=5..47.
        # Use its interior, not the selector's own bounds, as the click oracle.
        for width, height in ((540, 960), (900, 1600)):
            capture = _capture("hero_hall.png")
            capture = replace(capture, image=capture.image.resize((width, height)))
            observation = _builder(_RecordingOcrService(lines=())).build(capture)
            bounds = observation.visible_elements[UiElementId.PNC_BACK_BUTTON_TOP_LEFT].bounds
            center_x = (bounds.x + bounds.width / 2) * 540 / width
            center_y = (bounds.y + bounds.height / 2) * 960 / height
            self.assertTrue(20 <= center_x <= 80 and 5 <= center_y <= 47)

    def test_update_over_bag_overrides_header_and_removes_bag_controls(self) -> None:
        ocr = _RecordingOcrService(lines=(
            OcrLine("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28), 1.0),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        ))
        builder = _builder(ocr)
        capture = _capture("update_over_bag.png")
        self.assertEqual(builder.visual_recognizer.recognize(capture.image).evidence[0].screen_type, ScreenType.PNC_BAG)
        observation = builder.build(capture, request=ObservationRequest.base())
        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertTrue(observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_BAG_USE_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))

    def test_invitation_never_exposes_underlying_home_controls(self) -> None:
        observation = _builder(_RecordingOcrService(lines=())).build(_capture("alliance_invitation.png"))
        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertFalse(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_competing_visual_screens_abstain_without_actionable_geometry(self) -> None:
        builder = _builder(_RecordingOcrService(lines=()))
        recognizer = builder.visual_recognizer
        original = recognizer.profiles[0]
        builder.visual_recognizer = replace(
            recognizer,
            profiles=(original, replace(original, id="conflict", screen_type=ScreenType.PNC_BAG)),
        )
        observation = builder.build(_capture("hero_hall.png"))
        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertEqual(observation.visible_elements, {})

    def test_movement_proof_never_calls_global_visual_recognition(self) -> None:
        builder = _builder(_RecordingOcrService(lines=()))
        class ForbiddenRecognizer:
            def recognize(self, image: Image.Image) -> None:
                raise AssertionError("Coordinate-only proof must retain its dedicated fast path.")
        builder.visual_recognizer = ForbiddenRecognizer()
        builder.build(_capture("hero_hall.png"), request=ObservationRequest.world_map_movement_proof_follow_up())

    def test_invalid_catalog_fails_before_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            for document in (
                {},
                {"version": 2, "reference_size": [540, 960], "profiles": []},
                {"version": 1, "reference_size": [0, 960], "profiles": []},
                {"version": 1, "reference_size": [540, 960], "profiles": [{"id": "bad", "screen": "PNC_BAG", "anchors": []}]},
            ):
                path.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    load_visual_screen_recognizer(path)


if __name__ == "__main__":
    unittest.main()
