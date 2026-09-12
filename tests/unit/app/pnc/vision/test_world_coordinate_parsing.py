"""World coordinate parsing."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.world_map_coordinates import (
    parse_world_coordinate_dialog_field_text,
    parse_world_coordinate_text,
)



class WorldCoordinateParsingTests(unittest.TestCase):
    """Proves world coordinate parsing."""

    def test_world_coordinate_parser_accepts_fullwidth_colons_for_exact_world_map_proof(self) -> None:
        """Keeps fullwidth-colon OCR variants on the canonical coordinate parser path."""

        self.assertEqual(parse_world_coordinate_text("X\uff1a253 Y\uff1a987"), (253, 987))

    def test_world_coordinate_parser_recovers_live_noisy_merged_digits_and_rejects_resource_style_groups(self) -> None:
        """Parses bounded noisy coordinate fragments while still rejecting comma-grouped top-HUD resource numbers."""

        self.assertEqual(parse_world_coordinate_text("X:99287Y:707414"), (287, 707))
        self.assertEqual(parse_world_coordinate_text("X:101 4Y:695"), (101, 695))
        self.assertIsNone(parse_world_coordinate_text("X: 2,736,039 Y:958"))

    def test_world_coordinate_parser_rejects_one_off_overflows_instead_of_interior_substring_recovery(self) -> None:
        """Rejects plausible-looking overflow values instead of manufacturing nearby in-range coordinates."""

        for text in (
            "X:512 Y:200",
            "X:0 Y:1024",
            "X:999 Y:1023",
            "X:2736039 Y:958",
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse_world_coordinate_text(text))

    def test_world_coordinate_dialog_field_parser_handles_blank_labeled_and_invalid_kingdom_values(self) -> None:
        """Uses one shared numeric-field parser for dialog OCR enrichment and navigation proof."""

        self.assertIsNone(
            parse_world_coordinate_dialog_field_text(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                text="",
            )
        )
        self.assertEqual(
            parse_world_coordinate_dialog_field_text(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
                text="Y: 436",
            ),
            436,
        )
        self.assertIsNone(
            parse_world_coordinate_dialog_field_text(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
                text="K: 0",
            )
        )
