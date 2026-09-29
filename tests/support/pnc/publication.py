"""Construct fresh production publishers over caller-owned test dependencies."""

from __future__ import annotations

from pnc_automation.app.pnc.vision.navigation_perception import (
    NavigationGuard,
    NavigationPerception,
)
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import (
    load_visual_screen_recognizer,
)
from pnc_automation.core.vision.ocr.ocr_service import OcrService
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher


def make_publication_pair(
    *,
    selector_registry: SelectorRegistry,
    matcher: OpenCvTemplateMatcher,
    enricher: NavigationGuard,
    ocr_service: OcrService,
    ocr_backend_revision: str | None = None,
) -> tuple[ObservationBuilder, NavigationPerception]:
    """Share supplied dependencies while retaining fresh frame-scoped publishers."""

    builder = ObservationBuilder(
        selector_registry=selector_registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        ocr_service=ocr_service,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )
    if ocr_backend_revision is not None:
        builder.ocr_backend_revision = ocr_backend_revision
    navigation = NavigationPerception(
        builder.visual_recognizer,
        enricher,
        builder.screen_classifier,
        builder.create_ocr_context,
    )
    return builder, navigation
