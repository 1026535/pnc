"""Live Common Victory preview identity and its measured, owned close control."""

from datetime import UTC, datetime
import unittest
from unittest.mock import Mock

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.domain.popup import decide_popup_recovery
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.ocr.ocr_service import OcrResult, OcrService
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.support.paths import TEST_DATA_ROOT


class CommonVictoryPreviewProfileTests(unittest.TestCase):
    """Keep reference resizing distinct from independent capture evidence."""

    def setUp(self):
        with Image.open(TEST_DATA_ROOT / "screen_recognition/bag_common_victory_preview_20260916.png") as source:
            self.image = source.convert("RGB")
        registry = build_default_selector_registry()
        matcher = OpenCvTemplateMatcher()
        backend = Mock(spec=OcrService)
        backend.read_result.return_value = OcrResult(lines=(), words=())
        enricher = PncObservationEnricher(selector_registry=registry)
        self.builder = ObservationBuilder(
            selector_registry=registry, selector_engine=ImageSelectorEngine(matcher),
            screen_classifier=ScreenClassifier(), enricher=enricher, ocr_service=backend,
            visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        )
        self.navigation = NavigationPerception(
            self.builder.visual_recognizer, enricher, ScreenClassifier(), self.builder.create_ocr_context,
        )

    def publish(self, image):
        now = datetime.now(UTC)
        capture = CapturedScreenshot(
            None, image, "PNG", ephemeral_captured_at=now,
            frame_ref=FrameRef("common-preview-profile", 1, 1, 0, now),
        )
        return self.builder.build(capture), self.navigation.build(capture)

    def test_both_publishers_keep_preview_and_own_native_close(self):
        for size in ((900, 1600), (540, 960)):
            for observation in self.publish(self.image.resize(size, Image.Resampling.LANCZOS)):
                with self.subTest(size=size, screen=observation.screen_type):
                    self.assertEqual(ScreenType.PNC_BAG_CHEST_PREVIEW, observation.screen_type)
                    self.assertEqual("bag_common_victory_preview", observation.decision.layout_id)
                    self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                    self.assertFalse(observation.blocking_popup)
                    close = observation.require(UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE)
                    self.assertEqual(VisibleElementSourceKind.TEMPLATE, close.source_kind)
                    self.assertEqual(observation.frame_ref, close.frame_ref)
                    self.assertEqual("bag_common_victory_preview", close.source_layout_id)
                    x, y = close.action_point
                    self.assertTrue(470 <= x * 540 / size[0] <= 505)
                    self.assertTrue(145 <= y * 960 / size[1] <= 185)
                    self.assertIsNone(decide_popup_recovery(
                        screen_type=observation.screen_type, blocking_popup=observation.blocking_popup,
                        visible_selector_ids=frozenset(observation.visible_elements),
                        popup_overlay=observation.popup_overlay,
                    ))

    def test_hidden_close_does_not_inherit_an_action_from_panel_identity(self):
        observation = self.publish(self.image)[0]
        close = observation.require(UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE).bounds
        obscured = self.image.copy()
        ImageDraw.Draw(obscured).rectangle(
            (close.x - 2, close.y - 2, close.x + close.width + 2, close.y + close.height + 2),
            fill="black",
        )
        for result in self.publish(obscured):
            self.assertFalse(result.has(UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE))


if __name__ == "__main__":
    unittest.main()
