"""Shared OCR-line composition helpers used across screen and spatial parsing."""

from __future__ import annotations

from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


def merge_ocr_lines(upper_line: OcrLine, lower_line: OcrLine) -> OcrLine:
    """Returns one synthetic OCR line that combines two vertically stacked OCR fragments."""

    separator = "" if upper_line.text.rstrip().endswith(("]", ")", "}")) else " "
    left = min(upper_line.bounds.x, lower_line.bounds.x)
    top = min(upper_line.bounds.y, lower_line.bounds.y)
    right = max(
        upper_line.bounds.x + upper_line.bounds.width,
        lower_line.bounds.x + lower_line.bounds.width,
    )
    bottom = max(
        upper_line.bounds.y + upper_line.bounds.height,
        lower_line.bounds.y + lower_line.bounds.height,
    )
    return OcrLine(
        text=f"{upper_line.text.rstrip()}{separator}{lower_line.text.lstrip()}".strip(),
        bounds=Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top)),
        confidence=min(upper_line.confidence, lower_line.confidence),
        words=upper_line.words + lower_line.words,
    )
