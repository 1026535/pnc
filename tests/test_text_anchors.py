"""Shared OCR text-anchor detection tests."""

from __future__ import annotations

import unittest

from pnc_automation.vision.ocr_service import OcrLine
from pnc_automation.vision.selectors import Region
from pnc_automation.vision.text_anchors import TextAnchorDetector, TextAnchorId


class TextAnchorTests(unittest.TestCase):
    """Validates normalization and detection of shared OCR text anchors."""

    def test_text_anchor_detector_normalizes_known_labels(self) -> None:
        """Maps punctuation and spacing variants onto the canonical anchor identifiers."""

        detector = TextAnchorDetector()

        anchors = detector.detect(
            (
                OcrLine(text="Manage Char.", bounds=Region(x=10, y=10, width=50, height=20), confidence=0.99),
                OcrLine(text="Troop Skill", bounds=Region(x=20, y=30, width=60, height=20), confidence=0.99),
                OcrLine(text="More!", bounds=Region(x=30, y=50, width=40, height=20), confidence=0.99),
                OcrLine(text="Unmapped Text", bounds=Region(x=40, y=70, width=70, height=20), confidence=0.99),
            )
        )

        self.assertEqual(
            tuple(anchor.id for anchor in anchors),
            (
                TextAnchorId.LABEL_MANAGE_CHAR,
                TextAnchorId.LABEL_TROOP_SKILL,
                TextAnchorId.LABEL_MORE,
            ),
        )


if __name__ == "__main__":
    unittest.main()
