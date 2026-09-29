"""Captured Research detail publication acceptance coverage."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import ListEntryKind, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import ResearchNodeId, ResearchQueueState
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer

from tests.support.pnc.research.publication import (
    image as _image,
    observe as _observe,
    production_components as _production_components,
)

START = UiElementId.PNC_RESEARCH_START_BUTTON


class ResearchDetailPublicationTests(unittest.TestCase):
    """Pin detail identity, costs, controls, and max-panel obligations."""

    def test_category_detail_captures_resolve_the_matching_supported_node(self) -> None:
        """Shared detail parsing resolves each catalog without inferring category."""
        builder, perception = _production_components()
        for category, node in (
            ("economy", ResearchNodeId.FOOD_OUTPUT_I),
            ("military", ResearchNodeId.SIEGE_ATK_I),
            ("fortification", ResearchNodeId.WALL_DEF_I),
        ):
            image = _image(f"{category}_detail_idle.png", subdir="research_variants")
            for path, observation in enumerate(_observe(builder, perception, image, session_id=f"{category}-detail")):
                with self.subTest(category=category, publisher=path):
                    self.assertEqual("research_tree_node_detail", observation.decision.layout_id)
                    self.assertEqual(node, observation.research_detail.node_id)
                    self.assertIsNone(observation.research_detail.category)
                    self.assertEqual(observation.frame_ref, observation.research_detail.frame_ref)
                    self.assertEqual(VisibleElementSourceKind.TEMPLATE, observation.get(START).source_kind)
                    self.assertTrue(observation.research_detail.costs)

    def test_idle_detail_publishes_typed_costs_times_and_premium_geometry(self) -> None:
        """The idle Construction detail resolves identity, costs, times, and Start."""

        builder, perception = _production_components()
        image = _image("research_node_detail.png")

        for observation in _observe(builder, perception, image, session_id="idle-detail"):
            with self.subTest(path=type(observation).__name__):
                self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)
                self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
                self.assertEqual(observation.decision.layout_id, "research_tree_node_detail")
                detail = observation.research_detail
                self.assertIsNotNone(detail)
                self.assertEqual(ResearchNodeId.CONSTRUCTION_I, detail.node_id)
                self.assertIsNone(detail.category)
                self.assertEqual(2, detail.current_level)
                self.assertEqual(5, detail.max_level)
                costs = {cost.resource_type: cost for cost in detail.costs}
                self.assertEqual({"food", "wood"}, set(costs))
                self.assertEqual(16400, costs["food"].required)
                self.assertEqual(490250, costs["food"].available)
                self.assertEqual(7010, costs["wood"].required)
                self.assertEqual(740224, costs["wood"].available)
                self.assertEqual("00:45:41", detail.original_time_text)
                self.assertEqual("00:44:47", detail.actual_time_text)
                self.assertEqual(90, detail.premium_gem_cost)
                self.assertIsNotNone(detail.premium_button_bounds)
                self.assertEqual(ResearchQueueState.UNKNOWN, detail.queue_state)
                self.assertIsNone(detail.queue_timer_text)
                self.assertEqual(observation.frame_ref, detail.frame_ref)
                self.assertEqual(ScreenType.PNC_RESEARCH_TREE, detail.source_screen)
                self.assertEqual("research_tree_node_detail", detail.source_layout_id)
                self.assertEqual((), observation.entries(ListEntryKind.RESEARCH))
                self.assertEqual((), observation.research_queue_rows)
                self.assertEqual(
                    VisibleElementSourceKind.TEMPLATE, observation.require(START).source_kind
                )

    def test_active_detail_publishes_queue_timer_without_start_or_premium(self) -> None:
        """The active detail reads its countdown and stays read-only."""

        builder, perception = _production_components()
        image = _image("research_node_detail_active.png")

        for observation in _observe(builder, perception, image, session_id="active-detail"):
            with self.subTest(path=type(observation).__name__):
                self.assertEqual(observation.decision.layout_id, "research_tree_node_detail")
                self.assertFalse(observation.has(START))
                detail = observation.research_detail
                self.assertIsNotNone(detail)
                self.assertEqual(ResearchNodeId.CONSTRUCTION_I, detail.node_id)
                self.assertEqual(2, detail.current_level)
                self.assertEqual(5, detail.max_level)
                self.assertEqual(ResearchQueueState.ACTIVE, detail.queue_state)
                self.assertEqual("00:44:45", detail.queue_timer_text)
                self.assertIsNone(detail.premium_gem_cost)
                self.assertIsNone(detail.premium_button_bounds)
                self.assertEqual(observation.frame_ref, detail.frame_ref)
                self.assertEqual("research_tree_node_detail", detail.source_layout_id)

    def test_economy_holdout_detail_resolves_identity_from_its_own_title_band(self) -> None:
        """The independent holdout resolves its measured title without icon noise."""

        builder, perception = _production_components()
        image = _image("economy_detail_idle_holdout.png", subdir="research_variants")

        for observation in _observe(builder, perception, image, session_id="holdout-detail"):
            with self.subTest(path=type(observation).__name__):
                self.assertEqual(observation.decision.layout_id, "research_tree_node_detail")
                detail = observation.research_detail
                self.assertIsNotNone(detail)
                self.assertEqual(ResearchNodeId.FOOD_OUTPUT_I, detail.node_id)
                self.assertIsNone(detail.category)
                self.assertEqual(3, detail.current_level)
                self.assertEqual(4, detail.max_level)
                costs = {cost.resource_type: cost for cost in detail.costs}
                self.assertEqual({"food", "wood"}, set(costs))
                self.assertEqual(28300, costs["food"].required)
                self.assertEqual(12200, costs["wood"].required)
                self.assertEqual(69, detail.premium_gem_cost)
                self.assertEqual(observation.frame_ref, detail.frame_ref)
                self.assertEqual("research_tree_node_detail", detail.source_layout_id)

    def test_max_detail_reads_observed_levels_and_effects_without_actions(self) -> None:
        """The live max-level panel is readable at both sizes and never primes Start."""

        builder, perception = _production_components()
        source = _image("research_node_detail_max_20260916.png")
        for size in ((540, 960), (900, 1600)):
            for observation in _observe(
                builder, perception, source.resize(size), session_id=f"max-detail:{size}",
            ):
                with self.subTest(size=size, frame=observation.frame_ref):
                    self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)
                    self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                    self.assertEqual("research_tree_node_detail_max", observation.decision.layout_id)
                    detail = observation.research_detail
                    self.assertIsNotNone(detail)
                    self.assertEqual(ResearchNodeId.TROOP_LOAD_I, detail.node_id)
                    self.assertEqual((5, 5), (detail.current_level, detail.max_level))
                    self.assertEqual(2, len(detail.effect_records))
                    effects = " ".join(record.text for record in detail.effect_records)
                    self.assertIn("+572", effects)
                    self.assertIn("+5%", effects)
                    self.assertEqual((), detail.costs)
                    self.assertIsNone(detail.prerequisite_record)
                    self.assertIsNone(detail.original_time_text)
                    self.assertIsNone(detail.actual_time_text)
                    self.assertIsNone(detail.premium_button_bounds)
                    self.assertIsNone(detail.premium_gem_cost)
                    self.assertEqual(ResearchQueueState.UNKNOWN, detail.queue_state)
                    self.assertIsNone(detail.queue_timer_text)
                    self.assertFalse(observation.has(START))
                    self.assertEqual(observation.frame_ref, detail.frame_ref)
                    self.assertEqual("research_tree_node_detail_max", detail.source_layout_id)
                    self.assertEqual((), observation.entries(ListEntryKind.RESEARCH))

    def test_independent_max_detail_holdout_keeps_its_own_identity(self) -> None:
        """A later native-size Infirmary frame resolves independently of the anchor source."""

        builder, perception = _production_components()
        image = _image("research_node_detail_max_infirmary_holdout_20260916.png")
        for observation in _observe(builder, perception, image, session_id="max-holdout"):
            self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
            self.assertEqual("research_tree_node_detail_max", observation.decision.layout_id)
            detail = observation.research_detail
            self.assertEqual(ResearchNodeId.INFIRMARY_CAP_I, detail.node_id)
            self.assertEqual((5, 5), (detail.current_level, detail.max_level))
            self.assertEqual(observation.frame_ref, detail.frame_ref)
            self.assertFalse(observation.has(START))
            self.assertEqual((), detail.costs)
            effects = " ".join(record.text for record in detail.effect_records)
            self.assertIn("+2,735", effects)
            self.assertIn("+10,000", effects)

    def test_max_detail_requires_both_independent_anchors(self) -> None:
        """An isolated Max banner or Research header never establishes a detail."""

        recognizer = load_visual_screen_recognizer()
        for box in ((23, 358, 57, 391), (187, 409, 349, 467)):
            image = _image("research_node_detail_max_20260916.png")
            image.paste((80, 80, 80), box)
            self.assertNotIn("research_tree_node_detail_max", recognizer.recognize(image).profile_ids)


if __name__ == "__main__":
    unittest.main()
