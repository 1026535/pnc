"""Portable real-capture acceptance coverage for the typed Research model.

Runs the production ObservationBuilder and NavigationPerception stacks with
the shared RapidOCR backend over the tracked Research fixtures and the
sanitized scrolled tour capture. These assertions pin the V04 contracts the
lead reviewed: typed tree/detail/queue facts, honest row geometry, and
frame-scoped provenance on both publication paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import ResearchNodeId, ResearchQueueState
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.shared_rapid_ocr_service import _shared_rapid_ocr_service


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
START = UiElementId.PNC_RESEARCH_START_BUTTON


def _image(name: str, *, subdir: str = "") -> Image.Image:
    """Load one tracked, sanitized fixture into an independent RGB image."""

    root = FIXTURES / subdir if subdir else FIXTURES
    with Image.open(root / name) as source:
        return source.convert("RGB")


def _capture(image: Image.Image, *, session_id: str) -> CapturedScreenshot:
    """Attach canonical frame provenance to one fixture capture."""

    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _production_components() -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire both production publication paths to the shared RapidOCR backend."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        ocr_service=_shared_rapid_ocr_service(),
        ocr_backend_revision="research-acceptance",
    )
    perception = NavigationPerception(
        builder.visual_recognizer,
        builder.enricher,
        builder.screen_classifier,
        builder.create_ocr_context,
    )
    return builder, perception


def _observe(
    builder: ObservationBuilder,
    perception: NavigationPerception,
    image: Image.Image,
    *,
    session_id: str,
) -> tuple[Observation, Observation]:
    """Publish one fixture capture through both production paths."""

    return (
        builder.build(
            _capture(image, session_id=f"builder:{session_id}"),
            request=ObservationRequest.full_runtime_default(),
        ),
        perception.build(
            _capture(image, session_id=f"perception:{session_id}"),
            include_content=True,
        ),
    )


class ResearchCapturedAcceptanceTests(unittest.TestCase):
    """Pin the reviewed V04 publication contracts on qualified captures."""

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
                # The partial bottom tile keeps its honest clipped status.
                clipped = entries[5]
                self.assertEqual(RowRecognitionStatus.CLIPPED, clipped.row_status)
                self.assertIsNone(clipped.action_point)
                self.assertIsNone(clipped.action_bounds)
                self.assertIsNotNone(clipped.research_facts)
                self.assertIsNone(clipped.research_facts.node_id)
                # Tree captures carry no detail or queue facts.
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
                # Top two tiles cross the fixed header/viewport edge: clipped,
                # no action geometry, and no level/lock reads attempted.
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
                self.assertEqual(6, detail.premium_gem_cost)
                self.assertIsNotNone(detail.premium_button_bounds)
                self.assertEqual(ResearchQueueState.UNKNOWN, detail.queue_state)
                self.assertIsNone(detail.queue_timer_text)
                # Typed provenance binds to the current frame on both paths.
                self.assertEqual(observation.frame_ref, detail.frame_ref)
                self.assertEqual(ScreenType.PNC_RESEARCH_TREE, detail.source_screen)
                self.assertEqual("research_tree_node_detail", detail.source_layout_id)
                # Detail captures carry no tree rows or queue facts.
                self.assertEqual((), observation.entries(ListEntryKind.RESEARCH))
                self.assertEqual((), observation.research_queue_rows)
                # The measured Start control is template proof for mutation priming.
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

    def test_queue_capture_publishes_typed_idle_row_with_provenance(self) -> None:
        """The queue surface resolves its measured row and frame-scoped fields."""

        builder, perception = _production_components()
        image = _image("research_queue_core.png")

        for observation in _observe(builder, perception, image, session_id="queue"):
            with self.subTest(path=type(observation).__name__):
                self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_QUEUE)
                self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
                self.assertEqual(observation.decision.layout_id, "research_queue")
                rows = observation.research_queue_rows
                self.assertEqual(1, len(rows))
                row = rows[0]
                self.assertEqual("1stResearchQueue", row.title_text)
                self.assertEqual(ResearchQueueState.IDLE, row.state)
                self.assertIsNone(row.timer_text)
                self.assertEqual(observation.frame_ref, row.frame_ref)
                self.assertEqual(ScreenType.PNC_RESEARCH_QUEUE, row.source_screen)
                self.assertEqual("research_queue", row.source_layout_id)
                self.assertIsNone(observation.research_detail)
                self.assertEqual((), observation.entries(ListEntryKind.RESEARCH))

    def test_max_detail_reads_observed_levels_and_effects_without_actions(self) -> None:
        """The live max-level panel is readable at both sizes and never primes Start."""

        builder, perception = _production_components()
        source = _image("research_node_detail_max_20260916.png")
        for size in ((540, 960), (900, 1600)):
            for observation in _observe(
                builder, perception, source.resize(size), session_id=f"max-detail:{size}",
            ):
                with self.subTest(size=size, frame=observation.frame_ref):
                    self.assertEqual(ScreenType.PNC_RESEARCH_TREE, observation.screen_type)
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

    def test_fresh_frames_carry_no_prior_research_facts(self) -> None:
        """Detail and queue facts never survive onto a later tree or unknown frame."""

        builder, perception = _production_components()
        _observe(builder, perception, _image("research_node_detail.png"), session_id="prior-detail")

        tree_builder, tree_perception = _observe(
            builder, perception, _image("research_tree_development.png"), session_id="fresh-tree"
        )
        for observation in (tree_builder, tree_perception):
            self.assertIsNone(observation.research_detail)
            self.assertEqual((), observation.research_queue_rows)
            self.assertEqual(6, len(observation.entries(ListEntryKind.RESEARCH)))

        unknown_builder, unknown_perception = _observe(
            builder,
            perception,
            Image.new("RGB", (540, 960), (80, 80, 80)),
            session_id="unknown-frame",
        )
        for observation in (unknown_builder, unknown_perception):
            self.assertEqual(ScreenType.UNKNOWN, observation.screen_type)
            self.assertIsNone(observation.research_detail)
            self.assertEqual((), observation.research_queue_rows)
            self.assertEqual((), observation.entries(ListEntryKind.RESEARCH))


if __name__ == "__main__":
    unittest.main()
