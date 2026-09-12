"""Synthetic shared_rapid_ocr_service fixture."""

from __future__ import annotations

from functools import cache

from pnc_automation.core.vision.ocr.ocr_service import RapidOcrService



@cache
def _shared_rapid_ocr_service() -> RapidOcrService:
    """Returns one stateless RapidOCR engine shared by image-backed tests."""

    return RapidOcrService()
