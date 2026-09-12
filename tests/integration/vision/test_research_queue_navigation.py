"""Research Queue ownership coverage for the replacement navigator."""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import (
    VisualRecognition,
    load_visual_screen_recognizer,
)
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


FIXTURE = TEST_DATA_ROOT / "screen_recognition" / "research_queue_core.png"


def _capture(*, with_provenance: bool = False) -> CapturedScreenshot:
    """Load the reviewed Research Queue frame into an ephemeral capture."""

    with Image.open(FIXTURE) as source:
        image = source.convert("RGB")
    frame = make_captured_frame(_encode_png(image)) if with_provenance else None
    return CapturedScreenshot(
        artifact=None,
        image=image,
        image_format="PNG",
        payload=None if frame is None else frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=None if frame is None else frame.frame_ref,
    )


def _queue_lines() -> tuple[OcrLine, ...]:
    """Return deterministic OCR evidence for the reviewed idle queue row."""

    return (
        _ocr_line("Research Queue", x=173, y=258, width=196, height=24),
        _ocr_line("1st Research Queue", x=128, y=326, width=163, height=17),
        _ocr_line("Go", x=421, y=343, width=29, height=21),
        _ocr_line("Idle", x=126, y=358, width=33, height=19),
    )


def _perception(ocr: _FakeOcrService, recognizer=None) -> NavigationPerception:
    """Wire canonical navigation perception to deterministic OCR evidence."""

    return NavigationPerception(
        recognizer or load_visual_screen_recognizer(),
        PncObservationEnricher(),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "research-queue-navigation-test",
        ),
    )


class _StaticRecognizer:
    """Returns one prescribed visual result for missing-proof cases."""

    def __init__(self, recognition: VisualRecognition) -> None:
        self.recognition = recognition

    def recognize(self, image: Image.Image) -> VisualRecognition:
        del image
        return self.recognition


class ResearchQueueNavigationTests(unittest.TestCase):
    """Require independent queue identity before bypassing the popup guard."""

    def test_queue_controls_are_registered_for_the_reviewed_queue_screen(self) -> None:
        """Keeps both reviewed Queue actions available to the canonical executor."""

        registry = build_default_selector_registry()
        for selector_id in (
            UiElementId.PNC_RESEARCH_QUEUE_GO,
            UiElementId.PNC_RESEARCH_QUEUE_CLOSE,
        ):
            with self.subTest(selector=selector_id):
                definition = registry.require_supported(selector_id)
                self.assertIn(ScreenType.PNC_RESEARCH_QUEUE, definition.screens)

    def test_action_executor_dispatches_both_measured_queue_controls_with_frame_proof(self) -> None:
        """Dispatches each real visual target through a provenance-valid fake session."""

        registry = build_default_selector_registry()
        session = FakeSession()
        executor = ActionExecutor(
            selector_registry=registry,
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        for selector_id in (
            UiElementId.PNC_RESEARCH_QUEUE_CLOSE,
            UiElementId.PNC_RESEARCH_QUEUE_GO,
        ):
            observation = _perception(
                _FakeOcrService(lines=_queue_lines()),
            ).build(_capture(with_provenance=True))
            self.assertTrue(executor.execute_action(TapAction(selector_id=selector_id), observation))

        self.assertEqual([(488, 269), (435, 354)], session.taps)

    def test_reviewed_idle_queue_is_clear_with_measured_go_and_close(self) -> None:
        """Recognizes the tracked Queue fixture as an actionable typed surface."""

        observation = _perception(_FakeOcrService(lines=_queue_lines())).build(_capture())

        self.assertEqual(ScreenType.PNC_RESEARCH_QUEUE, observation.screen_type)
        self.assertEqual(ScreenType.PNC_RESEARCH_QUEUE, observation.decision.base_screen)
        self.assertEqual(ScreenType.PNC_RESEARCH_QUEUE, observation.decision.effective_screen)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        self.assertFalse(observation.blocking_popup)
        self.assertIsNone(observation.popup_overlay)
        self.assertEqual(
            {
                UiElementId.PNC_RESEARCH_QUEUE_GO,
                UiElementId.PNC_RESEARCH_QUEUE_CLOSE,
            },
            set(observation.visible_elements),
        )

        go = observation.require(UiElementId.PNC_RESEARCH_QUEUE_GO)
        close = observation.require(UiElementId.PNC_RESEARCH_QUEUE_CLOSE)
        self.assertEqual(Bounds(416, 343, 39, 22), go.bounds)
        self.assertEqual((435, 354), go.action_point)
        self.assertEqual(Bounds(471, 253, 34, 32), close.bounds)
        self.assertEqual((488, 269), close.action_point)
        self.assertEqual(VisibleElementSourceKind.TEMPLATE, go.source_kind)
        self.assertEqual(VisibleElementSourceKind.TEMPLATE, close.source_kind)

    def test_update_popup_above_queue_stays_blocking_and_hides_queue_controls(self) -> None:
        """Keeps an exact update modal as the foreground owner over Queue evidence."""

        lines = _queue_lines() + (
            _ocr_line(
                "New version detected. Tap Confirm to update.",
                x=58,
                y=380,
                width=420,
                height=28,
            ),
            _ocr_line("Confirm", x=221, y=531, width=90, height=27),
        )
        observation = _perception(_FakeOcrService(lines=lines)).build(_capture())

        self.assertEqual(ScreenType.PNC_POPUP, observation.screen_type)
        self.assertEqual(ScreenType.PNC_RESEARCH_QUEUE, observation.decision.base_screen)
        self.assertTrue(observation.blocking_popup)
        self.assertEqual(GuardVerdict.BLOCKED, observation.decision.guard)
        self.assertTrue(observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_RESEARCH_QUEUE_GO))
        self.assertFalse(observation.has(UiElementId.PNC_RESEARCH_QUEUE_CLOSE))

    def test_missing_visual_or_dismiss_proof_keeps_legacy_queue_guard(self) -> None:
        """Requires both reviewed identity and its measured close before queue ownership."""

        close = VisibleElement(
            UiElementId.PNC_RESEARCH_QUEUE_CLOSE,
            Bounds(471, 253, 34, 32),
            confidence=1.0,
            source_kind=VisibleElementSourceKind.TEMPLATE,
            action_point=(488, 269),
        )
        cases = {
            "missing_visual": VisualRecognition(),
            "missing_close": VisualRecognition(
                evidence=(ScreenEvidence(ScreenType.PNC_RESEARCH_QUEUE, "visual_queue"),),
                controls=(close,),
            ),
        }
        for name, recognition in cases.items():
            with self.subTest(case=name):
                observation = _perception(
                    _FakeOcrService(lines=_queue_lines()),
                    recognizer=_StaticRecognizer(recognition),
                ).build(_capture())

                self.assertEqual(ScreenType.PNC_POPUP, observation.screen_type)
                self.assertTrue(observation.blocking_popup)
                self.assertEqual(GuardVerdict.BLOCKED, observation.decision.guard)
                self.assertEqual({}, observation.visible_elements)
                self.assertIsNone(observation.popup_overlay)


if __name__ == "__main__":
    unittest.main()
