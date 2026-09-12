"""Generic OCR contracts and helpers."""

from pnc_automation.core.vision.ocr.ocr_lines import merge_ocr_lines
from pnc_automation.core.vision.ocr.ocr_service import (
    OcrContextMetrics,
    OcrLine,
    OcrReadDiagnostic,
    OcrReadPurpose,
    OcrReadStatus,
    OcrResult,
    OcrService,
    OcrWord,
    ObservationOcrContext,
    RapidOcrService,
    UnavailableOcrService,
)

__all__ = [
    "OcrContextMetrics",
    "OcrLine",
    "OcrReadDiagnostic",
    "OcrReadPurpose",
    "OcrReadStatus",
    "OcrResult",
    "OcrService",
    "OcrWord",
    "ObservationOcrContext",
    "RapidOcrService",
    "UnavailableOcrService",
    "merge_ocr_lines",
]

