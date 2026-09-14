"""Canonical building-requirement parser qualifications."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    _add_upgrade_requirement_controls,
    _find_building_requirement_go_line,
    _find_building_requirement_header_line,
    _find_building_requirement_target_line,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


VIEWPORT = (900, 1600)


def _line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    """Create one localized OCR line for the canonical requirement parser."""

    return OcrLine(text=text, bounds=Bounds(x, y, width, height), confidence=1.0)


def _requirement_lines(*, include_go: bool) -> tuple[OcrLine, ...]:
    """Return one satisfied row and one optionally actionable unmet row."""

    lines = [
        _line("Requirement", x=62, y=713, width=177, height=27),
        _line("Castle: Lv.8", x=154, y=768, width=147, height=24),
        _line("Warehouse: Lv.9", x=154, y=834, width=210, height=24),
        _line("Materials required", x=61, y=931, width=251, height=26),
    ]
    if include_go:
        lines.append(_line("Go", x=732, y=832, width=47, height=31))
    return tuple(lines)


class BuildingRequirementParserTests(unittest.TestCase):
    """Prove labels are tied to an unmet row after the visual screen is owned."""

    def test_parser_publishes_header_and_target_for_actionable_unmet_row(self) -> None:
        """The requirement label follows the row aligned with the parsed Go affordance."""

        image = Image.new("RGB", VIEWPORT)
        lines = _requirement_lines(include_go=True)
        header = _find_building_requirement_header_line(image=image, lines=lines)
        self.assertIsNotNone(header)
        assert header is not None
        go_line = _find_building_requirement_go_line(image=image, lines=lines, header=header)
        self.assertIsNotNone(go_line)
        assert go_line is not None
        target_line = _find_building_requirement_target_line(
            image=image,
            lines=lines,
            header=header,
            go_line=go_line,
        )
        self.assertIsNotNone(target_line)
        assert target_line is not None
        self.assertEqual(target_line.text, "Warehouse: Lv.9")

        visible_elements = {}
        _add_upgrade_requirement_controls(
            image=image,
            lines=lines,
            screen_type=ScreenType.PNC_INSTITUTE,
            visible_elements=visible_elements,
        )

        self.assertEqual(
            visible_elements[UiElementId.PNC_BUILDING_REQUIREMENT_HEADER].extracted_text,
            "Requirement",
        )
        self.assertEqual(
            visible_elements[UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL].extracted_text,
            "Warehouse: Lv.9",
        )
        self.assertTrue(
            all(
                visible_elements[selector_id].source_kind == VisibleElementSourceKind.OCR
                for selector_id in (
                    UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                    UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
                )
            )
        )

    def test_parser_omits_requirement_labels_when_no_actionable_row_exists(self) -> None:
        """A heading with no Go row cannot publish an unmet prerequisite label."""

        visible_elements = {}
        _add_upgrade_requirement_controls(
            image=Image.new("RGB", VIEWPORT),
            lines=_requirement_lines(include_go=False),
            screen_type=ScreenType.PNC_INSTITUTE,
            visible_elements=visible_elements,
        )

        self.assertEqual(visible_elements, {})


if __name__ == "__main__":
    unittest.main()
