"""Synthetic build_observation_from_ocr_lines fixture."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame


def _build_observation_from_ocr_lines(lines: tuple[OcrLine, ...]) -> Observation:
    """Builds one full-runtime observation from deterministic OCR lines and reviewed geometry."""

    registry = build_default_selector_registry()
    ocr_service = _FakeOcrService(lines=lines)
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
    screenshot = type(
        "Captured",
        (),
        {
            "image": Image.new("RGB", (900, 1600), (15, 28, 68)),
            "artifact": type("Artifact", (), {"path": Path("hero_arena_synthetic.png"), "captured_at": None})(),
            "frame_ref": make_captured_frame(b"").frame_ref,
        },
    )()
    return builder.build(screenshot, request=ObservationRequest.full_runtime_default())
