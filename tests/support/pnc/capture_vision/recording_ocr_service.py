"""Synthetic RecordingOcrService fixture."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from pnc_automation.core.vision.ocr.ocr_service import OcrResult
from pnc_automation.app.pnc.vision.selectors import Region

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService


@dataclass(slots=True)
class _RecordingOcrService(_FakeOcrService):
    """Counts OCR calls so staged-observation tests can assert cost control."""

    read_result_calls: int = 0
    read_text_calls: int = 0

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Records full-image OCR requests before returning deterministic lines."""

        self.read_result_calls += 1
        return _FakeOcrService.read_result(self, image, region)

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Records region OCR reads before returning deterministic text."""

        self.read_text_calls += 1
        return _FakeOcrService.read_text(self, image, region)
