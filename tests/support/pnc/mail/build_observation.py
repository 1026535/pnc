"""Synthetic build_observation fixture."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
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
):
    """Builds one synthetic OCR-backed observation using the default selector registry."""

    active_image = image.copy() if image is not None else _build_chat_fixture_image(image_size=image_size)
    payload = _encode_png(active_image)
    with tempfile.TemporaryDirectory() as temp_directory:
        screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=Path(temp_directory) / "artifacts"))
        screenshot = screenshot_service.capture(
            _FakeScreenshotSession(payload),
            artifact_directory="mail_test",
            label="synthetic",
        )
        builder = ObservationBuilder(
            selector_registry=build_default_selector_registry(),
            selector_engine=ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),
                ocr_service=UnavailableOcrService(),
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(
                ocr_service=_FakeOcrService(lines=lines),
                selector_registry=build_default_selector_registry(),
            ),
        )
        return builder.build(screenshot, request=request)
