"""Matched-region click points retain catalog ownership and center defaults."""

import unittest

from pnc_automation.app.pnc.vision.selector_catalog import (
    SelectorCatalogClickDefinition,
    load_selector_schema_click_definition,
)
from pnc_automation.app.pnc.vision.selectors import ClickDefinition
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.image.models import Bounds


class SelectorClickPointTests(unittest.TestCase):
    def test_native_match_targets_button_above_caption(self) -> None:
        self.assertEqual(
            (672, 533),
            ClickDefinition(point_ratio=(0.5, 0.35)).resolve_point(Bounds(633, 511, 78, 62)),
        )

    def test_unspecified_point_preserves_existing_center(self) -> None:
        bounds = Bounds(33, 7, 104, 73)
        self.assertEqual(bounds.center(), ClickDefinition().resolve_point(bounds))

    def test_click_point_round_trips_through_canonical_schema(self) -> None:
        authored = SelectorCatalogClickDefinition(
            anchor="center", outcomes=(), point_ratio=(0.5, 0.35),
        )
        loaded = load_selector_schema_click_definition(
            authored.to_document(), selector_id="PNC_HOME_SELECTED_BUILDING_UPGRADE_CHIP",
            document_label="test", selector_label="selector",
        )
        self.assertEqual(authored, loaded)

    def test_invalid_point_ratios_are_rejected(self) -> None:
        for value in ((0.5,), (0.5, True), (0.5, float("nan")), (0.5, 1.1)):
            with self.subTest(value=value), self.assertRaises(SelectorResolutionError):
                SelectorCatalogClickDefinition(anchor="center", outcomes=(), point_ratio=value)
