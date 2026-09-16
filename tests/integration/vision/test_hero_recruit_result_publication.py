"""Saved Hero Hall results pass real OCR, phase ownership and both publishers."""

from datetime import UTC, datetime
import hashlib
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.hero_recruit_result import HeroRecruitResultPhase
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


class HeroRecruitResultPublicationTests(unittest.TestCase):
    def _publishers(self):
        registry = build_default_selector_registry()
        matcher = OpenCvTemplateMatcher()
        builder = ObservationBuilder(
            selector_registry=registry, selector_engine=ImageSelectorEngine(matcher),
            screen_classifier=ScreenClassifier(), enricher=PncObservationEnricher(selector_registry=registry),
            visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
            ocr_service=_require_rapid_ocr_service(self),
        )
        navigation = NavigationPerception(builder.visual_recognizer, builder.enricher,
                                         builder.screen_classifier, builder.create_ocr_context)
        return builder, navigation

    def test_native_results_publish_observed_content_and_only_the_owned_acknowledgment(self):
        builder, navigation = self._publishers()
        for phase, expected_title, expected_control in (
            ("presentation", "Albertus", UiElementId.PNC_HERO_RESULT_CONFIRM),
            ("fragments", "Albertus Frag.", UiElementId.PNC_HERO_RESULT_CLOSE),
        ):
            path = TEST_DATA_ROOT / "screen_recognition" / f"hero_recruit_{phase}_20260913.png"
            with Image.open(path) as source:
                image = source.convert("RGB")
            for index, publisher in enumerate((builder, navigation), 1):
                with self.subTest(phase=phase, publisher=type(publisher).__name__):
                    now = datetime.now(tz=UTC)
                    frame_ref = FrameRef(session_id=f"hero-result-{phase}", session_epoch=1,
                                         capture_sequence=index, input_sequence=0, captured_at=now)
                    capture = CapturedScreenshot(artifact=None, image=image, image_format="PNG", frame_ref=frame_ref,
                                                 ephemeral_captured_at=now)
                    observation = (builder.build(capture, request=ObservationRequest.full_runtime_default())
                                   if publisher is builder else navigation.build(capture, include_content=True))
                    self.assertEqual(ScreenType.PNC_HERO_RECRUIT_RESULT, observation.screen_type)
                    self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                    self.assertEqual(f"hero_recruit_{phase}", observation.decision.layout_id)
                    self.assertEqual(hashlib.sha256(image.tobytes()).hexdigest(), observation.frame_fingerprint)
                    facts = observation.hero_recruit_result
                    self.assertIsNotNone(facts)
                    self.assertEqual(expected_title, facts.title_text)
                    self.assertEqual(frame_ref, facts.frame_ref)
                    self.assertEqual(observation.screen_type, facts.source_screen)
                    self.assertEqual(observation.decision.layout_id, facts.source_layout_id)
                    if phase == "presentation":
                        self.assertEqual(HeroRecruitResultPhase.HERO_PRESENTATION, facts.phase)
                        self.assertEqual(2, facts.star_count)
                        self.assertIsNone(facts.quantity)
                        self.assertIsNone(facts.items_left)
                        self.assertIsNone(facts.recruit_cost)
                    else:
                        self.assertEqual(HeroRecruitResultPhase.FRAGMENT_RESULT, facts.phase)
                        self.assertEqual(10, facts.quantity)
                        self.assertEqual(8, facts.items_left)
                        self.assertEqual(1, facts.recruit_cost)
                        self.assertIsNone(facts.star_count)
                    self.assertEqual({expected_control}, set(observation.visible_elements))
                    control = observation.require(expected_control)
                    self.assertEqual(VisibleElementSourceKind.TEMPLATE, control.source_kind)
                    self.assertEqual(frame_ref, control.frame_ref)
                    self.assertEqual(observation.decision.layout_id, control.source_layout_id)
                    self.assertTrue(control.bounds.contains_point(control.action_point))

    def test_shared_backdrop_does_not_confuse_result_phases_or_the_ordinary_menu(self):
        recognizer = load_visual_screen_recognizer()
        for filename, expected in (
            ("hero_recruit_presentation_20260913.png", {"hero_recruit_presentation"}),
            ("hero_recruit_fragments_20260913.png", {"hero_recruit_fragments"}),
            ("hero_hall.png", set()),
            ("hero_hall_aug29.png", set()),
        ):
            with self.subTest(filename=filename):
                with Image.open(TEST_DATA_ROOT / "screen_recognition" / filename) as image:
                    recognition = recognizer.recognize(image.convert("RGB"))
                self.assertEqual(expected, {item.layout_id for item in recognition.evidence
                    if item.screen_type == ScreenType.PNC_HERO_RECRUIT_RESULT})

    def test_missing_acknowledgment_is_never_recovered_from_backdrop_or_paid_button(self):
        recognizer = load_visual_screen_recognizer()
        for phase, box, selector in (
            ("presentation", (290, 1400, 610, 1510), UiElementId.PNC_HERO_RESULT_CONFIRM),
            ("fragments", (75, 1430, 390, 1530), UiElementId.PNC_HERO_RESULT_CLOSE),
        ):
            with self.subTest(phase=phase):
                path = TEST_DATA_ROOT / "screen_recognition" / f"hero_recruit_{phase}_20260913.png"
                with Image.open(path) as source:
                    image = source.convert("RGB")
                image.paste((0, 0, 0), box)
                recognition = recognizer.recognize(image)
                self.assertNotIn(selector, {element.selector_id for element in recognition.controls})
