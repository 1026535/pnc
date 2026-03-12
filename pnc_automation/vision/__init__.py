"""Vision and screenshot interpretation components."""

from pnc_automation.vision.observation_builder import (
    DefaultObservationEnricher,
    ObservationBuilder,
    ObservationService,
    PillowSelectorEngine,
)
from pnc_automation.vision.observation_request import ObservationRequest
from pnc_automation.vision.ocr_service import OcrLine, OcrResult, OcrService, OcrWord, RapidOcrService, UnavailableOcrService
from pnc_automation.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.vision.screen_classifier import ScreenClassifier, ScreenEvidence
from pnc_automation.vision.selector_discovery import (
    SelectorDiscoveryAnalyzer,
    SelectorDiscoveryDraft,
    SelectorDiscoveryProbe,
    SelectorDiscoveryReport,
    SelectorDiscoverySnapshot,
    load_artifact_paths,
    write_selector_discovery_report,
    write_selector_discovery_spec,
)
from pnc_automation.vision.selectors import SelectorRegistry, build_default_selector_registry
from pnc_automation.vision.text_anchors import DetectedTextAnchor, TextAnchorDetector, TextAnchorId, normalize_ocr_text
from pnc_automation.vision.template_matcher import PillowTemplateMatcher

__all__ = [
    "DetectedTextAnchor",
    "DefaultObservationEnricher",
    "ObservationBuilder",
    "ObservationRequest",
    "ObservationService",
    "OcrLine",
    "OcrResult",
    "OcrService",
    "OcrWord",
    "PncObservationEnricher",
    "PillowSelectorEngine",
    "PillowTemplateMatcher",
    "RapidOcrService",
    "ScreenClassifier",
    "ScreenEvidence",
    "SelectorDiscoveryAnalyzer",
    "SelectorDiscoveryDraft",
    "SelectorDiscoveryProbe",
    "SelectorDiscoveryReport",
    "SelectorDiscoverySnapshot",
    "SelectorRegistry",
    "TextAnchorDetector",
    "TextAnchorId",
    "UnavailableOcrService",
    "build_default_selector_registry",
    "load_artifact_paths",
    "normalize_ocr_text",
    "write_selector_discovery_report",
    "write_selector_discovery_spec",
]
