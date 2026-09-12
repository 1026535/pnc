"""Synthetic build_chat_observation_from_ocr_fallback fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.pnc.capture_vision.make_chat_ocr_fallback_fixture import (
    _make_chat_ocr_fallback_fixture,
)


def _build_chat_observation_from_ocr_fallback(
    *,
    request: ObservationRequest,
    active_channel: ChatChannel | None,
    draft_ocr_text: str | None,
) -> tuple[object, _RecordingOcrService]:
    """Builds one OCR-proven chat observation from the shared geometry-miss fixture."""

    screenshot, registry, ocr_service = _make_chat_ocr_fallback_fixture(
        active_channel=active_channel,
        draft_ocr_text=draft_ocr_text,
    )
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(
            template_matcher=OpenCvTemplateMatcher(),

        ),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(
            selector_registry=registry,
        ),
        ocr_service=ocr_service,
    )
    return builder.build(screenshot, request=request), ocr_service
