"""Vision and screenshot interpretation components."""

from pnc_automation.vision.observation_builder import (
    DefaultObservationEnricher,
    ObservationBuilder,
    ObservationService,
    PillowSelectorEngine,
)
from pnc_automation.vision.ocr_service import OcrLine, OcrService, RapidOcrService, UnavailableOcrService
from pnc_automation.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.vision.screen_classifier import ScreenClassifier
from pnc_automation.vision.selectors import SelectorRegistry, build_default_selector_registry
from pnc_automation.vision.text_anchors import DetectedTextAnchor, TextAnchorDetector, TextAnchorId, normalize_ocr_text
from pnc_automation.vision.template_matcher import PillowTemplateMatcher

__all__ = [
    "DetectedTextAnchor",
    "DefaultObservationEnricher",
    "ObservationBuilder",
    "ObservationService",
    "OcrLine",
    "OcrService",
    "PncObservationEnricher",
    "PillowSelectorEngine",
    "PillowTemplateMatcher",
    "RapidOcrService",
    "ScreenClassifier",
    "SelectorRegistry",
    "TextAnchorDetector",
    "TextAnchorId",
    "UnavailableOcrService",
    "build_default_selector_registry",
    "normalize_ocr_text",
]
