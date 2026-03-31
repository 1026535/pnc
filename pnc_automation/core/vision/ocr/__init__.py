"""Generic OCR contracts and helpers."""

from pnc_automation.core.vision.ocr.ocr_lines import merge_ocr_lines
from pnc_automation.core.vision.ocr.ocr_service import (
    CachedOcrService,
    OcrLine,
    OcrResult,
    OcrService,
    OcrWord,
    RapidOcrService,
    UnavailableOcrService,
)

__all__ = [
    "CachedOcrService",
    "OcrLine",
    "OcrResult",
    "OcrService",
    "OcrWord",
    "RapidOcrService",
    "UnavailableOcrService",
    "merge_ocr_lines",
]

