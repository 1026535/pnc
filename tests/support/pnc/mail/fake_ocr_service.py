"""Synthetic FakeOcrService fixture."""

from __future__ import annotations

from PIL import Image

from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.app.pnc.vision.selectors import Region



class _FakeOcrService:
    """Returns deterministic OCR lines for synthetic mail screen parsing tests."""

    def __init__(self, *, lines: tuple[OcrLine, ...]) -> None:
        """Stores the OCR lines returned for every synthetic screenshot."""

        self._lines = lines

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns pre-seeded OCR output, optionally clipped to the requested region."""

        return OcrResult(lines=self.read_lines(image, region), words=())

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns the pre-seeded OCR lines, optionally restricted to one region."""

        del image
        if region is None:
            return self._lines
        filtered: list[OcrLine] = []
        for line in self._lines:
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
