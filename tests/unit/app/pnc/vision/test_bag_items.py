"""Unit tests for the Bag item domain model and content producer."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from PIL import Image

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import (
    BagItemApplicability,
    BagItemFacts,
    BagPreviewRewardFacts,
    SpeedBonusIdentity,
    TimeReductionIdentity,
    TreasureIdentity,
    TreasureKind,
    bag_chest_preview_layout,
    bag_chest_preview_layouts,
    bag_item_facts_metadata,
    bag_item_identity_key,
    bag_item_inspection_supported,
    treasure_identity_for_label,
    treasure_identity_title,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.bag_items import (
    BagItemContentProducer,
    _mark_duplicate_identities,
    _owned_count,
    _speedup_identity,
    _CardLine,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


def _line(text: str, bounds: Bounds) -> OcrLine:
    return OcrLine(text=text, bounds=bounds, confidence=0.9)


def _card_line(text: str, *, rel_x: int, rel_y: int) -> _CardLine:
    return _CardLine(line=_line(text, Bounds(0, 0, 10, 10)), rel_x=rel_x, rel_y=rel_y)


def _entry(identity: BagItemFacts | None, status: RowRecognitionStatus) -> DetectedListEntry:
    action_bounds = Bounds(150, 290, 50, 45)
    complete = status == RowRecognitionStatus.COMPLETE
    return DetectedListEntry(
        kind=ListEntryKind.BAG_ITEM,
        bounds=Bounds(9, 286, 882, 202),
        action_point=action_bounds.center() if complete else None,
        action_bounds=action_bounds if complete else None,
        row_status=status,
        bag_item_facts=identity,
    )


class TreasureIdentityTests(unittest.TestCase):
    """Treasure labels resolve only through canonical displayed titles."""

    def test_plain_kind_titles_resolve(self) -> None:
        for label, kind in (
            ("Arena Surprise Chest", TreasureKind.ARENA_SURPRISE_CHEST),
            ("Common 1st Victory Chest", TreasureKind.COMMON_FIRST_VICTORY_CHEST),
            ("Rare 1st Victory Chest", TreasureKind.RARE_FIRST_VICTORY_CHEST),
            ("Pinball", TreasureKind.PINBALL),
            ("Starna's Dice", TreasureKind.STARNA_DICE),
            ("Diamond Chest", TreasureKind.DIAMOND_CHEST),
        ):
            with self.subTest(label=label):
                self.assertEqual(TreasureIdentity(kind=kind), treasure_identity_for_label(label))

    def test_levelled_kinds_distinguish_variants(self) -> None:
        self.assertEqual(
            TreasureIdentity(kind=TreasureKind.OATH_RUNE_CHEST, level=3),
            treasure_identity_for_label("Lv.3 Oath Rune Chest"),
        )
        self.assertEqual(
            TreasureIdentity(kind=TreasureKind.DEMON_CHEST, level=41),
            treasure_identity_for_label("Lv.41 Demon Chest"),
        )
        self.assertNotEqual(
            treasure_identity_for_label("Lv.21 Demon Chest"),
            treasure_identity_for_label("Lv.41 Demon Chest"),
        )

    def test_letter_confused_level_recovers_oath(self) -> None:
        self.assertEqual(
            TreasureIdentity(kind=TreasureKind.OATH_RUNE_CHEST, level=23),
            treasure_identity_for_label("Lv.230ath Rune Chest"),
        )

    def test_unknown_and_blank_labels_stay_unknown(self) -> None:
        for label in (
            None, "", "   ", "Mystery Crate", "Lv.10 Diamond Chest", "Lv.1 Elros",
            "Oath Rune Chest", "Demon Chest", "Lv.0 Demon Chest",
        ):
            with self.subTest(label=label):
                self.assertIsNone(treasure_identity_for_label(label))

    def test_levelled_kind_contract(self) -> None:
        with self.assertRaises(ValueError):
            TreasureIdentity(kind=TreasureKind.DEMON_CHEST)
        with self.assertRaises(ValueError):
            TreasureIdentity(kind=TreasureKind.PINBALL, level=5)
        with self.assertRaises(ValueError):
            TreasureIdentity(kind=TreasureKind.OATH_RUNE_CHEST, level=0)

    def test_canonical_titles_and_keys(self) -> None:
        self.assertEqual(
            "Lv.23 Oath Rune Chest",
            treasure_identity_title(TreasureIdentity(TreasureKind.OATH_RUNE_CHEST, 23)),
        )
        self.assertEqual(
            "Arena Surprise Chest",
            treasure_identity_title(TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST)),
        )
        self.assertEqual(
            "treasure:demon_chest:21",
            bag_item_identity_key(TreasureIdentity(TreasureKind.DEMON_CHEST, 21)),
        )
        self.assertEqual(
            "treasure:arena_surprise_chest",
            bag_item_identity_key(TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST)),
        )

    def test_qualified_inspection_targets(self) -> None:
        for kind in (TreasureKind.ARENA_SURPRISE_CHEST, TreasureKind.COMMON_FIRST_VICTORY_CHEST):
            with self.subTest(kind=kind):
                self.assertTrue(bag_item_inspection_supported(TreasureIdentity(kind)))
        for kind in (
            TreasureKind.RARE_FIRST_VICTORY_CHEST,
            TreasureKind.PINBALL,
            TreasureKind.STARNA_DICE,
            TreasureKind.DIAMOND_CHEST,
        ):
            with self.subTest(kind=kind):
                self.assertFalse(bag_item_inspection_supported(TreasureIdentity(kind)))
        self.assertFalse(
            bag_item_inspection_supported(
                TimeReductionIdentity(BagItemApplicability.GENERAL, 30)
            )
        )
        self.assertEqual(
            "bag_arena_chest_preview",
            bag_chest_preview_layout(TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST)),
        )
        self.assertEqual(
            "bag_common_victory_preview",
            bag_chest_preview_layout(TreasureIdentity(TreasureKind.COMMON_FIRST_VICTORY_CHEST)),
        )
        self.assertIsNone(
            bag_chest_preview_layout(TreasureIdentity(TreasureKind.OATH_RUNE_CHEST, 3))
        )
        self.assertEqual(
            frozenset({"bag_arena_chest_preview", "bag_common_victory_preview"}),
            bag_chest_preview_layouts(),
        )


class SpeedupIdentityTests(unittest.TestCase):
    """Speedup identity resolves from name/description tokens conservatively."""

    def test_flat_minute_name(self) -> None:
        self.assertEqual(
            TimeReductionIdentity(BagItemApplicability.GENERAL, 30),
            _speedup_identity("30-min Speedup", "Reduces remaining time by 30 mins."),
        )

    def test_hour_name_converts(self) -> None:
        self.assertEqual(
            TimeReductionIdentity(BagItemApplicability.GENERAL, 180),
            _speedup_identity("3-hr Speedup", "Reduces remaining time by 3 hrs."),
        )

    def test_flat_category_is_preserved_and_must_agree(self) -> None:
        self.assertEqual(
            TimeReductionIdentity(BagItemApplicability.RESEARCH, 30),
            _speedup_identity("30-min Research Speedup", "Reduces research time by 30 mins."),
        )
        self.assertIsNone(
            _speedup_identity("30-min Research Speedup", "Reduces heal time by 30 mins.")
        )

    def test_zero_ocr_values_stay_unknown(self) -> None:
        for name, description in (
            ("0-min Speedup", None),
            (None, "Reduces remaining time by 0 mins."),
            ("0% Build Speedup", "Boosts build speed by 0% for 1 hr."),
            ("10% Build Speedup", "Boosts build speed by 10% for 0 hr."),
        ):
            with self.subTest(name=name, description=description):
                self.assertIsNone(_speedup_identity(name, description))

    def test_description_supplies_dropped_digit(self) -> None:
        self.assertEqual(
            TimeReductionIdentity(BagItemApplicability.GENERAL, 5),
            _speedup_identity("-min Speedup", "Reduces remaining time by 5 mins."),
        )

    def test_percentage_bonus_with_active_duration(self) -> None:
        self.assertEqual(
            SpeedBonusIdentity(BagItemApplicability.BUILD, 10, 60),
            _speedup_identity("10% Build Speedup", "Boosts build speed by 10% for 1 hr."),
        )
        self.assertEqual(
            SpeedBonusIdentity(BagItemApplicability.TRAINING, 30, 60),
            _speedup_identity("30% Training Speedup", "Boosts training speed by 30% for 1 hr."),
        )

    def test_noisy_desc_verb_still_parses(self) -> None:
        self.assertEqual(
            SpeedBonusIdentity(BagItemApplicability.TRAINING, 30, 60),
            _speedup_identity("30% Training Speedup", "Bo0sts training speed by 30% for1 hr."),
        )

    def test_contradictions_stay_unknown(self) -> None:
        self.assertIsNone(
            _speedup_identity("10-min Speedup", "Reduces remaining time by 30 mins.")
        )
        self.assertIsNone(
            _speedup_identity("10% Build Speedup", "Boosts research speed by 10% for 1 hr.")
        )
        self.assertIsNone(
            _speedup_identity("10% Build Speedup", "Boosts build speed by 30% for 1 hr.")
        )

    def test_unreadable_inputs_stay_unknown(self) -> None:
        for name, desc in ((None, None), ("Speedup", None), (None, "Some description")):
            with self.subTest(name=name, desc=desc):
                self.assertIsNone(_speedup_identity(name, desc))

    def test_positive_integer_contracts(self) -> None:
        with self.assertRaises(ValueError):
            TimeReductionIdentity(BagItemApplicability.GENERAL, 0)
        with self.assertRaises(ValueError):
            SpeedBonusIdentity(BagItemApplicability.BUILD, 0, 60)
        with self.assertRaises(ValueError):
            SpeedBonusIdentity(BagItemApplicability.BUILD, 10, 0)


class OwnedCountTests(unittest.TestCase):
    """Owned counts parse displayed literals including grouped and confused forms."""

    def test_owned_variants(self) -> None:
        for text, expected in (
            ("Owned: 50", 50),
            ("Owned:5,800", 5800),
            ("Dwned:6,900", 6900),
            ("Owned:0", 0),
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    expected,
                    _owned_count([_card_line(text, rel_x=40, rel_y=167)]),
                )

    def test_unreadable_owned_stays_unknown(self) -> None:
        self.assertIsNone(_owned_count([_card_line("Owned: many", rel_x=40, rel_y=167)]))
        self.assertIsNone(_owned_count([]))


class FactsMetadataTests(unittest.TestCase):
    """Row metadata carries the canonical identity key for tap matching."""

    def test_metadata_only_when_resolved(self) -> None:
        facts = BagItemFacts(
            selected_tab=BagTab.TREASURE,
            identity=TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST),
        )
        self.assertEqual(
            {"identity": "treasure:arena_surprise_chest"},
            bag_item_facts_metadata(facts),
        )
        self.assertEqual(
            {},
            bag_item_facts_metadata(BagItemFacts(selected_tab=BagTab.SPEEDUP)),
        )


class DuplicateIdentityTests(unittest.TestCase):
    """Duplicate complete identities withhold the tap; non-action rows keep theirs."""

    def test_duplicate_complete_rows_become_ambiguous(self) -> None:
        facts = BagItemFacts(
            selected_tab=BagTab.TREASURE,
            identity=TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST),
            inspection_glyph_present=True,
        )
        entries = (
            _entry(facts, RowRecognitionStatus.COMPLETE),
            _entry(facts, RowRecognitionStatus.COMPLETE),
        )
        marked = _mark_duplicate_identities(entries)
        self.assertTrue(all(e.row_status == RowRecognitionStatus.AMBIGUOUS for e in marked))
        self.assertTrue(all(e.action_point is None for e in marked))

    def test_distinct_complete_identities_stay_complete(self) -> None:
        entries = (
            _entry(
                BagItemFacts(
                    selected_tab=BagTab.TREASURE,
                    identity=TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST),
                    inspection_glyph_present=True,
                ),
                RowRecognitionStatus.COMPLETE,
            ),
            _entry(
                BagItemFacts(
                    selected_tab=BagTab.TREASURE,
                    identity=TreasureIdentity(TreasureKind.COMMON_FIRST_VICTORY_CHEST),
                    inspection_glyph_present=True,
                ),
                RowRecognitionStatus.COMPLETE,
            ),
        )
        marked = _mark_duplicate_identities(entries)
        self.assertTrue(all(e.row_status == RowRecognitionStatus.COMPLETE for e in marked))

    def test_duplicate_no_action_rows_are_untouched(self) -> None:
        facts = BagItemFacts(
            selected_tab=BagTab.TREASURE,
            identity=TreasureIdentity(TreasureKind.DEMON_CHEST, 21),
            inspection_glyph_present=True,
        )
        entries = (
            _entry(facts, RowRecognitionStatus.NO_ACTION),
            _entry(facts, RowRecognitionStatus.NO_ACTION),
        )
        marked = _mark_duplicate_identities(entries)
        self.assertTrue(all(e.row_status == RowRecognitionStatus.NO_ACTION for e in marked))


class ProducerDispatchTests(unittest.TestCase):
    """The producer only runs under qualified screen/layout/tab gates."""

    def test_clipped_preview_owned_text_never_becomes_a_count(self) -> None:
        context = Mock()
        context.read_lines.side_effect = [(), (), (), (), (
            _line("Mithril Ore", Bounds(135, 601, 100, 18)),
            _line("Owned: 783,180", Bounds(135, 654, 100, 16)),
        )]
        result = BagItemContentProducer().preview_additions(
            image=Image.new("RGB", (540, 960)),
            ocr_context=context,
            layout_id="bag_common_victory_preview",
        )
        last = result.list_entries[-1]
        self.assertEqual(RowRecognitionStatus.CLIPPED, last.row_status)
        self.assertEqual("Mithril Ore", last.title_text)
        self.assertIsNone(last.bag_reward_facts.displayed_owned_count)
        self.assertEqual(662, last.bounds.y + last.bounds.height)
        self.assertIsNone(last.action_point)

    def test_additions_for_screen_gates_on_qualified_layout(self) -> None:
        producer = BagItemContentProducer()
        for layout_id in ("bag_arena_chest_preview", "bag_common_victory_preview"):
            with self.subTest(layout_id=layout_id):
                context = Mock()
                context.read_lines.return_value = ()
                result = producer.additions_for_screen(
                    image=Image.new("RGB", (540, 960)),
                    screen_type=ScreenType.PNC_BAG_CHEST_PREVIEW,
                    ocr_context=context,
                    layout_id=layout_id,
                )
                self.assertIsNotNone(result)
        context = Mock()
        result = producer.additions_for_screen(
            image=Image.new("RGB", (540, 960)),
            screen_type=ScreenType.PNC_BAG_CHEST_PREVIEW,
            ocr_context=context,
            layout_id="unqualified_popup",
        )
        self.assertIsNone(result)
        context.read_lines.assert_not_called()

    def test_additions_for_screen_ignores_other_screens(self) -> None:
        producer = BagItemContentProducer()
        context = Mock()
        for screen in (ScreenType.PNC_BAG, ScreenType.PNC_HOME_CITY, ScreenType.PNC_TRIAL_CHALLENGE):
            with self.subTest(screen=screen):
                self.assertIsNone(
                    producer.additions_for_screen(
                        image=Image.new("RGB", (540, 960)),
                        screen_type=screen,
                        ocr_context=context,
                        layout_id="bag_arena_chest_preview",
                    )
                )
        context.read_lines.assert_not_called()


if __name__ == "__main__":
    unittest.main()
