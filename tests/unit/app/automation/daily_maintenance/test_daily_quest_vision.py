"""Offline tests for Daily Quest visual geometry and OCR semantics."""

from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestRowState
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.vision.daily_quest_rows import (
    detect_daily_row_bounds,
    parse_daily_quest_screen,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine

from tests.support.paths import TEST_DATA_ROOT


class DailyQuestVisionTests(unittest.TestCase):
    """Covers card detection, exact title parsing, and non-OCR click geometry."""

    def test_detects_rows_from_visual_cards(self) -> None:
        """Finds full row rectangles without using OCR line positions."""

        image = _daily_image()

        rows = detect_daily_row_bounds(image)

        self.assertEqual((Bounds(9, 372, 518, 99), Bounds(9, 487, 518, 98)), rows)

    def test_parses_exact_titles_progress_and_actions(self) -> None:
        """Maps known titles and preserves excluded rows through the canonical catalog."""

        result = parse_daily_quest_screen(
            image=_daily_image(),
            lines=_daily_lines(go_x=438),
        )

        self.assertEqual("daily", result.selected_tab)
        self.assertEqual(2, len(result.rows))
        self.assertTrue(all(row.kind == ListEntryKind.DAILY_QUEST for row in result.rows))
        self.assertEqual("hero_arena", result.rows[0].metadata["quest_id"])
        self.assertEqual(DailyQuestRowState.GO.value, result.rows[0].metadata["row_state"])
        self.assertEqual(0, result.rows[0].metadata["progress_current"])
        self.assertEqual(3, result.rows[0].metadata["progress_required"])
        self.assertEqual("upgrade_building", result.rows[1].metadata["quest_id"])
        self.assertEqual(DailyQuestRowState.CLAIM.value, result.rows[1].metadata["row_state"])

    def test_ocr_button_coordinates_never_change_action_point(self) -> None:
        """Proves OCR classifies Go while visual card geometry owns the tap point."""

        first = parse_daily_quest_screen(image=_daily_image(), lines=_daily_lines(go_x=390))
        second = parse_daily_quest_screen(image=_daily_image(), lines=_daily_lines(go_x=500))

        self.assertEqual(first.rows[0].action_point, second.rows[0].action_point)
        self.assertEqual("visual_geometry", first.rows[0].metadata["coordinate_provenance"])

    def test_unknown_title_is_preserved_without_guessing(self) -> None:
        """Keeps future or noisy Daily titles visible for reporting but unowned."""

        lines = list(_daily_lines(go_x=438))
        lines[4] = _line("Challenge in Hero Championship", 155, 410, 220, 20)

        result = parse_daily_quest_screen(image=_daily_image(), lines=tuple(lines))

        self.assertIsNone(result.rows[0].metadata["quest_id"])
        self.assertEqual("Challenge in Hero Championship", result.rows[0].title_text)

    def test_committed_daily_fixture_uses_blue_button_fallback_when_go_ocr_is_missing(self) -> None:
        """Classifies a visually clear blue Go button when its OCR line is absent."""

        result = parse_daily_quest_screen(
            image=_fixture_daily_image("quest_daily.png"),
            lines=_fixture_daily_lines(omit_last_go=True),
        )

        self.assertEqual(5, len(result.rows))
        self.assertEqual(
            [
                DailyQuestRowState.CLAIM.value,
                DailyQuestRowState.GO.value,
                DailyQuestRowState.GO.value,
                DailyQuestRowState.GO.value,
                DailyQuestRowState.GO.value,
            ],
            [row.metadata["row_state"] for row in result.rows],
        )

    def test_visual_fallback_rejects_absent_or_small_blue_decoration(self) -> None:
        """Does not turn a card background or isolated blue decoration into Go."""

        image = _daily_image()
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((430, 530, 450, 550), fill=(45, 110, 190))

        result = parse_daily_quest_screen(
            image=image,
            lines=_daily_lines_without_actions(),
        )

        self.assertEqual(
            [DailyQuestRowState.UNKNOWN_ACTION.value, DailyQuestRowState.UNKNOWN_ACTION.value],
            [row.metadata["row_state"] for row in result.rows],
        )

    def test_visual_fallback_rejects_non_blue_right_side_decoration(self) -> None:
        """Does not treat a broad warm-colored action-side decoration as a blue Go button."""

        image = _daily_image()
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((390, 390, 515, 452), fill=(172, 104, 38))

        result = parse_daily_quest_screen(
            image=image,
            lines=_daily_lines_without_actions(),
        )

        self.assertEqual(
            [DailyQuestRowState.UNKNOWN_ACTION.value, DailyQuestRowState.UNKNOWN_ACTION.value],
            [row.metadata["row_state"] for row in result.rows],
        )

    def test_exact_claim_ocr_precedes_blue_visual_fallback(self) -> None:
        """Keeps OCR semantic precedence when a Claim row also contains blue pixels."""

        result = parse_daily_quest_screen(
            image=_fixture_daily_image("quest_daily_sep09.png"),
            lines=_fixture_daily_lines(omit_last_go=True, first_action="Claim"),
        )

        self.assertEqual(DailyQuestRowState.CLAIM.value, result.rows[0].metadata["row_state"])


def _daily_image() -> Image.Image:
    """Builds a deterministic Quest screen with visually detectable row cards."""

    image = Image.new("RGB", (540, 960), (19, 28, 44))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 50, 179, 108), fill=(25, 42, 72))
    draw.rectangle((180, 50, 359, 108), fill=(140, 103, 50))
    draw.rectangle((360, 50, 539, 108), fill=(25, 42, 72))
    draw.rectangle((9, 372, 526, 470), fill=(38, 50, 77))
    draw.rectangle((9, 487, 526, 584), fill=(38, 50, 77))
    return image


