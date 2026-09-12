"""Synthetic CoordinateBarFilteringOcrService fixture."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.app.pnc.vision.selectors import Region

from tests.support.pnc.capture_vision.ocr_line import _ocr_line


@dataclass(slots=True)
class _CoordinateBarFilteringOcrService:
    """Returns different OCR text for raw versus blue-text-filtered coordinate-bar crops."""

    raw_text: str
    filtered_text: str

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Builds one synthetic OCR result from the requested region text."""

        lines = self.read_lines(image, region)
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns one synthetic OCR line that reflects whether the crop was prefiltered."""

        if region is None:
            raise AssertionError("Coordinate-bar filtering OCR tests require an explicit region.")
        text = self.read_text(image, region)
        return (_ocr_line(text, x=region.x, y=region.y, width=max(1, region.width), height=max(1, region.height)),)

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns the filtered OCR text only when the image was reduced to a black-on-white mask."""

        crop = image.crop((region.x, region.y, region.x + region.width, region.y + region.height)).convert("L")
        colors = {value for count, value in (crop.getcolors(maxcolors=8) or []) if count > 0}
        if colors and colors.issubset({0, 255}):
            return self.filtered_text
        return self.raw_text
