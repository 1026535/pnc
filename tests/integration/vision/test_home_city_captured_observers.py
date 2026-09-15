"""Captured Home-city spatial publication through both production observers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import unittest

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


FIXTURE = (
    TEST_DATA_ROOT
    / "screen_recognition"
    / "building_routes"
    / "home_city_blacksmith_anchor_20260914.png"
)


class HomeCityCapturedObserversTests(unittest.TestCase):
    """Protect the real OCR-to-spatial-object contract needed for building focus."""

    def test_both_observers_publish_blacksmith_from_bounded_home_scene_ocr(self) -> None:
        """A current Home capture exposes the same exact object through both observers."""

        with Image.open(FIXTURE) as source:
            image = source.convert("RGB")
        capture = CapturedScreenshot(
            artifact=None,
            image=image,
            image_format="PNG",
            payload=FIXTURE.read_bytes(),
            ephemeral_captured_at=datetime.now(tz=UTC),
        )
        registry = build_default_selector_registry()
        matcher = OpenCvTemplateMatcher()
        recognizer = load_visual_screen_recognizer(matcher=matcher)
        enricher = PncObservationEnricher(selector_registry=registry)
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=ImageSelectorEngine(matcher),
            screen_classifier=ScreenClassifier(),
            enricher=enricher,
            visual_recognizer=recognizer,
            ocr_service=_require_rapid_ocr_service(self),
        )
        navigation = NavigationPerception(
            recognizer,
            enricher,
            ScreenClassifier(),
            builder.create_ocr_context,
        )

        observations = (
            ("observation_builder", builder.build(capture, request=ObservationRequest.full_runtime_default())),
            ("navigation_perception", navigation.build(capture, include_content=True)),
        )
        for observer_name, observation in observations:
            with self.subTest(observer=observer_name):
                self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
                self.assertIsNotNone(observation.spatial_surface)
                assert observation.spatial_surface is not None
                blacksmith = tuple(
                    item
                    for item in observation.spatial_surface.objects
                    if item.metadata.get("home_city_object_id") == "blacksmith"
                )
                self.assertEqual(len(blacksmith), 1)
                self.assertEqual(blacksmith[0].action_point, (458, 422))


if __name__ == "__main__":
    unittest.main()
