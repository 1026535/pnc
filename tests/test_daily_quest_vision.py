"""Offline tests for Daily Quest visual geometry and OCR semantics."""

from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestRowState
from pnc_automation.app.pnc.domain.observation import ListEntryKind, RowRecognitionStatus
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.daily_quest_rows import detect_daily_row_bounds, parse_daily_quest_screen
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


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
        self.assertTrue(all(row.row_status == RowRecognitionStatus.COMPLETE for row in result.rows))
        self.assertTrue(all(row.action_bounds is not None for row in result.rows))

    def test_ocr_button_coordinates_never_change_action_point(self) -> None:
        """Proves OCR classifies Go while visual card geometry owns the tap point."""

        first = parse_daily_quest_screen(image=_daily_image(), lines=_daily_lines(go_x=390))
        second = parse_daily_quest_screen(image=_daily_image(), lines=_daily_lines(go_x=470))

        self.assertEqual(first.rows[0].action_point, second.rows[0].action_point)
        self.assertEqual("visual_geometry", first.rows[0].metadata["coordinate_provenance"])

    def test_unknown_title_is_preserved_without_guessing(self) -> None:
        """Keeps future or noisy Daily titles visible for reporting but unowned."""

        lines = list(_daily_lines(go_x=438))
        lines[4] = _line("Challenge in Hero Championship", 155, 410, 220, 20)

        result = parse_daily_quest_screen(image=_daily_image(), lines=tuple(lines))

        self.assertIsNone(result.rows[0].metadata["quest_id"])
        self.assertEqual("Challenge in Hero Championship", result.rows[0].title_text)

    def test_multiple_valid_titles_in_one_card_are_ambiguous(self) -> None:
        lines = list(_daily_lines(go_x=438))
        lines.append(_line("Upgrade building 1x", 155, 435, 190, 20))

        result = parse_daily_quest_screen(image=_daily_image(), lines=tuple(lines))

        self.assertEqual(RowRecognitionStatus.AMBIGUOUS, result.rows[0].row_status)
        self.assertEqual("multiple_valid_titles", result.rows[0].metadata["unresolved_reason"])
        self.assertIsNone(result.rows[0].action_point)

    def test_saved_daily_fixture_uses_manual_ocr_labels_and_visual_action_boxes(self) -> None:
        """The reviewed 540x960 fixture yields five complete, independently bounded rows."""

        image = Image.open(
            Path(__file__).parent / "data" / "screen_recognition" / "quest_daily.png"
        ).convert("RGB")
        lines = _saved_daily_lines()

        result = parse_daily_quest_screen(image=image, lines=lines)

        self.assertIsNotNone(result)
        self.assertEqual(5, len(result.rows))
        self.assertTrue(all(row.row_status == RowRecognitionStatus.COMPLETE for row in result.rows))
        self.assertEqual(
            ((388, 398, 130, 43), (388, 512, 130, 44), (388, 627, 130, 44), (388, 741, 130, 44), (388, 856, 130, 44)),
            tuple((row.action_bounds.x, row.action_bounds.y, row.action_bounds.width, row.action_bounds.height) for row in result.rows),
        )

    def test_saved_900_daily_fixture_action_points_stay_inside_manual_boxes(self) -> None:
        image = Image.open(
            Path(__file__).parent / "data" / "screen_recognition" / "quest_daily_live_900.png"
        ).convert("RGB")
        rows = (
            (622, "Upgrade building 1x", (0, 1), (647, 663, 217, 73)),
            (813, "Challenge 3x in Hero Arena", (0, 3), (647, 854, 217, 73)),
            (1004, "Upgrade tech 1x", (0, 1), (647, 1045, 217, 73)),
            (1195, "Train Infantry x250", (0, 250), (647, 1236, 217, 73)),
            (1386, "Train Cavalry x250", (0, 250), (647, 1428, 217, 73)),
        )
        lines = []
        for y, title, progress, _ in rows:
            lines.extend(
                (
                    _line(title, 260, y + 35, 300, 30),
                    _line("Go", 690, y + 55, 80, 30),
                    _line(f"({progress[0]}/{progress[1]})", 250, y + 100, 80, 30),
                )
            )

        result = parse_daily_quest_screen(
            image=image,
            lines=tuple(lines),
            proved_screen=ScreenType.PNC_QUEST_DAILY,
        )

        self.assertEqual(5, len(result.rows))
        for (_, _, _, manual_action), row in zip(rows, result.rows, strict=True):
            self.assertEqual(RowRecognitionStatus.COMPLETE, row.row_status)
            self.assertTrue(_point_in_bounds(row.action_point, _bounds_from_tuple(manual_action)))

    def test_proved_main_never_emits_daily_rows_and_still_checks_tab_pixels(self) -> None:
        image = _daily_image(selected="main")

        result = parse_daily_quest_screen(
            image=image,
            lines=tuple(line for line in _daily_lines(go_x=438) if line.text not in {"Quest", "Main Quest", "Daily Quest", "Alliance Activity"}),
            proved_screen=ScreenType.PNC_QUEST_MAIN,
        )

        self.assertIsNotNone(result)
        self.assertEqual("main", result.selected_tab)
        self.assertEqual((), result.rows)

    def test_saved_main_fixture_never_infers_daily_rows(self) -> None:
        image = Image.open(
            Path(__file__).parent / "data" / "screen_recognition" / "quest_main.png"
        ).convert("RGB")

        result = parse_daily_quest_screen(
            image=image,
            lines=(),
            proved_screen=ScreenType.PNC_QUEST_MAIN,
        )

        self.assertIsNotNone(result)
        self.assertEqual("main", result.selected_tab)
        self.assertEqual((), result.rows)

    def test_proved_screen_requires_exact_enum(self) -> None:
        with self.assertRaises(TypeError):
            parse_daily_quest_screen(
                image=_daily_image(),
                lines=(),
                proved_screen="PNC_QUEST_DAILY",
            )

    def test_contradictory_claim_and_go_is_ambiguous(self) -> None:
        image = _daily_image()
        draw = ImageDraw.Draw(image)
        draw.rectangle((388, 420, 518, 450), fill=(45, 104, 170))
        draw.rectangle((388, 455, 518, 469), fill=(140, 103, 50))
        lines = list(_daily_lines(go_x=438))
        lines.extend((_line("Claim", 438, 455, 60, 12),))

        result = parse_daily_quest_screen(image=image, lines=tuple(lines))

        self.assertEqual(RowRecognitionStatus.AMBIGUOUS, result.rows[0].row_status)
        self.assertIsNone(result.rows[0].action_point)

    def test_go_and_claimed_inside_one_control_are_ambiguous(self) -> None:
        lines = list(_daily_lines(go_x=438))
        lines.append(_line("Claimed", 438, 430, 70, 20))

        result = parse_daily_quest_screen(image=_daily_image(), lines=tuple(lines))

        self.assertEqual(RowRecognitionStatus.AMBIGUOUS, result.rows[0].row_status)
        self.assertIsNone(result.rows[0].action_point)

    def test_claim_inside_control_and_go_elsewhere_are_ambiguous(self) -> None:
        image = _daily_image()
        ImageDraw.Draw(image).rectangle((388, 420, 518, 450), fill=(140, 103, 50))
        lines = list(_daily_lines(go_x=438))
        lines[5] = _line("Claim", 438, 430, 60, 20)
        lines.append(_line("Go", 438, 455, 40, 12))

        result = parse_daily_quest_screen(image=image, lines=tuple(lines))

        self.assertEqual(RowRecognitionStatus.AMBIGUOUS, result.rows[0].row_status)
        self.assertIsNone(result.rows[0].action_point)

    def test_claim_before_required_progress_is_ambiguous(self) -> None:
        image = _daily_image()
        ImageDraw.Draw(image).rectangle((388, 420, 518, 450), fill=(140, 103, 50))
        lines = list(_daily_lines(go_x=438))
        lines[4] = _line("Use resource item x1", 155, 410, 220, 20)
        lines[5] = _line("Claim", 438, 430, 60, 20)
        lines[6] = _line("(0/1)", 154, 451, 50, 20)

        result = parse_daily_quest_screen(image=image, lines=tuple(lines))

        self.assertEqual(RowRecognitionStatus.AMBIGUOUS, result.rows[0].row_status)
        self.assertEqual("claim_progress_incomplete", result.rows[0].metadata["unresolved_reason"])
        self.assertIsNone(result.rows[0].action_point)

    def test_malformed_progress_grouping_is_unreadable(self) -> None:
        lines = list(_daily_lines(go_x=438))
        lines[6] = _line("(1,2/3)", 154, 451, 70, 20)

        result = parse_daily_quest_screen(image=_daily_image(), lines=tuple(lines))

        self.assertEqual(RowRecognitionStatus.UNREADABLE, result.rows[0].row_status)
        self.assertIsNone(result.rows[0].action_point)

    def test_conflicting_progress_occurrences_are_unreadable(self) -> None:
        lines = list(_daily_lines(go_x=438))
        lines[6] = _line("(0/3) (1/3)", 154, 451, 120, 20)

        result = parse_daily_quest_screen(image=_daily_image(), lines=tuple(lines))

        self.assertEqual(RowRecognitionStatus.UNREADABLE, result.rows[0].row_status)
        self.assertIsNone(result.rows[0].action_point)

    def test_edge_clipped_daily_row_has_no_action(self) -> None:
        image = _daily_image()
        draw = ImageDraw.Draw(image)
        draw.rectangle((9, 900, 526, 959), fill=(38, 50, 77))
        draw.rectangle((388, 920, 518, 950), fill=(45, 104, 170))
        lines = list(_daily_lines(go_x=438))
        lines.extend(
            (
                _line("Challenge 3x in Hero Arena", 155, 915, 220, 20),
                _line("Go", 430, 925, 40, 15),
                _line("(0/3)", 155, 940, 50, 15),
            )
        )

        result = parse_daily_quest_screen(image=image, lines=tuple(lines))

        clipped = result.rows[-1]
        self.assertEqual(RowRecognitionStatus.CLIPPED, clipped.row_status)
        self.assertIsNone(clipped.action_point)

    def test_top_viewport_clipped_daily_row_has_no_action(self) -> None:
        image = _daily_image()
        draw = ImageDraw.Draw(image)
        draw.rectangle((9, 345, 526, 470), fill=(38, 50, 77))
        draw.rectangle((388, 360, 518, 390), fill=(45, 104, 170))
        lines = list(_daily_lines(go_x=438))
        lines.extend(
            (
                _line("Challenge 3x in Hero Arena", 155, 350, 220, 20),
                _line("Go", 430, 365, 40, 15),
                _line("(0/3)", 155, 410, 50, 15),
            )
        )

        result = parse_daily_quest_screen(image=image, lines=tuple(lines))

        clipped = result.rows[0]
        self.assertEqual(RowRecognitionStatus.CLIPPED, clipped.row_status)
        self.assertIsNone(clipped.action_point)


