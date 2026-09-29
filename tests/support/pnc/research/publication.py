"""Shared fixture capture and dual-publication wiring for Research tests."""

from __future__ import annotations

from datetime import UTC, datetime

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.shared_rapid_ocr_service import _shared_rapid_ocr_service
from tests.support.pnc.publication import make_publication_pair

FIXTURES = TEST_DATA_ROOT / "screen_recognition"


def image(name: str, *, subdir: str = "") -> Image.Image:
    """Load one tracked, sanitized fixture into an independent RGB image."""

    root = FIXTURES / subdir if subdir else FIXTURES
    with Image.open(root / name) as source:
        return source.convert("RGB")


def capture(image: Image.Image, *, session_id: str) -> CapturedScreenshot:
    """Attach canonical frame provenance to one fixture capture."""

    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def production_components() -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire both production publication paths to the shared RapidOCR backend."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    enricher = PncObservationEnricher(selector_registry=registry)
    return make_publication_pair(
        selector_registry=registry,
        matcher=matcher,
        enricher=enricher,
        ocr_service=_shared_rapid_ocr_service(),
        ocr_backend_revision="research-acceptance",
    )


def observe(
    builder: ObservationBuilder,
    perception: NavigationPerception,
    image: Image.Image,
    *,
    session_id: str,
) -> tuple[Observation, Observation]:
    """Publish one fixture capture through both production paths."""

    return (
        builder.build(
            capture(image, session_id=f"builder:{session_id}"),
            request=ObservationRequest.full_runtime_default(),
        ),
        perception.build(
            capture(image, session_id=f"perception:{session_id}"),
            include_content=True,
        ),
    )
