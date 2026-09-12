"""Synthetic FakeOcrService fixture."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.app.pnc.vision.selectors import Region



@dataclass(slots=True)
class _FakeOcrService:
    """Returns deterministic OCR lines for castle-selection parsing tests."""

    lines: tuple[OcrLine, ...]

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns pre-seeded OCR output with line and word-level data."""

        lines = self.read_lines(image, region)
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns pre-seeded OCR lines, optionally restricted to a region."""

        del image
        if region is None:
            return self.lines
        filtered: list[OcrLine] = []
        for line in self.lines:
            if line.bounds.x < region.x or line.bounds.y < region.y:
                continue
            if line.bounds.x + line.bounds.width > region.x + region.width:
                continue
            if line.bounds.y + line.bounds.height > region.y + region.height:
                continue
            filtered.append(line)
        return tuple(filtered)

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns newline-joined OCR text for the requested region."""

        return "\n".join(line.text for line in self.read_lines(image, region))
