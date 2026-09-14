"""Synthetic build_observation_from_ocr_lines fixture."""

from __future__ import annotations

from collections.abc import Callable

from PIL import Image
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot

from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
    ObservationAdditions,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.mail.build_observation import _build_accepted_observation
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame


def _build_observation_from_ocr_lines(
    lines: tuple[OcrLine, ...],
    *,
    accepted_screen: ScreenType | None = None,
    layout_id: str | None = None,
    image_size: tuple[int, int] = (900, 1600),
    image: Image.Image | None = None,
    semantic_parser: Callable[..., ObservationAdditions] | None = None,
    materialize_geometry: bool = True,
) -> Observation:
    """Build one deterministic observation, optionally after an explicit screen decision.

    The default path remains useful for negative classifier cases. Positive
    semantic cases should provide ``accepted_screen`` so fabricated OCR cannot
    act as screen identity evidence; the canonical enricher then consumes only
    bounded OCR regions for that accepted screen. ``semantic_parser`` is an
    explicit test seam for a canonical parser under test and receives the
    captured image and original line tuple.
    """

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
    active_image = image.copy() if image is not None else Image.new("RGB", image_size, (15, 28, 68))
    frame = make_captured_frame(b"")
    screenshot = CapturedScreenshot(
        artifact=None, image=active_image, image_format="PNG",
        ephemeral_captured_at=frame.frame_ref.captured_at, frame_ref=frame.frame_ref,
    )
    request = ObservationRequest.full_runtime_default()
    if accepted_screen is None:
        return builder.build(screenshot, request=request)

    return _build_accepted_observation(
        builder=builder, screenshot=screenshot, request=request, lines=lines,
        accepted_screen=accepted_screen, layout_id=layout_id,
        semantic_parser=semantic_parser, materialize_geometry=materialize_geometry,
    )
