"""Canonical build-queue parser qualifications for active and idle rows."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.pnc_observation_enricher import _build_build_queue_additions
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


VIEWPORT = (900, 1600)
QUEUE_ROWS = (Bounds(36, 512, 828, 160), Bounds(36, 672, 828, 160))


def _line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    """Create one localized OCR line in the canonical queue coordinates."""

    return OcrLine(text=text, bounds=Bounds(x, y, width, height), confidence=1.0)


def _queue_lines(*, active: bool) -> tuple[OcrLine, ...]:
    """Return OCR output already partitioned by the queue region compiler."""

    lines = [
        _line("Build Queue", x=330, y=432, width=248, height=57),
        _line("2nd Build Queue", x=212, y=703, width=225, height=30),
        _line("Inactive", x=211, y=758, width=110, height=30),
        _line("Activate", x=662, y=734, width=125, height=31),
    ]
    if active:
        lines.extend(
            (
                _line("Upgrading: Wall", x=210, y=543, width=302, height=40),
                _line("00:48:16", x=327, y=593, width=120, height=35),
                _line("Speedup", x=618, y=558, width=215, height=66),
            )
        )
    else:
        lines.extend(
            (
                _line("1st Build Queue", x=212, y=543, width=216, height=32),
                _line("Idle", x=209, y=596, width=57, height=33),
            )
        )
    return tuple(lines)


class BuildQueueParserTests(unittest.TestCase):
    """Prove only the canonical queue-row parser after screen ownership."""

    def test_parser_extracts_active_row_title_timer_and_state(self) -> None:
        """An active row keeps its title, timer, queue state, and owned bounds."""

        additions = _build_build_queue_additions(
            image=Image.new("RGB", VIEWPORT),
            lines=_queue_lines(active=True),
            proved_screen=ScreenType.PNC_BUILD_QUEUE,
            row_regions=QUEUE_ROWS,
        )

        self.assertIsNotNone(additions)
        assert additions is not None
        self.assertEqual(additions.screen_evidence, ())
        self.assertEqual(len(additions.list_entries), 1)
        entry = additions.list_entries[0]
        self.assertEqual(entry.kind, ListEntryKind.BUILDING)
        self.assertEqual(entry.title_text, "Wall")
        self.assertEqual(entry.timer_text, "00:48:16")
        self.assertEqual(entry.bounds, QUEUE_ROWS[0])
        self.assertEqual(entry.metadata, {"queue_state": "upgrading"})

    def test_parser_omits_idle_first_row_and_keeps_inactive_second_row_empty(self) -> None:
        """Idle and inactive rows cannot be published as active construction."""

        additions = _build_build_queue_additions(
            image=Image.new("RGB", VIEWPORT),
            lines=_queue_lines(active=False),
            proved_screen=ScreenType.PNC_BUILD_QUEUE,
            row_regions=QUEUE_ROWS,
        )

        self.assertIsNotNone(additions)
        assert additions is not None
        self.assertEqual(additions.list_entries, ())
        self.assertEqual(additions.screen_evidence, ())


if __name__ == "__main__":
    unittest.main()
