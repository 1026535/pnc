"""Synthetic ocr_line fixture."""

from __future__ import annotations

from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from pnc_automation.app.pnc.vision.selectors import Region



def _ocr_line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    """Builds one deterministic OCR line for synthetic mail screen tests."""

    return OcrLine(text=text, bounds=Region(x=x, y=y, width=width, height=height), confidence=0.99)
