"""Shared Campaign fixture, capture, and publisher wiring for visual tests."""

from __future__ import annotations
from datetime import UTC, datetime
from PIL import Image
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult, OcrService
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService

FIXTURES = TEST_DATA_ROOT / "screen_recognition"
CAMPAIGN_CHALLENGE_BOX = Bounds(178, 643, 184, 54)

def _image(name: str) -> Image.Image:
    with Image.open(FIXTURES / name) as source:
        return source.convert("RGB")

def _capture(image: Image.Image) -> CapturedScreenshot:
    """Wrap one fixture in the canonical capture model with explicit provenance."""

    frame = make_captured_frame(_encode_png(image), session_id="campaign-visual-test")
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )

def _builder(ocr_lines: tuple[OcrLine, ...] = ()) -> ObservationBuilder:
    """Wire the production observation builder to deterministic OCR."""

    return _builder_with_backend(_RecordingOcrService(lines=ocr_lines))


def _builder_with_backend(ocr_service: OcrService) -> ObservationBuilder:
    """Wire the production builder to one OCR backend."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry, template_matcher=matcher),
        ocr_service=ocr_service,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )

def _navigation_perception(ocr_lines: tuple[OcrLine, ...] = ()) -> NavigationPerception:
    """Wire NavigationPerception to the same registry and controlled OCR."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    ocr = _FakeOcrService(lines=ocr_lines)
    return NavigationPerception(
        load_visual_screen_recognizer(matcher=matcher),
        PncObservationEnricher(selector_registry=registry, template_matcher=matcher),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "campaign-visual-test",
        ),
    )

class _CampaignCropOcrService:
    """Honors requested regions while retaining every backend crop for assertions."""

    def __init__(self, lines: tuple[OcrLine, ...]) -> None:
        """Initialize one fixture-backed OCR response set."""

        self.lines = lines
        self.regions: list[Bounds | None] = []

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Return only lines wholly contained by the requested native region."""

        self.regions.append(region)
        if region is None:
            return OcrResult(lines=self.lines, words=())
        lines = tuple(line for line in self.lines if region.contains_bounds(line.bounds))
        return OcrResult(lines=lines, words=())

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Return crop-filtered lines through the backend protocol."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Return newline-joined crop-filtered text through the backend protocol."""

        return "\n".join(line.text for line in self.read_lines(image, region))

def _navigation_perception_with_backend(ocr_service: _CampaignCropOcrService) -> NavigationPerception:
    """Wire replacement perception to one crop-aware OCR backend."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return NavigationPerception(
        load_visual_screen_recognizer(matcher=matcher),
        PncObservationEnricher(selector_registry=registry, template_matcher=matcher),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr_service,
            capture.frame_ref,
            "campaign-visual-test",
        ),
    )
__all__ = [
    "CAMPAIGN_CHALLENGE_BOX", "FIXTURES", "_CampaignCropOcrService",
    "_builder", "_builder_with_backend", "_capture", "_image",
    "_navigation_perception", "_navigation_perception_with_backend",
]
