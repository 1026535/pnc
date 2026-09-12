"""Deterministic Bag resource-row tests with no OCR-derived tap geometry."""

from __future__ import annotations

import unittest
from dataclasses import replace

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.vision.resource_inventory import parse_resource_inventory
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


class ResourceInventoryVisionTests(unittest.TestCase):
    """Rejects shop/bulk buttons and resolves only visually anchored resource packs."""

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
        self.assertEqual((), parse_resource_inventory(image=_image(), lines=lines))

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
        self.assertEqual((), parse_resource_inventory(image=image, lines=_lines()))

    def test_missing_owned_count_does_not_guess_inventory(self) -> None:
        """Leaves an unparsed row non-actionable instead of inferring a stock count."""

        lines = tuple(line for line in _lines() if not line.text.startswith("Owned"))
        self.assertEqual((), parse_resource_inventory(image=_image(), lines=lines))

    def test_diamond_shop_tab_cannot_be_resource_inventory(self) -> None:
        """Requires the actual Bag and Resource tabs to be selected visually."""

        image = _image()
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 65, 269, 110), fill=(25, 42, 72))
        draw.rectangle((270, 65, 539, 110), fill=(140, 103, 50))
        self.assertIsNone(parse_resource_inventory(image=image, lines=_lines()))


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


def _line(text: str, x: int, y: int, width: int, height: int) -> OcrLine:
    """Builds one exact OCR fixture line."""

    return OcrLine(text, Bounds(x, y, width, height), 0.95)
