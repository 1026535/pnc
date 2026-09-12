"""Synthetic require_rapid_ocr_service fixture."""

from __future__ import annotations

import unittest

from pnc_automation.core.errors import ScreenClassificationError
from pnc_automation.core.vision.ocr.ocr_service import RapidOcrService

from tests.support.pnc.capture_vision.shared_rapid_ocr_service import _shared_rapid_ocr_service


def _require_rapid_ocr_service(test_case: unittest.TestCase) -> RapidOcrService:
    """Returns shared RapidOCR support or skips when the optional backend is unavailable."""

    try:
        return _shared_rapid_ocr_service()
    except ScreenClassificationError as error:
        test_case.skipTest(str(error))
        raise AssertionError("skipTest must stop the current test") from error
