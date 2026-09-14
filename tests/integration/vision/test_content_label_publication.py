"""Production publication of non-actionable OCR labels."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import InputTextAction, TapAction
from pnc_automation.app.pnc.domain.observation import VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_provenance import bind_visible_elements, select_content_labels
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.modal_overlay import with_update_modal
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
LEVEL_BOUNDS = Bounds(122, 245, 45, 23)


def _image(name: str) -> Image.Image:
    """Load one committed visual fixture into an independent RGB image."""

    with Image.open(FIXTURES / name) as source:
        return source.convert("RGB")


def _capture(image: Image.Image, *, session_id: str = "content-label-test") -> CapturedScreenshot:
    """Attach canonical frame provenance to one fixture capture."""

    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _institute_ocr_lines() -> tuple[OcrLine, ...]:
    """Return controlled OCR evidence at the native Institute fixture coordinates."""

    return (
        OcrLine("Institute", Bounds(110, 15, 120, 28), 1.0),
        OcrLine("8/45", LEVEL_BOUNDS, 1.0),
        OcrLine("Glory Level", Bounds(397, 220, 137, 30), 1.0),
        OcrLine("Upgrade", Bounds(404, 254, 104, 40), 1.0),
        OcrLine("Development", Bounds(41, 337, 125, 20), 1.0),
        OcrLine("Economy", Bounds(305, 337, 107, 20), 1.0),
        OcrLine("Military", Bounds(41, 417, 101, 20), 1.0),
        OcrLine("Fortification", Bounds(305, 417, 139, 20), 1.0),
    )


def _production_components(lines: tuple[OcrLine, ...]):
    """Wire both production perception paths to one runtime registry and OCR backend."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    enricher = PncObservationEnricher(selector_registry=registry)
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        ocr_service=_FakeOcrService(lines=lines),
    )
    perception = NavigationPerception(
        builder.visual_recognizer,
        enricher,
        builder.screen_classifier,
        builder.create_ocr_context,
    )
    return registry, builder, perception


