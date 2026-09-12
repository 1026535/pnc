"""Synthetic CoordinateBarTopHudFallbackOcrService fixture."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.app.pnc.vision.selectors import Region



@dataclass(slots=True)
class _CoordinateBarTopHudFallbackOcrService:
    """Simulates a selector-crop coordinate miss with a successful bounded top-HUD OCR fallback."""

    top_hud_lines: tuple[OcrLine, ...]
    read_text_calls: int = 0
    read_lines_regions: list[Region | None] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns OCR lines for callers that request a full OCR result."""

        lines = self.read_lines(image, region)
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns top-HUD coordinate lines only outside the canonical selector crop."""

        del image
        self.read_lines_regions.append(region)
        if region is None or region.x != 0 or region.y != 0:
            return ()
        return tuple(
            line
            for line in self.top_hud_lines
            if line.bounds.x >= region.x
            and line.bounds.y >= region.y
            and line.bounds.x + line.bounds.width <= region.x + region.width
            and line.bounds.y + line.bounds.height <= region.y + region.height
        )

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns an empty filtered selector-crop read to force the top-HUD fallback."""

        del image, region
        self.read_text_calls += 1
        return ""
