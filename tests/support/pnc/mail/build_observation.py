"""Synthetic build_observation fixture."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, ScreenshotService
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
    ObservationAdditions,
)
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    compile_screen_content_ocr_region_plans,
    execute_ocr_region_plans,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.mail.fake_ocr_service import _FakeOcrService
from tests.support.pnc.mail.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.mail.build_chat_fixture_image import _build_chat_fixture_image
from tests.support.pnc.mail.encode_png import _encode_png


def _build_observation(
    *,
    request: ObservationRequest,
    lines: tuple[OcrLine, ...],
    image_size: tuple[int, int] = (900, 1600),
    image: Image.Image | None = None,
    accepted_screen: ScreenType | None = None,
    layout_id: str | None = None,
    semantic_parser: Callable[..., ObservationAdditions] | None = None,
    materialize_geometry: bool = True,
):
    """Build an OCR fixture, optionally after an explicit screen decision.

    The default path exercises production screen classification and is retained
    for negative/abstention cases. Positive synthetic semantic cases must pass
    ``accepted_screen``: OCR text is then consumed only by the canonical
    screen-specific enricher, with the caller-owned screen/layout decision
    carried into publication.
    """

    active_image = image.copy() if image is not None else _build_chat_fixture_image(image_size=image_size)
    payload = _encode_png(active_image)
    with tempfile.TemporaryDirectory() as temp_directory:
        screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=Path(temp_directory) / "artifacts"))
        screenshot = screenshot_service.capture(
            _FakeScreenshotSession(payload),
            artifact_directory="mail_test",
            label="synthetic",
        )
        ocr_service = _FakeOcrService(lines=lines)
        builder = ObservationBuilder(
            selector_registry=build_default_selector_registry(),
            selector_engine=ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),

            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(

                selector_registry=build_default_selector_registry(),
            ),
            ocr_service=ocr_service,
        )
        if accepted_screen is None:
            return builder.build(screenshot, request=request)
        return _build_accepted_observation(
            builder=builder,
            screenshot=screenshot,
            request=request,
            lines=lines,
            accepted_screen=accepted_screen,
            layout_id=layout_id,
            semantic_parser=semantic_parser,
            materialize_geometry=materialize_geometry,
        )


def _build_accepted_observation(
    *,
    builder: ObservationBuilder,
    screenshot: CapturedScreenshot,
    request: ObservationRequest,
    lines: tuple[OcrLine, ...],
    accepted_screen: ScreenType,
    layout_id: str | None = None,
    semantic_parser: Callable[..., ObservationAdditions] | None = None,
    materialize_geometry: bool = True,
    ocr_context: ObservationOcrContext | None = None,
):
    """Publish one existing screenshot after an explicit semantic screen decision."""

    active_ocr_context = ocr_context or builder.create_ocr_context(screenshot)
    if ocr_context is not None:
        active_ocr_context.validate_capture(screenshot.image, getattr(screenshot, "frame_ref", None))
    active_ocr_context.require_bounded_regions()
    visible_elements, _ = builder._complete_screen_scope(
        screenshot=screenshot,
        visible_elements={},
        screen_type=accepted_screen,
        evidence=(
            ScreenEvidence(
                accepted_screen,
                "explicit_test_input",
                layout_id=layout_id,
            ),
        ),
        ocr_context=active_ocr_context,
        materialize_geometry=materialize_geometry,
    )
    plans = compile_screen_content_ocr_region_plans(
        resolved_screen=accepted_screen,
        request=request,
        image_size=screenshot.image.size,
        layout_id=layout_id,
    )
    reads = execute_ocr_region_plans(
        image=screenshot.image,
        plans=plans,
        ocr_context=active_ocr_context,
    )
    ocr_regions = {
        read.plan.selector_id: read
        for read in reads
        if read.plan.selector_id is not None
    }
    additions = (
        semantic_parser(image=screenshot.image, lines=lines)
        if semantic_parser is not None
        else builder.enricher.enrich(
            screenshot.image,
            accepted_screen,
            visible_elements,
            request,
            ocr_context=active_ocr_context,
            ocr_regions=ocr_regions,
            layout_id=layout_id,
        )
    )
    if any(item.screen_type != accepted_screen for item in additions.screen_evidence):
        raise AssertionError("Semantic parser contradicted its explicit screen input.")
    visible_elements = {
        **visible_elements,
        **additions.visible_elements,
    }
    if additions.suppress_geometry_selector_ids:
        visible_elements = {
            selector_id: element
            for selector_id, element in visible_elements.items()
            if selector_id not in additions.suppress_geometry_selector_ids
        }
    decision = ScreenDecision(
        base_screen=accepted_screen,
        effective_screen=accepted_screen,
        layout_id=layout_id,
        guard=GuardVerdict.CLEAR,
        evidence=(
            ScreenEvidence(
                accepted_screen,
                "explicit_test_input",
                layout_id=layout_id,
            ),
        ),
    )
    return builder._publish(
        screenshot=screenshot,
        decision=decision,
        visible_elements=visible_elements,
        additions=additions,
        ocr_context=active_ocr_context,
    )
