"""Dual publisher-logo startup recognition and guard regression coverage."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService


FIXTURE = TEST_DATA_ROOT / "screen_recognition" / "loading_publisher_splash.png"


class PublisherSplashRecognitionTests(unittest.TestCase):
    """Keep startup loading passive and require both reviewed logo anchors."""

    def test_dual_publisher_splash_is_loading_without_controls_at_both_viewports(self) -> None:
        """The reviewed startup frame remains a passive loading observation."""

        perception = _perception()
        capture = _capture()
        for size in ((540, 960), (900, 1600)):
            with self.subTest(size=size):
                observation = perception.build(replace(capture, image=capture.image.resize(size)))
                self.assertEqual(ScreenType.PNC_LOADING, observation.screen_type)
                self.assertFalse(observation.blocking_popup)
                self.assertEqual({}, observation.visible_elements)

    def test_missing_either_publisher_logo_abstains_as_unknown(self) -> None:
        """A single logo or unrelated bright startup content cannot pass the gate."""

        perception = _perception()
        capture = _capture()
        for missing_logo in ((110, 385, 435, 455), (135, 480, 405, 540)):
            with self.subTest(missing_logo=missing_logo):
                image = capture.image.resize((540, 960))
                image.paste((0, 0, 0), missing_logo)
                observation = perception.build(replace(capture, image=image))
                self.assertEqual(ScreenType.UNKNOWN, observation.screen_type)
                self.assertEqual({}, observation.visible_elements)


def _capture() -> CapturedScreenshot:
    """Load the committed startup frame into the canonical capture model."""

    with Image.open(FIXTURE) as source:
        image = source.convert("RGB")
    return CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))


def _perception() -> NavigationPerception:
    """Wire deterministic empty OCR into the production perception boundary."""

    ocr = _FakeOcrService(lines=())
    return NavigationPerception(
        recognizer=load_visual_screen_recognizer(),
        guard=PncObservationEnricher(),
        screen_classifier=ScreenClassifier(),
        create_ocr_context=lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "publisher-splash-test",
        ),
    )