def _daily_lines(*, go_x: int) -> tuple[OcrLine, ...]:
    """Returns Quest OCR with deliberately movable button coordinates."""

    return (
        _line("Quest", 110, 13, 83, 29),
        _line("Main Quest", 37, 73, 108, 22),
        _line("Daily Quest", 219, 75, 105, 19),
        _line("Alliance Activity", 416, 66, 70, 38),
        _line("Challenge 3x in Hero Arena", 155, 410, 220, 20),
        _line("Go", go_x, 430, 30, 20),
        _line("(0/3)", 154, 451, 50, 20),
        _line("Upgrade building 1x", 155, 520, 190, 20),
        _line("Claim", 438, 540, 60, 20),
        _line("(1/1)", 154, 565, 50, 20),
    )


def _daily_lines_without_actions() -> tuple[OcrLine, ...]:
    """Returns Quest chrome without action text for visual negative coverage."""

    return (
        _line("Quest", 110, 13, 83, 29),
        _line("Main Quest", 37, 73, 108, 22),
        _line("Daily Quest", 219, 75, 105, 19),
        _line("Alliance Activity", 416, 66, 70, 38),
    )


def _fixture_daily_image(name: str) -> Image.Image:
    """Loads one committed Daily fixture without using local artifact configuration."""

    path = TEST_DATA_ROOT / "screen_recognition" / name
    return Image.open(path).convert("RGB")


def _fixture_daily_lines(*, omit_last_go: bool, first_action: str = "Claim") -> tuple[OcrLine, ...]:
    """Builds deterministic fixture OCR while selectively omitting one Go token."""

    lines = [
        _line("Quest", 110, 13, 83, 29),
        _line("Main Quest", 37, 73, 108, 22),
        _line("Daily Quest", 219, 75, 105, 19),
        _line("Alliance Activity", 416, 66, 70, 38),
        _line(first_action, 438, 420, 60, 20),
        _line("Go", 438, 535, 30, 20),
        _line("Go", 438, 650, 30, 20),
        _line("Go", 438, 765, 30, 20),
    ]
    if not omit_last_go:
        lines.append(_line("Go", 438, 880, 30, 20))
    return tuple(lines)


def _line(text: str, x: int, y: int, width: int, height: int) -> OcrLine:
    """Builds one deterministic OCR line."""

    return OcrLine(text=text, bounds=Bounds(x=x, y=y, width=width, height=height), confidence=0.95)


if __name__ == "__main__":
    unittest.main()
