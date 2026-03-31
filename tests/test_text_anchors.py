"""Shared OCR text-anchor detection tests."""

from __future__ import annotations

import unittest

from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult, OcrWord
from pnc_automation.app.pnc.vision.selectors import Region
from pnc_automation.app.pnc.vision.text_anchors import TextAnchorDetector, TextAnchorId


class TextAnchorTests(unittest.TestCase):
    """Validates normalization and detection of shared OCR text anchors."""

    def test_text_anchor_detector_normalizes_known_labels(self) -> None:
        """Maps punctuation and spacing variants onto the canonical anchor identifiers."""

        detector = TextAnchorDetector()

        anchors = detector.detect(
            OcrResult(
                lines=(
                    OcrLine(text="Manage Char.", bounds=Region(x=10, y=10, width=50, height=20), confidence=0.99),
                    OcrLine(text="Troop Skill", bounds=Region(x=20, y=30, width=60, height=20), confidence=0.99),
                    OcrLine(text="More!", bounds=Region(x=30, y=50, width=40, height=20), confidence=0.99),
                    OcrLine(text="Cancel", bounds=Region(x=40, y=70, width=70, height=20), confidence=0.99),
                    OcrLine(text="Join/Apply", bounds=Region(x=50, y=90, width=90, height=20), confidence=0.99),
                    OcrLine(text="Unmapped Text", bounds=Region(x=60, y=110, width=100, height=20), confidence=0.99),
                ),
                words=(),
            )
        )

        self.assertEqual(
            tuple(anchor.id for anchor in anchors),
            (
                TextAnchorId.LABEL_MANAGE_CHAR,
                TextAnchorId.LABEL_TROOP_SKILL,
                TextAnchorId.LABEL_MORE,
                TextAnchorId.LABEL_CANCEL,
                TextAnchorId.LABEL_JOIN_APPLY,
            ),
        )

    def test_text_anchor_detector_uses_word_spans_and_structured_matches(self) -> None:
        """Detects split-word phrases plus structured kingdom and castle-level anchors."""

        detector = TextAnchorDetector()
        line = OcrLine(
            text="???",
            bounds=Region(x=10, y=10, width=90, height=20),
            confidence=0.99,
            words=(
                OcrWord(text="Manage", bounds=Region(x=10, y=10, width=40, height=20), confidence=0.99),
                OcrWord(text="Char", bounds=Region(x=52, y=10, width=28, height=20), confidence=0.99),
            ),
        )

        anchors = detector.detect(
            OcrResult(
                lines=(
                    line,
                    OcrLine(text="K230 Kingdom", bounds=Region(x=20, y=40, width=100, height=20), confidence=0.99),
                    OcrLine(text="Castle Level 11", bounds=Region(x=20, y=70, width=110, height=20), confidence=0.99),
                ),
                words=line.words,
            )
        )

        anchor_ids = tuple(anchor.id for anchor in anchors)
        self.assertIn(TextAnchorId.LABEL_MANAGE_CHAR, anchor_ids)
        self.assertIn(TextAnchorId.KINGDOM, anchor_ids)
        self.assertIn(TextAnchorId.CASTLE_LEVEL, anchor_ids)
        kingdom_anchor = next(anchor for anchor in anchors if anchor.id == TextAnchorId.KINGDOM)
        castle_level_anchor = next(anchor for anchor in anchors if anchor.id == TextAnchorId.CASTLE_LEVEL)
        self.assertEqual(kingdom_anchor.metadata_value("kingdom"), "K230")
        self.assertEqual(castle_level_anchor.metadata_value("castle_level"), 11)

    def test_text_anchor_detector_accepts_merged_kingdom_labels_without_matching_castle_names(self) -> None:
        """Parses merged `K313Kingdom` OCR while rejecting castle-name rows that only start with a kingdom token."""

        detector = TextAnchorDetector()

        anchors = detector.detect(
            OcrResult(
                lines=(
                    OcrLine(text="K313Kingdom", bounds=Region(x=20, y=40, width=120, height=20), confidence=0.99),
                    OcrLine(text="ColdDukeOfTheNorth", bounds=Region(x=20, y=70, width=180, height=20), confidence=0.99),
                    OcrLine(text="K304554ca2797", bounds=Region(x=20, y=100, width=140, height=20), confidence=0.99),
                ),
                words=(),
            )
        )

        kingdom_anchors = tuple(anchor for anchor in anchors if anchor.id == TextAnchorId.KINGDOM)
        self.assertEqual(len(kingdom_anchors), 1)
        self.assertEqual(kingdom_anchors[0].metadata_value("kingdom"), "K313")


if __name__ == "__main__":
    unittest.main()
