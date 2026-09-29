"""Unit tests for Bag producer gates, bounded retry and preview clipping."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from PIL import Image

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import MilitaryItemIdentity, MilitaryKind, MiscItemIdentity, MiscKind
from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.bag_items import BagItemContentProducer
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


def _line(text: str, bounds: Bounds) -> OcrLine:
    return OcrLine(text=text, bounds=bounds, confidence=0.9)


class ProducerDispatchTests(unittest.TestCase):
    """The producer only runs under qualified screen/layout/tab gates."""

    def test_name_retry_preserves_selected_family_and_observation_only_rows(self) -> None:
        for tab, retry_name, expected in (
            (BagTab.MILITARY, "6-hr Anti-Scout", MilitaryItemIdentity(MilitaryKind.ANTI_SCOUT, duration_minutes=360)),
            (BagTab.MISC, "Pickaxe", MiscItemIdentity(MiscKind.PICKAXE)),
            (BagTab.MILITARY, "5 Min Speedup", None),
            (BagTab.MISC, "5 Min Speedup", None),
        ):
            with self.subTest(tab=tab, retry_name=retry_name):
                context = Mock()
                context.read_lines.side_effect = [
                    (_line("Unreadable name", Bounds(205, 306, 300, 30)), _line("Owned: 7", Bounds(49, 450, 150, 24))),
                    (_line(retry_name, Bounds(205, 306, 300, 30)),),
                ]
                matcher = Mock()
                matcher.find_best_match.return_value = None
                entry = BagItemContentProducer(matcher=matcher)._card_entry(
                    image=Image.new("RGB", (900, 1600)),
                    prepared=Mock(),
                    card_bounds=Bounds(9, 286, 882, 202),
                    card_clipped=False,
                    card_index=0,
                    tab=tab,
                    ocr_context=context,
                )
                self.assertEqual(expected, entry.bag_item_facts.identity)
                self.assertEqual(tab, entry.bag_item_facts.selected_tab)
                self.assertEqual(7, entry.bag_item_facts.owned_count)
                self.assertEqual(
                    RowRecognitionStatus.NO_ACTION if expected is not None else RowRecognitionStatus.UNREADABLE,
                    entry.row_status,
                )
                self.assertIsNone(entry.action_point)
                self.assertIsNone(entry.action_bounds)
                self.assertEqual(2, context.read_lines.call_count)

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
