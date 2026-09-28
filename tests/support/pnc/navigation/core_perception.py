"""Shared core perception doubles and fixtures."""

from unittest.mock import Mock

from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenEvidence
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrResult,
    OcrService,
)


def _perception(recognizer, guard, *, ocr_service=None):
    backend = ocr_service if ocr_service is not None else getattr(guard, "ocr_service", None)
    if backend is None:
        backend = Mock(spec=OcrService)
        backend.read_result.return_value = OcrResult(lines=(), words=())
    return NavigationPerception(
        recognizer, guard, ScreenClassifier(),
        lambda capture: ObservationOcrContext(capture.image, backend, capture.frame_ref, 'test'),
    )


class Guard:
    def __init__(self, screen=None):
        self.screen = screen
        self.ocr_service = Mock(spec=OcrService)
        self.ocr_service.read_result.return_value = OcrResult(lines=(), words=())

    def detect_interruption(
        self, image, *, ocr_context, owned_dismiss_bounds=(), owned_navigation_screen=None,
    ):
        del image, ocr_context, owned_dismiss_bounds, owned_navigation_screen
        evidence = () if self.screen is None else (ScreenEvidence(self.screen, "test_interruption"),)
        return ObservationAdditions(screen_evidence=evidence, guard_verdict=GuardVerdict.BLOCKED if evidence else GuardVerdict.CLEAR)