class ContentLabelPublicationTests(unittest.TestCase):
    """Keep content labels visible while preserving the independent control boundary."""

    def test_real_builder_and_navigation_publish_institute_level_from_ocr(self) -> None:
        """Both production paths publish the parsed level label with frame-local proof."""

        image = _image("institute_audit.png")
        capture = _capture(image)
        _registry, builder, perception = _production_components(_institute_ocr_lines())

        builder_observation = builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_INSTITUTE),
        )
        navigation_observation = perception.build(capture, include_content=True)

        for observation in (builder_observation, navigation_observation):
            with self.subTest(path="builder" if observation is builder_observation else "navigation"):
                self.assertEqual(observation.screen_type, ScreenType.PNC_INSTITUTE)
                level = observation.require(UiElementId.PNC_BUILDING_LEVEL_LABEL)
                self.assertEqual(level.extracted_text, "8/45")
                self.assertEqual(level.bounds, LEVEL_BOUNDS)
                self.assertEqual(level.source_kind, VisibleElementSourceKind.OCR)
                self.assertFalse(level.identity_evidence)
                self.assertIsNone(level.action_point)
                self.assertEqual(level.frame_ref, capture.frame_ref)
                self.assertEqual(level.source_screen, ScreenType.PNC_INSTITUTE)
                self.assertEqual(level.source_layout_id, observation.decision.layout_id)

        self.assertTrue(navigation_observation.has(UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON))
        self.assertTrue(navigation_observation.has(UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON))
        self.assertNotIn(UiElementId.PNC_BUILDING_UPGRADE_BUTTON, navigation_observation.visible_elements)

    def test_published_labels_cannot_dispatch_taps_or_text_focus(self) -> None:
        """Both paths preserve readable labels without authorizing input to their bounds."""

        capture = _capture(_image("institute_audit.png"))
        registry, builder, perception = _production_components(_institute_ocr_lines())
        observations = {
            "builder": builder.build(
                capture,
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_INSTITUTE),
            ),
            "navigation": perception.build(capture, include_content=True),
        }
        label_id = UiElementId.PNC_BUILDING_LEVEL_LABEL
        actions = (
            TapAction(selector_id=label_id),
            InputTextAction(selector_id=label_id, text="must not be entered"),
        )
        for path, observation in observations.items():
            self.assertEqual(observation.require(label_id).extracted_text, "8/45")
            for action in actions:
                with self.subTest(path=path, action=type(action).__name__):
                    session = FakeSession()
                    executor = ActionExecutor(
                        session=session,
                        selector_registry=registry,
                        stable_click_delay_ms=0,
                        post_action_observe_delay_ms=0,
                        chat_stable_click_delay_ms=0,
                        chat_post_action_observe_delay_ms=0,
                        logger=build_logger(),
                        sleep=lambda _: None,
                    )
                    with self.assertRaisesRegex(SelectorResolutionError, "Label selectors"):
                        executor.execute_action(action, observation)
                    self.assertEqual(session.taps, [])
                    self.assertEqual(session.texts, [])
                    self.assertEqual(executor.input_attempts, 0)

                    # Denial must leave the same frame available for a proved control.
                    control_id = UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON
                    control = observation.require(control_id)
                    self.assertTrue(executor.execute_action(TapAction(selector_id=control_id), observation))
                    self.assertEqual(session.taps, [control.action_point or control.bounds.center()])

    def test_navigation_content_false_and_blocked_or_unknown_frames_have_no_label(self) -> None:
        """Content publication requires an eligible screen and an explicitly requested content pass."""

        image = _image("institute_audit.png")
        _registry, _builder, perception = _production_components(_institute_ocr_lines())
        without_content = perception.build(_capture(image, session_id="content-label-no-content"))
        self.assertFalse(without_content.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))

        blocked_lines = (
            *_institute_ocr_lines(),
            OcrLine(
                "New version detected. Tap Confirm to update.",
                Bounds(58, 380, 420, 28),
                1.0,
            ),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        _registry, _builder, blocked_perception = _production_components(blocked_lines)
        blocked = blocked_perception.build(
            _capture(with_update_modal(image), session_id="content-label-blocked"),
            include_content=True,
        )
        self.assertEqual(blocked.screen_type, ScreenType.PNC_POPUP)
        self.assertFalse(blocked.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))

        _registry, _builder, unknown_perception = _production_components(_institute_ocr_lines())
        unknown = unknown_perception.build(
            _capture(Image.new("RGB", image.size, (80, 80, 80)), session_id="content-label-unknown"),
            include_content=True,
        )
        self.assertEqual(unknown.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(unknown.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))

    def test_label_selection_requires_registry_metadata_and_ocr_source(self) -> None:
        """Labels are selected by interaction metadata, while controls and other sources stay untouched."""

        registry = build_default_selector_registry()
        label = VisibleElement(
            UiElementId.PNC_BUILDING_LEVEL_LABEL,
            LEVEL_BOUNDS,
            0.9,
            source_kind=VisibleElementSourceKind.OCR,
            extracted_text="8/45",
            action_point=(145, 256),
            identity_evidence=True,
        )
        control = VisibleElement(
            UiElementId.PNC_INSTITUTE_UPGRADE_BUTTON,
            Bounds(404, 254, 104, 40),
            1.0,
            source_kind=VisibleElementSourceKind.OCR,
            action_point=(456, 274),
        )
        selected = select_content_labels(
            {label.selector_id: label, control.selector_id: control},
            selector_registry=registry,
        )
        self.assertEqual(set(selected), {UiElementId.PNC_BUILDING_LEVEL_LABEL})
        self.assertFalse(selected[UiElementId.PNC_BUILDING_LEVEL_LABEL].identity_evidence)
        self.assertIsNone(selected[UiElementId.PNC_BUILDING_LEVEL_LABEL].action_point)
        self.assertEqual(selected[UiElementId.PNC_BUILDING_LEVEL_LABEL].extracted_text, "8/45")
        template_label = replace(
            label,
            source_kind=VisibleElementSourceKind.TEMPLATE,
            action_point=None,
            identity_evidence=True,
        )
        self.assertEqual(
            select_content_labels(
                {template_label.selector_id: template_label},
                selector_registry=registry,
            ),
            {},
        )
        self.assertTrue(template_label.identity_evidence)
        self.assertEqual(template_label.bounds, LEVEL_BOUNDS)
        self.assertEqual(select_content_labels({label.selector_id: label}, selector_registry=None), {})
        self.assertIsNone(registry.require(UiElementId.PNC_BUILDING_LEVEL_LABEL).click)
        self.assertEqual(
            registry.require(UiElementId.PNC_BUILDING_LEVEL_LABEL).interaction_kind,
            SelectorInteractionKind.LABEL,
        )

    def test_label_binding_rejects_foreign_frame_and_layout_and_key_mismatch(self) -> None:
        """Shared selection leaves existing provenance checks authoritative."""

        registry = build_default_selector_registry()
        frame = make_captured_frame(_encode_png(Image.new("RGB", (540, 960))), session_id="label-frame")
        label = VisibleElement(
            UiElementId.PNC_BUILDING_LEVEL_LABEL,
            LEVEL_BOUNDS,
            1.0,
            source_kind=VisibleElementSourceKind.OCR,
            extracted_text="8/45",
            frame_ref=frame.frame_ref,
            source_layout_id="institute",
        )
        selected = select_content_labels(
            {label.selector_id: label},
            selector_registry=registry,
        )
        with self.assertRaisesRegex(SelectorResolutionError, "different capture frame"):
            bind_visible_elements(
                selected,
                frame_ref=replace(frame.frame_ref, capture_sequence=frame.frame_ref.capture_sequence + 1),
                source_screen=ScreenType.PNC_INSTITUTE,
                source_layout_id="institute",
            )
        with self.assertRaisesRegex(SelectorResolutionError, "different source layout"):
            bind_visible_elements(
                selected,
                frame_ref=frame.frame_ref,
                source_screen=ScreenType.PNC_INSTITUTE,
                source_layout_id="foreign-layout",
            )

        mismatched = replace(label, selector_id=UiElementId.PNC_INSTITUTE_UPGRADE_BUTTON)
        with self.assertRaisesRegex(SelectorResolutionError, "mapping key"):
            select_content_labels(
                {UiElementId.PNC_BUILDING_LEVEL_LABEL: mismatched},
                selector_registry=registry,
            )


if __name__ == "__main__":
    unittest.main()
