"""Deterministic Bag resource-row tests with no OCR-derived tap geometry."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import ListEntryKind, RowRecognitionStatus
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.resource_inventory import parse_resource_inventory, resource_inventory_tab_is_selected
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


class ResourceInventoryVisionTests(unittest.TestCase):
    """Rejects shop/bulk buttons and resolves only visually anchored resource packs."""

    def test_selected_tab_predicate_accepts_rgba_captures(self) -> None:
        for mode in ("RGB", "RGBA"):
            with self.subTest(mode=mode):
                self.assertTrue(resource_inventory_tab_is_selected(_image().convert(mode)))

    def test_known_non_pack_rows_are_visible_but_never_actionable(self) -> None:
        """Keeps Soulstones and boosts in scan geometry without permitting their use."""

        for title in (
            "500 Soulstones", "500Soulstones", "10kSoulstones",
            "24-hr Farm Output Boost", "24-hrFarmOutputBoost", "24-hr Lumber Output Boost",
            "24-hr Iron Mine Output Boost", "24-hr Gold Mine Output Boost",
        ):
            with self.subTest(title=title):
                lines = tuple(replace(line, text=title) if line.text == "1K Food" else line for line in _lines())
                rows = parse_resource_inventory(image=_image(), lines=lines)
                self.assertEqual(1, len(rows))
                self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION, rows[0].kind)
                self.assertIsNone(rows[0].action_point)

    def test_unknown_inventory_title_still_fails_closed(self) -> None:
        """Does not allow arbitrary text to bypass full-scan completeness checks."""

        lines = tuple(replace(line, text="Mystery pack") if line.text == "1K Food" else line for line in _lines())
        rows = parse_resource_inventory(image=_image(), lines=lines)
        self.assertEqual(1, len(rows))
        self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
        self.assertEqual(RowRecognitionStatus.UNREADABLE, rows[0].row_status)

    def test_invalid_pack_amount_is_explicitly_unresolved(self) -> None:
        lines = tuple(
            replace(line, text="0K Food") if line.text == "1K Food" else line
            for line in _lines()
        )

        rows = parse_resource_inventory(image=_image(), lines=lines)

        self.assertEqual(1, len(rows))
        self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
        self.assertEqual(RowRecognitionStatus.UNREADABLE, rows[0].row_status)
        self.assertEqual("invalid_pack_amount", rows[0].metadata["unresolved_reason"])

    def test_malformed_pack_separators_are_unresolved(self) -> None:
        for title in ("1.2.3K Food", "1,,2K Food"):
            with self.subTest(title=title):
                lines = tuple(
                    replace(line, text=title) if line.text == "1K Food" else line
                    for line in _lines()
                )

                rows = parse_resource_inventory(image=_image(), lines=lines)

                self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
                self.assertEqual(RowRecognitionStatus.UNREADABLE, rows[0].row_status)

    def test_decimal_pack_amount_uses_exact_arithmetic(self) -> None:
        lines = tuple(
            replace(line, text="1.5K Food") if line.text == "1K Food" else line
            for line in _lines()
        )

        rows = parse_resource_inventory(image=_image(), lines=lines)

        self.assertEqual(1_500, rows[0].metadata["amount"])

    def test_malformed_owned_grouping_is_unresolved(self) -> None:
        for owned in ("1,2", "1,,2"):
            with self.subTest(owned=owned):
                lines = tuple(
                    replace(line, text=f"Owned: {owned}") if line.text.startswith("Owned")
                    else line
                    for line in _lines()
                )

                rows = parse_resource_inventory(image=_image(), lines=lines)

                self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
                self.assertEqual(RowRecognitionStatus.UNREADABLE, rows[0].row_status)

    def test_valid_count_does_not_hide_a_second_malformed_owned_label(self) -> None:
        source = next(line for line in _lines() if line.text.startswith("Owned"))
        rows = parse_resource_inventory(
            image=_image(),
            lines=(*_lines(), replace(source, text="Owned: 1,,2")),
        )
        self.assertEqual(RowRecognitionStatus.UNREADABLE, rows[0].row_status)
        self.assertIsNone(rows[0].action_point)

    def test_parses_amount_and_owned_count(self) -> None:
        """Converts K suffixes and commas without confusing per-pack amount and stock."""

        rows = parse_resource_inventory(image=_image(), lines=_lines())
        self.assertEqual(1, len(rows))
        self.assertEqual(1000, rows[0].metadata["amount"])
        self.assertEqual(35174, rows[0].metadata["owned"])
        self.assertEqual("food", rows[0].metadata["resource"])
        self.assertEqual("visual_geometry", rows[0].metadata["coordinate_provenance"])

    def test_recovers_known_zero_for_o_resource_title_ocr(self) -> None:
        """Accepts the live `Fo0d` OCR variant without relaxing the pack grammar."""

        lines = tuple(replace(line, text="150KFo0d") if line.text == "1K Food" else line for line in _lines())
        rows = parse_resource_inventory(image=_image(), lines=lines)
        self.assertEqual(1, len(rows))
        self.assertEqual(150_000, rows[0].metadata["amount"])

    def test_recovers_known_zero_for_wood_resource_title_ocr(self) -> None:
        """Accepts the live `Wo0d` OCR variant while retaining the wood identity."""

        lines = tuple(replace(line, text="150KWo0d") if line.text == "1K Food" else line for line in _lines())
        rows = parse_resource_inventory(image=_image(), lines=lines)
        self.assertEqual(1, len(rows))
        self.assertEqual("wood", rows[0].metadata["resource"])

    def test_recovers_normalized_safe_suffix_for_wood_resource_title_ocr(self) -> None:
        """Keeps the safe-pack variant typed when OCR drops its parentheses."""

        lines = tuple(
            replace(line, text="150KWo0d (Safe)") if line.text == "1K Food" else line
            for line in _lines()
        )
        rows = parse_resource_inventory(image=_image(), lines=lines)
        self.assertEqual(1, len(rows))
        self.assertEqual("safe", rows[0].metadata["item_id"].split(":")[-1])

    def test_recovers_live_lowercase_i_ocr_for_iron_resource_title(self) -> None:
        """Accepts the live `lron` OCR variant without broadening the resource grammar."""

        lines = tuple(replace(line, text="200 lron") if line.text == "1K Food" else line for line in _lines())
        rows = parse_resource_inventory(image=_image(), lines=lines)
        self.assertEqual(1, len(rows))
        self.assertEqual("iron", rows[0].metadata["resource"])
        self.assertEqual(200, rows[0].metadata["amount"])

    def test_moving_ocr_use_text_does_not_move_click(self) -> None:
        """The blue button's pixels own the click, not text coordinates."""

        a = parse_resource_inventory(image=_image(), lines=_lines(use_y=200))
        b = parse_resource_inventory(image=_image(), lines=_lines(use_y=247))
        self.assertEqual(a[0].action_point, b[0].action_point)
        self.assertLess(a[0].action_point[1], 230)

    def test_orange_bulk_only_row_has_no_single_use_target(self) -> None:
        """Never substitutes the adjacent orange bulk action for missing blue Use."""

        image = _image()
        ImageDraw.Draw(image).rectangle((390, 190, 518, 222), fill=(175, 131, 49))
        rows = parse_resource_inventory(image=image, lines=_lines())
        self.assertEqual(1, len(rows))
        self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
        self.assertIsNone(rows[0].action_point)

    def test_contradictory_action_label_inside_blue_button_is_unresolved(self) -> None:
        for label in ("Bulk Use", "Buy", "Gray"):
            with self.subTest(label=label):
                lines = _lines() + (_line(label, 430, 200, 80, 20),)

                rows = parse_resource_inventory(image=_image(), lines=lines)

                self.assertEqual(1, len(rows))
                self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
                self.assertEqual("missing_or_ambiguous_single_use_button", rows[0].metadata["unresolved_reason"])
                self.assertIsNone(rows[0].action_point)

    def test_missing_owned_count_does_not_guess_inventory(self) -> None:
        """Leaves an unparsed row non-actionable instead of inferring a stock count."""

        lines = tuple(line for line in _lines() if not line.text.startswith("Owned"))
        rows = parse_resource_inventory(image=_image(), lines=lines)
        self.assertEqual(1, len(rows))
        self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
        self.assertEqual(RowRecognitionStatus.UNREADABLE, rows[0].row_status)

    def test_diamond_shop_tab_cannot_be_resource_inventory(self) -> None:
        """Requires the actual Bag and Resource tabs to be selected visually."""

        image = _image()
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 65, 269, 110), fill=(25, 42, 72))
        draw.rectangle((270, 65, 539, 110), fill=(140, 103, 50))
        self.assertIsNone(parse_resource_inventory(image=image, lines=_lines()))

    def test_saved_bag_fixture_preserves_six_cards_and_actual_button_y(self) -> None:
        """The saved six-card Bag fixture keeps each blue Use control's visual Y."""

        image = Image.open(
            Path(__file__).parent / "data" / "screen_recognition" / "bag.png"
        ).convert("RGB")
        lines = _saved_bag_lines()

        rows = parse_resource_inventory(
            image=image,
            lines=lines,
            proved_screen=ScreenType.PNC_BAG,
        )

        self.assertEqual(6, len(rows))
        self.assertTrue(all(row.row_status == RowRecognitionStatus.COMPLETE for row in rows))
        self.assertEqual([208, 339, 471, 602, 734, 891], [row.action_point[1] for row in rows])
        self.assertNotEqual(rows[-1].action_point[1], rows[-1].bounds.y + rows[-1].bounds.height // 2)

    def test_saved_900_bag_fixture_action_points_stay_inside_manual_boxes(self) -> None:
        image = Image.open(
            Path(__file__).parent / "data" / "screen_recognition" / "bag_current_testing.png"
        ).convert("RGB")
        lines = _saved_900_bag_lines()
        manual_cards = (
            Bounds(10, 287, 880, 201),
            Bounds(10, 506, 880, 201),
            Bounds(10, 725, 880, 201),
            Bounds(10, 945, 880, 200),
            Bounds(10, 1164, 880, 201),
            Bounds(10, 1383, 880, 200),
        )
        manual_use = (
            Bounds(649, 314, 214, 65),
            Bounds(649, 534, 214, 65),
            Bounds(649, 752, 214, 65),
            Bounds(649, 1014, 214, 65),
            Bounds(649, 1190, 214, 65),
            Bounds(649, 1409, 214, 65),
        )

        rows = parse_resource_inventory(
            image=image,
            lines=lines,
            proved_screen=ScreenType.PNC_BAG,
        )

        self.assertEqual(6, len(rows))
        for row, card, use in zip(rows, manual_cards, manual_use, strict=True):
            self.assertEqual(RowRecognitionStatus.COMPLETE, row.row_status)
            self.assertTrue(_point_in_bounds(row.action_point, card))
            self.assertTrue(_point_in_bounds(row.action_point, use))

    def test_duplicate_item_id_marks_both_rows_ambiguous(self) -> None:
        image = _image()
        draw = ImageDraw.Draw(image)
        draw.rectangle((6, 303, 532, 422), fill=(38, 50, 77))
        draw.rectangle((390, 321, 518, 353), fill=(45, 104, 170))
        draw.rectangle((390, 370, 518, 404), fill=(175, 131, 49))
        lines = _lines() + (
            _line("1K Food", 123, 324, 170, 22),
            _line("Owned: 72", 20, 404, 115, 15),
        )

        rows = parse_resource_inventory(image=image, lines=lines)

        self.assertEqual(2, sum(row.row_status == RowRecognitionStatus.AMBIGUOUS for row in rows))
        self.assertTrue(all(row.action_point is None for row in rows if row.row_status == RowRecognitionStatus.AMBIGUOUS))

    def test_empty_proved_bag_is_explicitly_unreadable(self) -> None:
        image = Image.new("RGB", (540, 960), (19, 28, 44))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 65, 269, 110), fill=(140, 103, 50))
        draw.rectangle((0, 124, 106, 160), fill=(140, 103, 50))

        rows = parse_resource_inventory(image=image, lines=(), proved_screen=ScreenType.PNC_BAG)

        self.assertEqual(1, len(rows))
        self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
        self.assertEqual(RowRecognitionStatus.UNREADABLE, rows[0].row_status)

    def test_proved_screen_requires_exact_enum(self) -> None:
        with self.assertRaises(TypeError):
            parse_resource_inventory(
                image=_image(),
                lines=(),
                proved_screen="PNC_BAG",
            )

    def test_edge_clipped_resource_card_is_explicitly_non_actionable(self) -> None:
        image = Image.new("RGB", (540, 960), (19, 28, 44))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 65, 269, 110), fill=(140, 103, 50))
        draw.rectangle((0, 124, 106, 160), fill=(140, 103, 50))
        draw.rectangle((6, 840, 532, 959), fill=(38, 50, 77))
        draw.rectangle((390, 860, 518, 892), fill=(45, 104, 170))

        rows = parse_resource_inventory(
            image=image,
            lines=(),
            proved_screen=ScreenType.PNC_BAG,
        )

        self.assertEqual(1, len(rows))
        self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
        self.assertEqual(RowRecognitionStatus.CLIPPED, rows[0].row_status)
        self.assertIsNone(rows[0].action_point)
        self.assertEqual("clipped_card", rows[0].metadata["unresolved_reason"])

    def test_top_viewport_clipped_resource_card_is_explicitly_non_actionable(self) -> None:
        image = _image()
        draw = ImageDraw.Draw(image)
        draw.rectangle((6, 163, 532, 291), fill=(38, 50, 77))
        draw.rectangle((390, 185, 518, 217), fill=(45, 104, 170))
        lines = (
            _line("Bag", 105, 14, 80, 25),
            _line("Resource", 12, 132, 85, 20),
            _line("1K Food", 123, 190, 170, 22),
            _line("Owned: 35,174", 20, 260, 115, 15),
        )

        rows = parse_resource_inventory(image=image, lines=lines)

        self.assertEqual(1, len(rows))
        self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, rows[0].kind)
        self.assertEqual(RowRecognitionStatus.CLIPPED, rows[0].row_status)
        self.assertIsNone(rows[0].action_point)
        self.assertEqual("clipped_card", rows[0].metadata["unresolved_reason"])


