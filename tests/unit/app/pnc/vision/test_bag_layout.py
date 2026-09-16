"""Shared Bag shell geometry: measured subtab selection and card bands."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.bag import BAG_TAB_ORDER, BagTab, bag_tab_selector_id
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.bag_layout import (
    bag_body_bounds,
    bag_body_bounds_for_size,
    detect_bag_card_geometry,
    detect_selected_bag_tab,
)
from pnc_automation.core.vision.image.models import Bounds
from tests.support.paths import TEST_DATA_ROOT


_FIXTURES = TEST_DATA_ROOT / "screen_recognition"
_SELECTED_TAB_CAPTURES = {
    "bag.png": BagTab.RESOURCE,
    "bag_current_testing.png": BagTab.RESOURCE,
    "bag_variants/bag_resource_scroll_first.png": BagTab.RESOURCE,
    "bag_variants/bag_resource_scroll_settled.png": BagTab.RESOURCE,
    "bag_variants/bag_speedup_tab.png": BagTab.SPEEDUP,
    "bag_variants/bag_treasure_tab.png": BagTab.TREASURE,
}


def _capture(name: str) -> Image.Image:
    with Image.open(_FIXTURES / name) as source:
        return source.convert("RGB")


class BagTabSelectionMeasurementTests(unittest.TestCase):
    """The gold subtab container maps to canonical slots on saved captures."""

    def test_saved_captures_measure_their_selected_tab(self) -> None:
        for name, expected in _SELECTED_TAB_CAPTURES.items():
            with self.subTest(capture=name):
                self.assertEqual(expected, detect_selected_bag_tab(_capture(name)))

    def test_absent_or_ambiguous_selection_is_unknown(self) -> None:
        solid = Image.new("RGB", (540, 960), (19, 28, 44))
        self.assertIsNone(detect_selected_bag_tab(solid))

        bag = _capture("bag.png")
        blanked = bag.copy()
        # Removing the selected gold container leaves no measurable selection.
        blanked.paste((19, 28, 44), (0, 122, 108, 162))
        self.assertIsNone(detect_selected_bag_tab(blanked))

        doubled = bag.copy()
        # A second gold container makes selection ambiguous and fails closed.
        doubled.paste(bag.crop((0, 122, 108, 162)), (108, 122))
        self.assertIsNone(detect_selected_bag_tab(doubled))

    def test_fixed_selector_mapping_covers_canonical_slots(self) -> None:
        self.assertEqual(5, len(BAG_TAB_ORDER))
        self.assertEqual(UiElementId.PNC_BAG_SUBTAB_RESOURCE, bag_tab_selector_id(BagTab.RESOURCE))
        self.assertEqual(UiElementId.PNC_BAG_SUBTAB_SPEEDUP, bag_tab_selector_id(BagTab.SPEEDUP))
        self.assertEqual(UiElementId.PNC_BAG_SUBTAB_MILITARY, bag_tab_selector_id(BagTab.MILITARY))
        self.assertEqual(UiElementId.PNC_BAG_SUBTAB_TREASURE, bag_tab_selector_id(BagTab.TREASURE))
        self.assertEqual(UiElementId.PNC_BAG_SUBTAB_MISC, bag_tab_selector_id(BagTab.MISC))


class BagCardGeometryTests(unittest.TestCase):
    """Resource, Speedup and Treasure captures share one measured card layout."""

    def test_body_bounds_follow_the_reviewed_ratios(self) -> None:
        self.assertEqual(Bounds(0, 163, 540, 797), bag_body_bounds_for_size((540, 960)))
        self.assertEqual(Bounds(0, 272, 900, 1328), bag_body_bounds_for_size((900, 1600)))
        self.assertEqual(Bounds(0, 163, 540, 797), bag_body_bounds(_capture("bag.png")))

    def test_card_geometry_is_shared_across_subtabs(self) -> None:
        resource = tuple(card.bounds for card in detect_bag_card_geometry(_capture("bag_current_testing.png")))
        speedup = tuple(card.bounds for card in detect_bag_card_geometry(_capture("bag_variants/bag_speedup_tab.png")))
        treasure = tuple(card.bounds for card in detect_bag_card_geometry(_capture("bag_variants/bag_treasure_tab.png")))

        self.assertEqual(6, len(resource))
        self.assertEqual(resource, speedup)
        self.assertEqual(resource, treasure)
        self.assertTrue(all(not card.clipped for card in detect_bag_card_geometry(_capture("bag_current_testing.png"))))

    def test_scrolled_capture_marks_edge_bands_clipped(self) -> None:
        cards = detect_bag_card_geometry(_capture("bag_variants/bag_resource_scroll_settled.png"))

        self.assertEqual(7, len(cards))
        self.assertTrue(cards[0].clipped)
        self.assertTrue(cards[-1].clipped)
        self.assertTrue(all(not card.clipped for card in cards[1:-1]))


if __name__ == "__main__":
    unittest.main()
