"""Tests for the test-only shared RapidOCR request cache."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    OcrLine,
    OcrResult,
    OcrTextOrientation,
)
from tests.support.pnc.capture_vision.shared_rapid_ocr_service import (
    _MemoizingOcrService,
)


class _CountingOcrService:
    def __init__(self) -> None:
        self.calls: list[tuple[Bounds | None, OcrTextOrientation]] = []
        self.result = OcrResult(
            lines=(OcrLine("fixture text", Bounds(1, 2, 5, 4), 0.9),),
            words=(),
        )

    def read_result(
        self,
        image: Image.Image,
        region: Bounds | None = None,
        *,
        orientation: OcrTextOrientation = OcrTextOrientation.AUTO,
    ) -> OcrResult:
        del image
        self.calls.append((region, orientation))
        return self.result

    def read_lines(
        self,
        image: Image.Image,
        region: Bounds | None = None,
        *,
        orientation: OcrTextOrientation = OcrTextOrientation.AUTO,
    ) -> tuple[OcrLine, ...]:
        return self.read_result(image, region, orientation=orientation).lines

    def read_text(
        self,
        image: Image.Image,
        region: Bounds,
        *,
        orientation: OcrTextOrientation = OcrTextOrientation.AUTO,
    ) -> str:
        return "\n".join(
            line.text
            for line in self.read_lines(image, region, orientation=orientation)
        )


class MemoizingOcrServiceTests(unittest.TestCase):
    def test_reuses_only_identical_pixels_region_and_orientation(self) -> None:
        backend = _CountingOcrService()
        service = _MemoizingOcrService(backend)
        image = Image.new("RGB", (20, 20), (10, 20, 30))
        region = Bounds(1, 2, 10, 8)

        first = service.read_result(image, region)
        self.assertIs(first, service.read_result(image.copy(), region))
        self.assertEqual((first.lines,), (service.read_lines(image.copy(), region),))
        self.assertEqual("fixture text", service.read_text(image.copy(), region))
        service.read_result(image, region, orientation=OcrTextOrientation.UPRIGHT)
        service.read_result(image, Bounds(2, 2, 10, 8))
        changed_image = image.copy()
        changed_image.putpixel((0, 0), (30, 20, 10))
        service.read_result(changed_image, region)

        self.assertEqual(4, len(backend.calls))
        self.assertEqual(3, service.cache_hits)

    def test_distinguishes_palettes_with_identical_pixel_indices(self) -> None:
        backend = _CountingOcrService()
        service = _MemoizingOcrService(backend)
        black = Image.new("P", (20, 20), 0)
        black.putpalette([0, 0, 0] + [0, 0, 0] * 255)
        white = Image.new("P", (20, 20), 0)
        white.putpalette([255, 255, 255] + [0, 0, 0] * 255)

        self.assertEqual(black.tobytes(), white.tobytes())
        self.assertNotEqual(
            black.convert("RGBA").tobytes(),
            white.convert("RGBA").tobytes(),
        )
        service.read_result(black)
        service.read_result(white)

        self.assertEqual(2, len(backend.calls))

    def test_evicts_oldest_result_at_the_configured_bound(self) -> None:
        backend = _CountingOcrService()
        service = _MemoizingOcrService(backend, max_cache_entries=1)
        first_image = Image.new("RGB", (20, 20), (1, 2, 3))
        second_image = Image.new("RGB", (20, 20), (4, 5, 6))

        service.read_result(first_image)
        service.read_result(second_image)
        service.read_result(first_image)

        self.assertEqual(3, len(backend.calls))
        self.assertEqual(1, len(service._results))


if __name__ == "__main__":
    unittest.main()