def _image() -> Image.Image:
    """Builds a synthetic version of the inspected resource Bag layout."""

    image = Image.new("RGB", (540, 960), (19, 28, 44))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 65, 269, 110), fill=(140, 103, 50))
    draw.rectangle((0, 124, 106, 160), fill=(140, 103, 50))
    draw.rectangle((6, 172, 532, 291), fill=(38, 50, 77))
    draw.rectangle((390, 190, 518, 222), fill=(45, 104, 170))
    draw.rectangle((390, 239, 518, 273), fill=(175, 131, 49))
    return image


def _lines(*, use_y: int = 200) -> tuple[OcrLine, ...]:
    """Provides semantics with deliberately movable Use text."""

    return (
        _line("Bag", 105, 14, 80, 25),
        _line("Resource", 12, 132, 85, 20),
        _line("1K Food", 123, 193, 170, 22),
        _line("Owned: 35,174", 20, 273, 115, 15),
        _line("Use", 440, use_y, 40, 20),
        _line("Use in bulk", 402, 246, 90, 20),
    )


def _saved_bag_lines() -> tuple[OcrLine, ...]:
    """Manual semantic labels for the saved six-card fixture."""

    lines = []
    cards = (
        (172, "1K Food", 2_011),
        (303, "10K Food", 72),
        (435, "10K Food (Safe)", 29),
        (566, "150K Food", 1),
        (698, "1K Wood", 1_963),
        (829, "10K Wood", 66),
    )
    for y, title, owned in cards:
        lines.extend(
            (
                _line(title, 120, y + 20, 180, 20),
                _line(f"Owned: {owned:,}", 20, y + 90, 120, 20),
            )
        )
    return tuple(lines)


def _saved_900_bag_lines() -> tuple[OcrLine, ...]:
    """Manual semantic labels for the independently reviewed 900x1600 fixture."""

    lines = []
    cards = (
        (287, "1K Food", 2_011),
        (506, "10K Food", 72),
        (725, "10K Food (Safe)", 29),
        (945, "150K Food", 1),
        (1164, "1K Wood", 1_963),
        (1383, "10K Wood", 66),
    )
    for y, title, owned in cards:
        lines.extend(
            (
                _line(title, 180, y + 35, 250, 30),
                _line(f"Owned: {owned:,}", 40, y + 120, 180, 30),
            )
        )
    return tuple(lines)


def _point_in_bounds(point: tuple[int, int], bounds: Bounds) -> bool:
    return bounds.x <= point[0] < bounds.x + bounds.width and bounds.y <= point[1] < bounds.y + bounds.height


def _line(text: str, x: int, y: int, width: int, height: int) -> OcrLine:
    """Builds one exact OCR fixture line."""

    return OcrLine(text, Bounds(x, y, width, height), 0.95)
