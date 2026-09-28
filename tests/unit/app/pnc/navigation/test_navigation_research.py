"""Navigation research tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import unittest

from pnc_automation.app.pnc.domain.action_requests import (
    KeyEventAction,
    SwipeAction,
    TapListEntryAction,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    RowRecognitionStatus,
    VisibleElement,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import ResearchNodeId, research_node_title
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.navigation.core_frames import Actuator, observation
from tests.support.pnc.navigation.core_recording import RecordingNavigationCore
from tests.support.pnc.navigation.core_research import (
    research_detail_frame,
    research_entry,
    research_tree_frame,
)


class ResearchNavigationCoreTests(RecordingNavigationCore, unittest.TestCase):
    """Prove research node open, scroll, and close through typed content proof."""


    def test_open_research_node_taps_unique_complete_row_once_for_matching_detail(self):
        """One qualified row tap followed by two stable matching detail frames."""

        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter((
            research_tree_frame((research_entry(ResearchNodeId.CONSTRUCTION_I),), captured_at=now),
            research_detail_frame(ResearchNodeId.CONSTRUCTION_I, captured_at=now + timedelta(seconds=1)),
            research_detail_frame(ResearchNodeId.CONSTRUCTION_I, captured_at=now + timedelta(seconds=2)),
        ))
        actuator = Actuator()
        result = self.make_core(actuator).open_research_node(
            "Construction I",
            ResearchCategory.DEVELOPMENT,
            observe_content=lambda _: next(frames),
        )

        self.assertIsNotNone(result.research_detail)
        self.assertEqual(ResearchNodeId.CONSTRUCTION_I, result.research_detail.node_id)
        self.assertEqual(1, len(actuator.actions))
        action = actuator.actions[0]
        self.assertIsInstance(action, TapListEntryAction)
        self.assertEqual("Construction I", action.title_text)
        self.assertEqual("category", action.metadata_key)
        self.assertEqual(ResearchCategory.DEVELOPMENT.value, action.metadata_value)

    def test_registered_categories_open_matching_detail_and_return_to_same_grid(self):
        """Each registered category keeps identity across one tap and one Back."""
        now = datetime(2026, 9, 16, tzinfo=UTC)
        for category, node in (
            (ResearchCategory.ECONOMY, ResearchNodeId.FOOD_OUTPUT_I),
            (ResearchCategory.MILITARY, ResearchNodeId.SIEGE_ATK_I),
            (ResearchCategory.FORTIFICATION, ResearchNodeId.WALL_DEF_I),
        ):
            with self.subTest(category=category):
                def grid(seconds):
                    return research_tree_frame(
                        (research_entry(node, category=category),), category=category,
                        captured_at=now + timedelta(seconds=seconds),
                    )
                def detail(seconds):
                    return research_detail_frame(node, captured_at=now + timedelta(seconds=seconds))
                frames = iter((grid(0), detail(1), detail(2), detail(3), grid(4), grid(5)))
                actuator = Actuator()
                core = self.make_core(actuator)
                opened = core.open_research_node(
                    research_node_title(node), category, observe_content=lambda _: next(frames),
                )
                self.assertEqual(node, opened.research_detail.node_id)
                core.close_research_detail(category=category, observe_content=lambda _: next(frames))
                self.assertEqual(2, len(actuator.actions))
                self.assertEqual(category.value, actuator.actions[0].metadata_value)
                self.assertIsInstance(actuator.actions[1], KeyEventAction)

    def test_cross_category_node_or_grid_sends_no_tap(self):
        """A valid label in a foreign catalog or a foreign grid grants no action."""
        for title, expected in (("Construction I", ValueError), ("Food Output I", RuntimeError)):
            with self.subTest(title=title):
                actuator = Actuator()
                with self.assertRaises(expected):
                    self.make_core(actuator).open_research_node(
                        title, ResearchCategory.ECONOMY,
                        observe_content=lambda _: research_tree_frame((research_entry(ResearchNodeId.FOOD_OUTPUT_I),)),
                    )
                self.assertEqual([], actuator.actions)

    def test_detail_close_rejects_a_different_category_without_repeating_back(self):
        """A fresh foreign grid cannot satisfy the requested category return."""
        now = datetime(2026, 9, 16, tzinfo=UTC)
        frames = iter((
            research_detail_frame(ResearchNodeId.FOOD_OUTPUT_I, captured_at=now),
            *(research_tree_frame(category=ResearchCategory.MILITARY,
                                  captured_at=now + timedelta(seconds=i)) for i in range(1, 5)),
        ))
        actuator = Actuator()
        with self.assertRaises(RuntimeError):
            self.make_core(actuator).close_research_detail(
                category=ResearchCategory.ECONOMY, observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], KeyEventAction)

    def test_category_entry_uses_measured_control_and_matching_fresh_layout(self):
        """An Institute entry alone cannot confirm arrival in another category."""
        now = datetime(2026, 9, 16, tzinfo=UTC)
        selector = UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON
        source = replace(
            observation(ScreenType.PNC_INSTITUTE), captured_at=now,
            visible_elements={selector: VisibleElement(selector, Bounds(40, 300, 130, 60), 1.0)},
        )
        frames = iter((source, *(
            research_tree_frame(category=ResearchCategory.ECONOMY, captured_at=now + timedelta(seconds=i))
            for i in (1, 2)
        )))
        actuator = Actuator()
        self.make_core(actuator).open_research_category(
            ResearchCategory.ECONOMY, observe_content=lambda _: next(frames),
        )
        self.assertEqual([selector], [action.selector_id for action in actuator.actions])
        actuator = Actuator()
        with self.assertRaises(RuntimeError):
            self.make_core(actuator).open_research_category(
                ResearchCategory.MILITARY, observe_content=lambda _: source,
            )
        self.assertEqual([], actuator.actions)

    def test_open_research_node_rejects_unqualified_sources_without_any_tap(self):
        """Missing, duplicated, unproved, or unreadable rows send no action."""

        node = ResearchNodeId.CONSTRUCTION_I
        cases = (
            ("unproved_grid", research_tree_frame((research_entry(node),), proved=False)),
            ("missing", research_tree_frame(())),
            (
                "ambiguous",
                research_tree_frame((research_entry(node), research_entry(node))),
            ),
            (
                "unreadable",
                research_tree_frame(
                    (research_entry(node, status=RowRecognitionStatus.UNREADABLE),)
                ),
            ),
            (
                "clipped",
                research_tree_frame(
                    (research_entry(node, status=RowRecognitionStatus.CLIPPED),)
                ),
            ),
        )
        for name, source in cases:
            with self.subTest(reason=name):
                actuator = Actuator()
                with self.assertRaises(RuntimeError):
                    self.make_core(actuator).open_research_node(
                        "Construction I",
                        ResearchCategory.DEVELOPMENT,
                        observe_content=lambda _: source,
                    )
                self.assertEqual(0, len(actuator.actions))

    def test_open_research_node_rejects_wrong_detail_without_replaying_tap(self):
        """A different node's detail never proves completion; no second tap."""

        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter((
            research_tree_frame((research_entry(ResearchNodeId.CONSTRUCTION_I),), captured_at=now),
            *(
                research_detail_frame(
                    ResearchNodeId.STORAGE_I,
                    captured_at=now + timedelta(seconds=index),
                )
                for index in range(1, 5)
            ),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            self.make_core(actuator).open_research_node(
                "Construction I",
                ResearchCategory.DEVELOPMENT,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))

    def test_open_research_node_rejects_stale_detail_without_replaying_tap(self):
        """A detail frame no newer than the source is a stale capture."""

        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter((
            research_tree_frame((research_entry(ResearchNodeId.CONSTRUCTION_I),), captured_at=now),
            research_detail_frame(ResearchNodeId.CONSTRUCTION_I, captured_at=now),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "stale capture"):
            self.make_core(actuator).open_research_node(
                "Construction I",
                ResearchCategory.DEVELOPMENT,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))

    def test_open_research_node_rejects_conflicting_detail_category(self):
        """A detail that names a different category cannot prove the selection."""

        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter((
            research_tree_frame((research_entry(ResearchNodeId.CONSTRUCTION_I),), captured_at=now),
            *(
                research_detail_frame(
                    ResearchNodeId.CONSTRUCTION_I,
                    category=ResearchCategory.ECONOMY,
                    captured_at=now + timedelta(seconds=index),
                )
                for index in range(1, 5)
            ),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            self.make_core(actuator).open_research_node(
                "Construction I",
                ResearchCategory.DEVELOPMENT,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))

    def test_scroll_research_tree_sends_one_qualified_swipe(self):
        """One reviewed gesture confirmed by two fresh proved tree frames."""

        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter((
            research_tree_frame(
                (research_entry(ResearchNodeId.CONSTRUCTION_I),), captured_at=now
            ),
            research_tree_frame(
                (research_entry(ResearchNodeId.INFIRMARY_CAP_I),),
                captured_at=now + timedelta(seconds=1),
            ),
            research_tree_frame(
                (research_entry(ResearchNodeId.INFIRMARY_CAP_I),),
                captured_at=now + timedelta(seconds=2),
            ),
        ))
        actuator = Actuator()
        result = self.make_core(actuator).scroll_research_tree(
            observe_content=lambda _: next(frames)
        )

        self.assertEqual(ScreenType.PNC_RESEARCH_TREE, result.screen_type)
        self.assertEqual(1, len(actuator.actions))
        action = actuator.actions[0]
        self.assertIsInstance(action, SwipeAction)
        self.assertEqual("replacement_scroll_research_tree", action.reason)

    def test_scroll_research_tree_without_proved_grid_sends_nothing(self):
        """A blocked or unproved source never receives the reviewed gesture."""

        for source in (
            research_tree_frame((research_entry(ResearchNodeId.CONSTRUCTION_I),), proved=False),
            research_tree_frame((research_entry(ResearchNodeId.CONSTRUCTION_I),), blocked=True),
            observation(ScreenType.PNC_HOME_CITY),
        ):
            with self.subTest(source=source.decision.effective_screen, blocked=source.blocking_popup):
                actuator = Actuator()
                with self.assertRaises(RuntimeError):
                    self.make_core(actuator).scroll_research_tree(
                        observe_content=lambda _: source
                    )
                self.assertEqual(0, len(actuator.actions))

    def test_scroll_research_tree_failed_confirmation_never_repeats_swipe(self):
        """Unchanged follow-up frames exhaust the budget after one gesture."""

        now = datetime(2026, 9, 12, tzinfo=UTC)
        source = research_tree_frame(
            (research_entry(ResearchNodeId.CONSTRUCTION_I),), captured_at=now
        )
        unknowns = tuple(observation(ScreenType.UNKNOWN) for _ in range(4))
        frames = iter((
            source,
            *(
                replace(frame, captured_at=now + timedelta(seconds=index))
                for index, frame in enumerate(unknowns, start=1)
            ),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            self.make_core(actuator).scroll_research_tree(
                observe_content=lambda _: next(frames)
            )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)

    def test_close_research_detail_sends_one_back_for_tree_return(self):
        """One Android Back from the proved detail confirmed by the fresh grid."""

        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter((
            research_detail_frame(ResearchNodeId.CONSTRUCTION_I, captured_at=now),
            research_tree_frame(
                (research_entry(ResearchNodeId.CONSTRUCTION_I),),
                captured_at=now + timedelta(seconds=1),
            ),
            research_tree_frame(
                (research_entry(ResearchNodeId.CONSTRUCTION_I),),
                captured_at=now + timedelta(seconds=2),
            ),
        ))
        actuator = Actuator()
        result = self.make_core(actuator).close_research_detail(
            observe_content=lambda _: next(frames)
        )

        self.assertEqual(ScreenType.PNC_RESEARCH_TREE, result.screen_type)
        self.assertEqual(1, len(actuator.actions))
        action = actuator.actions[0]
        self.assertIsInstance(action, KeyEventAction)
        self.assertEqual("KEYCODE_BACK", action.key_code)

    def test_max_level_detail_can_be_inspected_and_closed_without_start(self):
        """A fresh matching max panel completes the tap and allows only Back."""

        now = datetime(2026, 9, 16, tzinfo=UTC)
        node = ResearchNodeId.TROOP_LOAD_I
        tree = lambda seconds: research_tree_frame(
            (research_entry(node),), captured_at=now + timedelta(seconds=seconds),
        )
        detail = lambda seconds: research_detail_frame(
            node, max_level=True, start=False,
            captured_at=now + timedelta(seconds=seconds),
        )
        frames = iter((tree(0), detail(1), detail(2), detail(3), tree(4), tree(5)))
        actuator = Actuator()
        core = self.make_core(actuator)
        opened = core.open_research_node(
            title="Troop Load I", category=ResearchCategory.DEVELOPMENT,
            observe_content=lambda _: next(frames),
        )
        self.assertEqual(node, opened.research_detail.node_id)
        self.assertFalse(opened.has(UiElementId.PNC_RESEARCH_START_BUTTON))
        closed = core.close_research_detail(observe_content=lambda _: next(frames))
        self.assertEqual(ScreenType.PNC_RESEARCH_TREE, closed.screen_type)
        self.assertEqual(2, len(actuator.actions))
        self.assertIsInstance(actuator.actions[-1], KeyEventAction)
        self.assertEqual("KEYCODE_BACK", actuator.actions[-1].key_code)

    def test_close_research_detail_rejects_non_detail_sources_without_action(self):
        """A tree grid or blocked detail cannot trigger the Back gesture."""

        now = datetime(2026, 9, 12, tzinfo=UTC)
        for source in (
            research_tree_frame(
                (research_entry(ResearchNodeId.CONSTRUCTION_I),), captured_at=now
            ),
            research_detail_frame(
                ResearchNodeId.CONSTRUCTION_I, captured_at=now, blocked=True
            ),
            observation(ScreenType.PNC_HOME_CITY),
        ):
            with self.subTest(screen=source.screen_type, blocked=source.blocking_popup):
                actuator = Actuator()
                with self.assertRaises(RuntimeError):
                    self.make_core(actuator).close_research_detail(
                        observe_content=lambda _: source
                    )
                self.assertEqual(0, len(actuator.actions))
