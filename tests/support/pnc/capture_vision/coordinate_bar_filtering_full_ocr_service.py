"""Synthetic CoordinateBarFilteringFullOcrService fixture."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from pnc_automation.app.pnc.vision.selectors import Region

from tests.support.pnc.capture_vision.coordinate_bar_filtering_ocr_service import (
    _CoordinateBarFilteringOcrService,
)


@dataclass(slots=True)
class _CoordinateBarFilteringFullOcrService(_CoordinateBarFilteringOcrService):
    """Returns full-screen OCR lines while preserving selector-crop filtered coordinate text."""

    full_lines: tuple[OcrLine, ...] = ()

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns full-screen lines or one synthetic region line for the requested coordinate crop."""

        if region is None:
            return self.full_lines
        return _CoordinateBarFilteringOcrService.read_lines(self, image, region)
