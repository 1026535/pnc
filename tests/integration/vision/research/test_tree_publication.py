"""Captured Research tree publication acceptance coverage."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import ResearchNodeId
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.research.publication import (
    image as _image,
    observe as _observe,
    production_components as _production_components,
)


class ResearchTreePublicationTests(unittest.TestCase):
    """Pin tree category, row geometry, and viewport obligations."""

    def test_qualified_category_grids_publish_observed_nodes_and_states(self) -> None:
        """Real category captures preserve labels, repeated art, MAX and padlocks."""
        builder, perception = _production_components()
        cases = (
            (ResearchCategory.ECONOMY, (
                (ResearchNodeId.FOOD_OUTPUT_I, 3, 4, False),
                (ResearchNodeId.WOOD_OUTPUT_I, 1, 5, False),
                (ResearchNodeId.FOOD_HARVEST_I, 2, 5, False),
                (ResearchNodeId.WOOD_HARVEST_I, 1, 5, False),
                (ResearchNodeId.IRON_OUTPUT_I, 1, 5, False),
            )),
            (ResearchCategory.MILITARY, (
                (ResearchNodeId.MARCH_SPEED_I, None, None, False),
                (ResearchNodeId.INFANTRY_HP_I, None, None, False),
                (ResearchNodeId.INFANTRY_ATK_I, None, None, False),
                (ResearchNodeId.INFANTRY_DEF_I, None, None, False),
                (ResearchNodeId.HUNT_MARCH_I, None, None, False),
                (ResearchNodeId.SIEGE_ATK_I, 2, 3, False),
                (ResearchNodeId.CAVALRY_ATK_I, None, None, False),
                (ResearchNodeId.RANGED_ATK_I, 1, 3, False),
                (ResearchNodeId.MARCH_QUEUE_I, None, None, False),
            )),
            (ResearchCategory.FORTIFICATION, (
                (ResearchNodeId.WALL_DEF_I, 2, 10, False),
                (ResearchNodeId.TRAP_ATK_I, 0, 3, False),
                (ResearchNodeId.TRAP_DEF_I, 0, 3, True),
                (ResearchNodeId.TRAP_HP_I, 0, 3, True),
                (ResearchNodeId.DEFENDER_ATK_I, 0, 3, True),
                (ResearchNodeId.DEFENDER_DEF_I, 0, 3, True),
                (ResearchNodeId.DEFENDER_HP_I, 0, 3, True),
            )),
        )
        for category, expected in cases:
            image = _image(f"research_tree_{category.value}_20260916.png")
            for path, observation in enumerate(_observe(builder, perception, image, session_id=category.value)):
                with self.subTest(category=category, publisher=path):
                    self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                    self.assertEqual(f"research_tree_{category.value}", observation.decision.layout_id)
                    rows = observation.entries(ListEntryKind.RESEARCH)
                    complete = {row.research_facts.node_id: row for row in rows
                                if row.row_status == RowRecognitionStatus.COMPLETE}
                    self.assertEqual({item[0] for item in expected}, set(complete))
                    self.assertEqual(len(expected) + (category == ResearchCategory.ECONOMY), len(rows))
                    for node, current, maximum, locked in expected:
                        row = complete[node]
                        facts = row.research_facts
                        self.assertEqual(category, facts.category)
                        self.assertEqual((current, maximum, locked),
                                         (facts.current_level, facts.max_level, facts.locked))
                        self.assertEqual(current is None or current == maximum, facts.maximum_reached)
                        self.assertTrue(row.bounds.contains_bounds(row.action_bounds))
                        self.assertTrue(row.action_bounds.contains_point(row.action_point))
                        self.assertEqual(observation.frame_ref, row.frame_ref)
                        self.assertEqual(observation.decision.layout_id, row.source_layout_id)
                    if category == ResearchCategory.ECONOMY:
                        self.assertEqual(RowRecognitionStatus.CLIPPED, rows[-1].row_status)
                        self.assertIsNone(rows[-1].action_point)
                        self.assertIsNone(rows[-1].action_bounds)

    def test_independent_economy_tree_reacquires_its_current_complete_rows(self) -> None:
        """A later viewport has a complete Iron Harvest tile with fresh geometry."""
        builder, perception = _production_components()
        image = _image("research_tree_economy_holdout_20260916.png")
        expected = {
            ResearchNodeId.FOOD_OUTPUT_I: (3, 4),
            ResearchNodeId.WOOD_OUTPUT_I: (1, 5),
            ResearchNodeId.FOOD_HARVEST_I: (2, 5),
            ResearchNodeId.WOOD_HARVEST_I: (1, 5),
            ResearchNodeId.IRON_OUTPUT_I: (1, 5),
            ResearchNodeId.IRON_HARVEST_I: (0, 5),
        }
        for path, observation in enumerate(_observe(builder, perception, image, session_id="economy-holdout")):
            with self.subTest(publisher=path):
                self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                self.assertEqual("research_tree_economy", observation.decision.layout_id)
                rows = observation.entries(ListEntryKind.RESEARCH)
                self.assertEqual(6, len(rows))
                by_node = {row.research_facts.node_id: row for row in rows}
                for node, levels in expected.items():
                    row = by_node[node]
                    self.assertEqual(RowRecognitionStatus.COMPLETE, row.row_status)
                    self.assertEqual(ResearchCategory.ECONOMY, row.research_facts.category)
                    self.assertEqual(levels, (row.research_facts.current_level, row.research_facts.max_level))
                    self.assertTrue(row.bounds.contains_bounds(row.action_bounds))
                    self.assertTrue(row.action_bounds.contains_point(row.action_point))
                    self.assertEqual(observation.frame_ref, row.frame_ref)
                for row in rows:
                    if row.research_facts.node_id is None:
                        self.assertEqual(RowRecognitionStatus.UNREADABLE, row.row_status)
                        self.assertIsNone(row.action_bounds)
                        self.assertIsNone(row.action_point)

    def test_upper_tree_publishes_complete_typed_rows_on_both_paths(self) -> None:
        """The 540x960 upper tree yields five complete rows and one clipped bottom tile."""

        builder, perception = _production_components()
        image = _image("research_tree_development.png")

        for observation in _observe(builder, perception, image, session_id="upper-tree"):
            with self.subTest(path=type(observation).__name__):
                self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)
                self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
                self.assertEqual(observation.decision.layout_id, "research_tree_development")
                entries = observation.entries(ListEntryKind.RESEARCH)
                self.assertEqual(6, len(entries))
                titles = [entry.title_text for entry in entries]
                self.assertEqual(
                    ["Construction I", "Research Speed I", "Troop Load I",
                     "Storage I", "Infirmary Cap I", "Miraculous"],
                    titles,
                )
                expected_nodes = (
                    ResearchNodeId.CONSTRUCTION_I,
                    ResearchNodeId.RESEARCH_SPEED_I,
                    ResearchNodeId.TROOP_LOAD_I,
                    ResearchNodeId.STORAGE_I,
                    ResearchNodeId.INFIRMARY_CAP_I,
                )
                for entry, node_id in zip(entries[:5], expected_nodes, strict=True):
                    self.assertEqual(RowRecognitionStatus.COMPLETE, entry.row_status)
                    self.assertIsNotNone(entry.action_point)
                    self.assertIsNotNone(entry.action_bounds)
                    self.assertTrue(entry.bounds.contains_point(entry.action_point))
                    facts = entry.research_facts
                    self.assertIsNotNone(facts)
                    self.assertEqual(ResearchCategory.DEVELOPMENT, facts.category)
                    self.assertEqual(node_id, facts.node_id)
                    self.assertEqual(observation.frame_ref, entry.frame_ref)
                    self.assertEqual(ScreenType.PNC_RESEARCH_TREE, entry.source_screen)
                    self.assertEqual("research_tree_development", entry.source_layout_id)
                clipped = entries[5]
                self.assertEqual(RowRecognitionStatus.CLIPPED, clipped.row_status)
                self.assertIsNone(clipped.action_point)
                self.assertIsNone(clipped.action_bounds)
                self.assertIsNotNone(clipped.research_facts)
                self.assertIsNone(clipped.research_facts.node_id)
                self.assertIsNone(observation.research_detail)
                self.assertEqual((), observation.research_queue_rows)

    def test_scrolled_tree_clips_header_rows_and_reads_lower_nodes(self) -> None:
        """The 900x1600 tour capture clips the covered top rows, not the visible ones."""

        builder, perception = _production_components()
        image = _image("research_tree_scrolled.png")

        for observation in _observe(builder, perception, image, session_id="scrolled-tree"):
            with self.subTest(path=type(observation).__name__):
                self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)
                self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
                entries = observation.entries(ListEntryKind.RESEARCH)
                self.assertEqual(7, len(entries))
                for entry in entries[:2]:
                    self.assertEqual(RowRecognitionStatus.CLIPPED, entry.row_status)
                    self.assertEqual("incomplete_node_tile_geometry", entry.metadata["unresolved_reason"])
                    self.assertIsNone(entry.action_point)
                    self.assertIsNone(entry.action_bounds)
                    self.assertIsNone(entry.research_facts.current_level)
                    self.assertIsNone(entry.research_facts.locked)
                self.assertEqual(ResearchNodeId.TROOP_LOAD_I, entries[0].research_facts.node_id)
                self.assertEqual(ResearchNodeId.STORAGE_I, entries[1].research_facts.node_id)
                expected = (
                    ("Infirmary Cap I", ResearchNodeId.INFIRMARY_CAP_I, 1, 5, False),
                    ("Miraculous Survival I", ResearchNodeId.MIRACULOUS_SURVIVAL_I, 0, 5, True),
                    ("Training Speed I", ResearchNodeId.TRAINING_SPEED_I, 0, 5, True),
                    ("Fast Heal I", ResearchNodeId.FAST_HEAL_I, 0, 5, True),
                    ("Food Output I", ResearchNodeId.FOOD_OUTPUT_I, 0, 5, True),
                )
                for entry, (title, node_id, level, max_level, locked) in zip(
                    entries[2:], expected, strict=True
                ):
                    self.assertEqual(title, entry.title_text)
                    self.assertEqual(RowRecognitionStatus.COMPLETE, entry.row_status)
                    self.assertIsNotNone(entry.action_point)
                    facts = entry.research_facts
                    self.assertEqual(node_id, facts.node_id)
                    self.assertEqual(level, facts.current_level)
                    self.assertEqual(max_level, facts.max_level)
                    self.assertEqual(locked, facts.locked)
                    self.assertEqual(observation.frame_ref, entry.frame_ref)
                    self.assertEqual("research_tree_development", entry.source_layout_id)
                self.assertIsNone(observation.research_detail)
                self.assertEqual((), observation.research_queue_rows)


if __name__ == "__main__":
    unittest.main()
