"""Captured Bag family/tab publication through both production observers."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import MiscItemIdentity
from pnc_automation.app.pnc.domain.observation import ListEntryKind, RowRecognitionStatus, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from tests.support.pnc.bag_items.publication import (
    BagPublicationAssertions,
    BoundedRapidOcrService,
    _BONUS_CARDS,
    _MILITARY_CARDS,
    _MISC_CARDS,
    _SPEEDUP_CARDS,
    _TREASURE_CARDS,
    _VICTORY_CARDS,
    build_both,
    capture,
    wire,
)
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


class BagTabPublicationTests(BagPublicationAssertions, unittest.TestCase):
    """Replayed Bag tabs qualify family identity and row contracts."""

    def test_speedup_capture_publishes_flat_time_reductions_on_both_paths(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        current = capture("bag_variants/bag_speedup_tab.png", session_id="v10-speedup")
        builder_observation, navigation_observation = build_both(
            builder, navigation, backend, current, ScreenType.PNC_BAG
        )
        for name, observation in (("observation_builder", builder_observation), ("navigation_perception", navigation_observation)):
            with self.subTest(publisher=name):
                self.assert_bag_identity(observation, current, BagTab.SPEEDUP)
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry, (minutes, owned) in zip(entries, _SPEEDUP_CARDS, strict=True):
                    self.assert_speedup_row(entry, minutes, owned, current)
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_bonus_capture_publishes_percentage_bonuses_on_both_paths(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        current = capture("bag_variants/bag_speedup_bonus_tab.png", session_id="v10-speedup-bonus")
        builder_observation, navigation_observation = build_both(
            builder, navigation, backend, current, ScreenType.PNC_BAG
        )
        for name, observation in (("observation_builder", builder_observation), ("navigation_perception", navigation_observation)):
            with self.subTest(publisher=name):
                self.assert_bag_identity(observation, current, BagTab.SPEEDUP)
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry, expected in zip(entries, _BONUS_CARDS, strict=True):
                    self.assert_bonus_row(entry, expected, current)
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_treasure_capture_publishes_typed_identities_on_both_paths(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        current = capture("bag_variants/bag_treasure_tab.png", session_id="v11-treasure")
        builder_observation, navigation_observation = build_both(
            builder, navigation, backend, current, ScreenType.PNC_BAG
        )
        for name, observation in (("observation_builder", builder_observation), ("navigation_perception", navigation_observation)):
            with self.subTest(publisher=name):
                self.assert_bag_identity(observation, current, BagTab.TREASURE)
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry, expected in zip(entries, _TREASURE_CARDS, strict=True):
                    self.assert_treasure_row(entry, expected, current)
                actionable = [entry for entry in entries if entry.row_status == RowRecognitionStatus.COMPLETE]
                self.assertEqual(1, len(actionable))
                self.assertEqual("treasure:arena_surprise_chest", actionable[0].metadata.get("identity"))
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_victory_capture_publishes_common_as_the_qualified_target(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        current = capture("bag_variants/bag_treasure_victory_tab.png", session_id="v11-victory")
        builder_observation, navigation_observation = build_both(
            builder, navigation, backend, current, ScreenType.PNC_BAG
        )
        for name, observation in (("observation_builder", builder_observation), ("navigation_perception", navigation_observation)):
            with self.subTest(publisher=name):
                self.assert_bag_identity(observation, current, BagTab.TREASURE)
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry, expected in zip(entries, _VICTORY_CARDS, strict=True):
                    self.assert_treasure_row(entry, expected, current)
                actionable = [entry for entry in entries if entry.row_status == RowRecognitionStatus.COMPLETE]
                self.assertEqual(1, len(actionable))
                self.assertEqual("treasure:common_first_victory_chest", actionable[0].metadata.get("identity"))
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_military_capture_publishes_typed_rows_on_both_paths(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        for reference_size in (None, (540, 960)):
            current = capture("bag_variants/bag_military_tab.png", session_id=f"v12-military:{reference_size}", reference_size=reference_size)
            builder_observation, navigation_observation = build_both(
                builder, navigation, backend, current, ScreenType.PNC_BAG
            )
            for name, observation in (("observation_builder", builder_observation), ("navigation_perception", navigation_observation)):
                with self.subTest(publisher=name, reference_size=reference_size):
                    self.assert_bag_identity(observation, current, BagTab.MILITARY)
                    entries = observation.entries(ListEntryKind.BAG_ITEM)
                    self.assertEqual(6, len(entries))
                    for entry, (identity, owned) in zip(entries, _MILITARY_CARDS, strict=True):
                        self.assert_typed_row(entry, tab=BagTab.MILITARY, identity=identity, expected_owned=owned, capture=current)
                    misc_control = observation.visible_elements.get(UiElementId.PNC_BAG_SUBTAB_MISC)
                    self.assertIsNotNone(misc_control)
                    assert misc_control is not None
                    self.assertEqual(VisibleElementSourceKind.TEMPLATE, misc_control.source_kind)
                    self.assertIsNone(observation.visible_elements.get(UiElementId.PNC_BAG_SUBTAB_MILITARY))
            self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_misc_capture_publishes_typed_rows_on_both_paths(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        for reference_size in (None, (540, 960)):
            current = capture("bag_variants/bag_misc_tab.png", session_id=f"v12-misc:{reference_size}", reference_size=reference_size)
            builder_observation, navigation_observation = build_both(
                builder, navigation, backend, current, ScreenType.PNC_BAG
            )
            for name, observation in (("observation_builder", builder_observation), ("navigation_perception", navigation_observation)):
                with self.subTest(publisher=name, reference_size=reference_size):
                    self.assert_bag_identity(observation, current, BagTab.MISC)
                    entries = observation.entries(ListEntryKind.BAG_ITEM)
                    self.assertEqual(6, len(entries))
                    for entry, (identity, owned) in zip(entries, _MISC_CARDS, strict=True):
                        self.assert_typed_row(entry, tab=BagTab.MISC, identity=identity, expected_owned=owned, capture=current)
                    military_control = observation.visible_elements.get(UiElementId.PNC_BAG_SUBTAB_MILITARY)
                    self.assertIsNotNone(military_control)
                    assert military_control is not None
                    self.assertEqual(VisibleElementSourceKind.TEMPLATE, military_control.source_kind)
                    self.assertIsNone(observation.visible_elements.get(UiElementId.PNC_BAG_SUBTAB_MISC))
            self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_tab_switch_publishes_only_current_family_rows(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        military_capture = capture("bag_variants/bag_military_tab.png", session_id="v12-switch:military")
        misc_capture = capture("bag_variants/bag_misc_tab.png", session_id="v12-switch:misc")
        build_both(builder, navigation, backend, military_capture, ScreenType.PNC_BAG)
        misc_builder, misc_navigation = build_both(builder, navigation, backend, misc_capture, ScreenType.PNC_BAG)
        for name, observation in (("observation_builder", misc_builder), ("navigation_perception", misc_navigation)):
            with self.subTest(publisher=name):
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry in entries:
                    facts = entry.bag_item_facts
                    self.assertIsNotNone(facts)
                    assert facts is not None
                    self.assertEqual(BagTab.MISC, facts.selected_tab)
                    self.assertIsInstance(facts.identity, MiscItemIdentity)
                    self.assertNotIn("military:", entry.metadata.get("identity") or "")


if __name__ == "__main__":
    unittest.main()
