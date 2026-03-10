"""OCR service helper tests."""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from PIL import Image

from pnc_automation.vision.ocr_service import CachedOcrService, OcrResult
from pnc_automation.vision.selectors import Region


@dataclass(slots=True)
class _CountingOcrService:
    """Counts delegated OCR reads for cache-behavior tests."""

    calls: int = 0

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns an empty OCR result while counting calls."""

        del image, region
        self.calls += 1
        return OcrResult(lines=(), words=())

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[object, ...]:
        """Returns cached lines through the canonical result path."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns cached text through the canonical result path."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


class CachedOcrServiceTests(unittest.TestCase):
    """Validates the lightweight OCR cache used by discovery and observation pipelines."""

    def test_read_result_reuses_consecutive_full_image_requests(self) -> None:
        """Caches the immediately repeated full-image OCR request for one screenshot object."""

        image = Image.new("RGB", (10, 10), (15, 28, 68))
        inner = _CountingOcrService()
        cached = CachedOcrService(inner)

        first = cached.read_result(image)
        second = cached.read_result(image)

        self.assertIs(first, second)
        self.assertEqual(inner.calls, 1)

    def test_read_result_distinguishes_different_regions(self) -> None:
        """Does not reuse cached OCR output when the requested region changes."""

        image = Image.new("RGB", (10, 10), (15, 28, 68))
        inner = _CountingOcrService()
        cached = CachedOcrService(inner)

        cached.read_result(image, Region(x=0, y=0, width=5, height=5))
        cached.read_result(image, Region(x=1, y=1, width=5, height=5))

        self.assertEqual(inner.calls, 2)


if __name__ == "__main__":
    unittest.main()
