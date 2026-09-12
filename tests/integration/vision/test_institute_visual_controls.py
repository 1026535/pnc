"""Institute visual-control coverage for the reviewed anchor profile."""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

from PIL import Image

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

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService


FIXTURE_PATH = TEST_DATA_ROOT / "screen_recognition" / "institute_audit.png"
CONTROL_BOXES = {
    UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON: (14, 315, 248, 67),
    UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON: (278, 315, 250, 67),
    UiElementId.PNC_INSTITUTE_MILITARY_BUTTON: (14, 394, 248, 68),
    UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON: (278, 394, 250, 68),
}
EXPECTED_CONTROLS = {
    UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON: (Bounds(14, 315, 248, 67), (138, 348)),
    UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON: (Bounds(278, 315, 250, 67), (403, 348)),
    UiElementId.PNC_INSTITUTE_MILITARY_BUTTON: (Bounds(14, 394, 248, 68), (138, 428)),
    UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON: (Bounds(278, 394, 250, 68), (403, 428)),
}
EXPECTED_SCALED_CONTROLS = {
    UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON: (Bounds(23, 525, 414, 112), (230, 581)),
    UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON: (Bounds(463, 525, 417, 112), (671, 581)),
    UiElementId.PNC_INSTITUTE_MILITARY_BUTTON: (Bounds(23, 657, 414, 113), (230, 713)),
    UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON: (Bounds(463, 657, 417, 113), (671, 713)),
}


def _capture(image: Image.Image) -> CapturedScreenshot:
    """Wrap one deterministic image in the canonical capture model."""

    return CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))


def _load_fixture() -> Image.Image:
    """Load the reviewed Institute fixture without retaining an open file handle."""

    with Image.open(FIXTURE_PATH) as source:
        return source.convert("RGB")


def _observation_builder(ocr_lines: tuple[OcrLine, ...]) -> ObservationBuilder:
    """Wire the production observation path to deterministic OCR lines."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        ocr_service=_RecordingOcrService(lines=ocr_lines),
    )


class InstituteVisualControlTests(unittest.TestCase):
    """Require the measured Institute category controls to remain bounded."""

    def test_controls_match_fixture_and_resized_fixture(self) -> None:
        """Recognizes each measured control at both reviewed viewport sizes."""

        recognizer = load_visual_screen_recognizer()
        source = _load_fixture()
        for size, expected in (
            ((540, 960), EXPECTED_CONTROLS),
            ((900, 1600), EXPECTED_SCALED_CONTROLS),
        ):
            with self.subTest(size=size):
                recognition = recognizer.recognize(source.resize(size))
                self.assertEqual(recognition.profile_ids, ("institute",))
                self.assertEqual(
                    {item.screen_type for item in recognition.evidence},
                    {ScreenType.PNC_INSTITUTE},
                )
                controls = {item.selector_id: item for item in recognition.controls}
                for selector_id, (bounds, action_point) in expected.items():
                    with self.subTest(selector=selector_id):
                        control = controls[selector_id]
                        self.assertEqual(control.bounds, bounds)
                        self.assertEqual(control.action_point, action_point)
                        self.assertGreaterEqual(control.confidence, 0.97)

    def test_erased_development_interior_preserves_identity_without_control(self) -> None:
        """A missing category must abstain while the Institute identity remains visible."""

        image = _load_fixture()
        x, y, width, height = CONTROL_BOXES[UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON]
        image.paste((0, 0, 0), (x, y, x + width, y + height))

        recognition = load_visual_screen_recognizer().recognize(image)
        self.assertEqual(recognition.profile_ids, ("institute",))
        control_ids = {item.selector_id for item in recognition.controls}
        self.assertNotIn(UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON, control_ids)
        self.assertIn(UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON, control_ids)
        self.assertIn(UiElementId.PNC_INSTITUTE_MILITARY_BUTTON, control_ids)
        self.assertIn(UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON, control_ids)

    def test_swapped_development_and_economy_interiors_abstain_at_original_regions(self) -> None:
        """A category anchor must not accept the other category at its original location."""

        image = _load_fixture()
        development = image.crop((14, 315, 262, 382))
        economy = image.crop((278, 315, 528, 382))
        image.paste(economy.resize((248, 67)), (14, 315))
        image.paste(development.resize((250, 67)), (278, 315))

        recognition = load_visual_screen_recognizer().recognize(image)
        self.assertEqual(recognition.profile_ids, ("institute",))
        control_ids = {item.selector_id for item in recognition.controls}
        self.assertNotIn(UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON, control_ids)
        self.assertNotIn(UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON, control_ids)
        self.assertIn(UiElementId.PNC_INSTITUTE_MILITARY_BUTTON, control_ids)
        self.assertIn(UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON, control_ids)

    def test_blocking_popup_suppresses_institute_background_controls(self) -> None:
        """A blocking update popup owns the frame even when Institute anchors remain visible."""

        popup_lines = (
            OcrLine(
                "New version detected. Tap Confirm to update.",
                Bounds(58, 380, 420, 28),
                1.0,
            ),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        observation = _observation_builder(popup_lines).build(
            _capture(_load_fixture()),
            request=ObservationRequest.base(),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertTrue(observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
        self.assertFalse(
            any(
                selector_id in observation.visible_elements
                for selector_id in EXPECTED_CONTROLS
            )
        )


if __name__ == "__main__":
    unittest.main()