def _daily_image(*, selected: str = "daily") -> Image.Image:
    """Builds a deterministic Quest screen with visually detectable row cards."""

    image = Image.new("RGB", (540, 960), (19, 28, 44))
    draw = ImageDraw.Draw(image)
    fills = {
        "main": ((140, 103, 50), (25, 42, 72), (25, 42, 72)),
        "daily": ((25, 42, 72), (140, 103, 50), (25, 42, 72)),
        "alliance": ((25, 42, 72), (25, 42, 72), (140, 103, 50)),
    }[selected]
    draw.rectangle((0, 50, 179, 108), fill=fills[0])
    draw.rectangle((180, 50, 359, 108), fill=fills[1])
    draw.rectangle((360, 50, 539, 108), fill=fills[2])
    draw.rectangle((9, 372, 526, 470), fill=(38, 50, 77))
    draw.rectangle((9, 487, 526, 584), fill=(38, 50, 77))
    draw.rectangle((388, 420, 518, 450), fill=(45, 104, 170))
    draw.rectangle((388, 530, 518, 570), fill=(140, 103, 50))
    return image


def _saved_daily_lines() -> tuple[OcrLine, ...]:
    """Manual semantic labels paired with the independently reviewed fixture boxes."""

    lines = [
        _line("Quest", 10, 10, 80, 25),
        _line("Main Quest", 20, 70, 110, 20),
        _line("Daily Quest", 220, 70, 110, 20),
        _line("Alliance Activity", 420, 70, 100, 20),
    ]
    rows = (
        (373, "Use resource item x1", (1, 1), "Claim"),
        (488, "Upgrade building 1x", (0, 1), "Go"),
        (602, "Challenge 3x in Hero Arena", (0, 3), "Go"),
        (717, "Upgrade tech 1x", (0, 1), "Go"),
        (832, "Train Infantry x250", (0, 250), "Go"),
    )
    for y, title, progress, state in rows:
        lines.extend(
            (
                _line(title, 155, y + 15, 220, 20),
                _line(state, 430, y + 30, 60, 20),
                _line(f"({progress[0]}/{progress[1]})", 154, y + 55, 50, 20),
            )
        )
    return tuple(lines)


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

    path = Path(__file__).parent / "data" / "screen_recognition" / name
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


def _bounds_from_tuple(values: tuple[int, int, int, int]) -> Bounds:
    return Bounds(*values)


def _point_in_bounds(point: tuple[int, int], bounds: Bounds) -> bool:
    return bounds.x <= point[0] < bounds.x + bounds.width and bounds.y <= point[1] < bounds.y + bounds.height


if __name__ == "__main__":
    unittest.main()
