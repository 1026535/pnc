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


def _build_observation_from_ocr_lines(lines: tuple[OcrLine, ...]) -> Observation:
    """Builds one full-runtime observation from deterministic OCR lines and reviewed geometry."""

    registry = build_default_selector_registry()
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(
            template_matcher=OpenCvTemplateMatcher(),
            ocr_service=UnavailableOcrService(),
        ),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(
            ocr_service=_FakeOcrService(lines=lines),
            selector_registry=registry,
        ),
    )
    screenshot = type(
        "Captured",
        (),
        {
            "image": Image.new("RGB", (900, 1600), (15, 28, 68)),
            "artifact": type("Artifact", (), {"path": Path("hero_arena_synthetic.png"), "captured_at": None})(),
        },
    )()
    return builder.build(screenshot, request=ObservationRequest.full_runtime_default())
