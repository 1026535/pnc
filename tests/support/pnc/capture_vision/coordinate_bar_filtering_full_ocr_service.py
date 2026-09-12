"""Synthetic CoordinateBarFilteringFullOcrService fixture."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.app.pnc.vision.selectors import Region

from tests.support.pnc.capture_vision.coordinate_bar_filtering_ocr_service import (
    _CoordinateBarFilteringOcrService,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


@dataclass(slots=True)
class _CoordinateBarFilteringFullOcrService(_CoordinateBarFilteringOcrService):
    """Returns full-screen OCR lines while preserving selector-crop filtered coordinate text."""

    full_lines: tuple[OcrLine, ...] = ()

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns filtered coordinates for the context-owned transformed crop."""

        if region is None and image.mode == "L":
            line = _ocr_line(
                self.filtered_text,
                x=0,
                y=0,
                width=max(1, image.width),
                height=max(1, image.height),
            )
            return OcrResult(lines=(line,), words=tuple(line.words))
        if region is None:
            return OcrResult(lines=self.full_lines, words=tuple(word for line in self.full_lines for word in line.words))
        lines = self.read_lines(image, region)
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns full-screen lines or one synthetic region line for the requested coordinate crop."""

        if region is None:
            return self.full_lines
        return _CoordinateBarFilteringOcrService.read_lines(self, image, region)
