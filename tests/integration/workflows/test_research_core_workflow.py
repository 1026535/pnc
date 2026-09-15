"""Focused offline coverage for the typed Development research workflow."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import unittest

from pnc_automation.app.automation.engine.core_workflow import WorkflowEffect
from pnc_automation.app.automation.research import (
    ResearchDisposition,
    ResearchResult,
    ResearchWorkflow,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory, ResearchPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import ScriptValidationError, TaskVerificationError
from tests.support.pnc.observations import make_observation


class ResearchCoreWorkflowTests(unittest.TestCase):
    """Proves exact Development selection and one delegated mutation call."""

    def setUp(self) -> None:
        """Build a checkpoint and reviewed-shaped fake observations."""

        castle = CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22)
        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-12",
            game_reset_id="2026-09-12T00",
            account_id="account",
            castle=castle,
        )

    def test_valid_development_row_starts_once_and_returns_typed_result(self) -> None:
        """Uses the real workflow selection path and delegates exactly one authorized Start."""

        context = _FakeResearchContext(_tree(_complete_entry("Construction I")))
        workflow = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        )

        result = workflow.execute(context)

        self.assertIsInstance(result, ResearchResult)
        self.assertEqual(ResearchDisposition.STARTED, result.disposition)
        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, result.outcome.status)
        self.assertEqual("Construction I", result.node_title)
        self.assertEqual(
            [
                ("open_building", HomeCityObjectId.INSTITUTE),
                ("navigate", ScreenType.PNC_RESEARCH_TREE),
                ("observe", ScreenType.PNC_RESEARCH_TREE),
                ("open_node", "Construction I", ResearchCategory.DEVELOPMENT),
                ("start", self.checkpoint),
            ],
            context.calls,
        )

    def test_max_nodes_are_skipped_before_one_bounded_scroll_selects_progression(self) -> None:
        """Uses node-local progress and never opens a completed Development node."""

        context = _FakeResearchContext(
            (
                _tree(_max_entry("Construction I"), _max_entry("Research Speed I")),
                _tree(_complete_entry("Troop Load I", current=1, limit=5)),
            )
        )

        result = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        ).execute(context)

        self.assertEqual(ResearchDisposition.STARTED, result.disposition)
        self.assertEqual("Troop Load I", result.node_title)
        self.assertEqual(1, context.scroll_calls)
        self.assertNotIn(
            ("open_node", "Construction I", ResearchCategory.DEVELOPMENT),
            context.calls,
        )

    def test_incomplete_locked_node_is_not_opened_or_started(self) -> None:
        """A client prerequisite badge withholds the node before detail navigation."""

        context = _FakeResearchContext(_tree(_locked_entry("Infirmary Cap II")))

        result = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        ).execute(context)

        self.assertEqual(ResearchDisposition.NO_VISIBLE_SUPPORTED_NODE, result.disposition)
        self.assertEqual(0, context.open_node_calls)
        self.assertEqual(0, context.start_calls)

    def test_empty_or_unsupported_viewport_returns_no_visible_disposition(self) -> None:
        """Does not infer a free or eligible target from an empty or unsupported tree."""

        context = _FakeResearchContext(
            _tree(
                _complete_entry("Economy I", category=ResearchCategory.ECONOMY),
            )
        )
        result = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        ).execute(context)

        self.assertEqual(ResearchDisposition.NO_VISIBLE_SUPPORTED_NODE, result.disposition)
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, result.outcome.status)
        self.assertIsNone(result.outcome.skip_reason)
        self.assertEqual(0, context.start_calls)

    def test_policy_without_development_is_rejected_before_actions(self) -> None:
        """Rejects unsupported categories at construction instead of silently choosing another route."""

        for priority in (
            (ResearchCategory.ECONOMY,),
            (ResearchCategory.DEVELOPMENT, ResearchCategory.ECONOMY),
        ):
            with self.subTest(priority=priority), self.assertRaisesRegex(
                ValueError, "exact Development-only policy"
            ):
                ResearchWorkflow(
                    policy=ResearchPolicy(priority=priority),
                    checkpoint=self.checkpoint,
                )

    def test_duplicate_development_node_is_denied_before_research_start(self) -> None:
        """Retains fail-closed duplicate-title handling before any node is opened."""

        entries = (_complete_entry("Construction I"), _complete_entry("Construction I"))
        context = _FakeResearchContext(_tree(*entries))
        workflow = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        )
        with self.assertRaises(TaskVerificationError):
            workflow.execute(context)
        self.assertEqual(0, context.open_node_calls)
        self.assertEqual(0, context.start_calls)

    def test_bad_geometry_is_skipped_for_a_later_complete_peer(self) -> None:
        """Skips a clipped row and inspects the next complete eligible Development row."""

        context = _FakeResearchContext(
            _tree(_clipped_entry("Construction I"), _complete_entry("Research Speed I"))
        )
        result = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        ).execute(context)

        self.assertEqual(ResearchDisposition.STARTED, result.disposition)
        self.assertEqual("Research Speed I", result.node_title)
        self.assertEqual(1, context.open_node_calls)
        self.assertEqual(1, context.start_calls)

    def test_invalid_action_geometry_is_skipped_for_a_later_complete_peer(self) -> None:
        """Skips an unreadable row with unusable action geometry."""

        invalid = _complete_entry("Construction I")
        invalid = replace(
            invalid,
            action_point=None,
            action_bounds=None,
            row_status=RowRecognitionStatus.UNREADABLE,
        )
        context = _FakeResearchContext(
            _tree(invalid, _complete_entry("Research Speed I"))
        )
        result = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        ).execute(context)

        self.assertEqual(ResearchDisposition.STARTED, result.disposition)
        self.assertEqual("Research Speed I", result.node_title)
        self.assertEqual(1, context.open_node_calls)
        self.assertEqual(1, context.start_calls)

    def test_only_bad_geometry_returns_no_visible_disposition(self) -> None:
        """Leaves the mutation budget untouched when every eligible row is unreadable."""

        context = _FakeResearchContext(_tree(_clipped_entry("Construction I")))
        result = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        ).execute(context)

        self.assertEqual(ResearchDisposition.NO_VISIBLE_SUPPORTED_NODE, result.disposition)
        self.assertEqual(0, context.open_node_calls)
        self.assertEqual(0, context.start_calls)

    def test_start_failure_propagates_without_replay(self) -> None:
        """Leaves an ambiguous or failed mutation result to the boundary without replaying Start."""

        context = _FakeResearchContext(
            _tree(_complete_entry("Construction I")),
            start_error=RuntimeError("research receipt ambiguous"),
        )
        workflow = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        )

        with self.assertRaisesRegex(RuntimeError, "receipt ambiguous"):
            workflow.execute(context)
        self.assertEqual(1, context.start_calls)

    def test_unfunded_detail_is_closed_before_a_funded_peer_starts(self) -> None:
        """Inspects candidate resources without creating an intent for the short node."""

        context = _FakeResearchContext(
            _tree(
                _complete_entry("Troop Load II"),
                _complete_entry("Storage II"),
            ),
            detail_resources={"Troop Load II": False, "Storage II": True},
        )

        result = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        ).execute(context)

        self.assertEqual(ResearchDisposition.STARTED, result.disposition)
        self.assertEqual("Storage II", result.node_title)
        self.assertEqual(2, context.open_node_calls)
        self.assertEqual(1, context.close_detail_calls)
        self.assertEqual(1, context.start_calls)

    def test_all_unfunded_details_return_pending_without_start(self) -> None:
        """Exhausts bounded safe candidates while retaining an unconsumed mutation budget."""

        context = _FakeResearchContext(
            _tree(
                _complete_entry("Troop Load II"),
                _complete_entry("Storage II"),
            ),
            detail_resources={"Troop Load II": False, "Storage II": None},
        )

        result = ResearchWorkflow(
            policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
            checkpoint=self.checkpoint,
        ).execute(context)

        self.assertEqual(ResearchDisposition.PENDING_CLARIFICATION, result.disposition)
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, result.outcome.status)
        self.assertEqual(2, context.open_node_calls)
        self.assertEqual(2, context.close_detail_calls)
        self.assertEqual(0, context.start_calls)

    def test_opt_in_selects_one_unfunded_detail_for_bag_confirmation(self) -> None:
        """Carries the explicit Bag-resource opt-in to the mutation boundary."""

        context = _FakeResearchContext(
            _tree(_complete_entry("Construction II")),
            detail_resources={"Construction II": False},
        )

        result = ResearchWorkflow(
            policy=ResearchPolicy(
                priority=(ResearchCategory.DEVELOPMENT,),
                confirm_resource_shortfall_from_bag=True,
            ),
            checkpoint=self.checkpoint,
        ).execute(context)

        self.assertEqual(ResearchDisposition.STARTED, result.disposition)
        self.assertEqual("Construction II", result.node_title)
        self.assertEqual([True], context.confirm_resource_shortfall_flags)

    def test_research_policy_parses_strict_bag_confirmation_opt_in(self) -> None:
        """Defaults the spending branch off and rejects non-boolean authored values."""

        default = ResearchPolicy.from_params({"priority": ["development"]})
        enabled = ResearchPolicy.from_params(
            {
                "priority": ["development"],
                "confirm_resource_shortfall_from_bag": True,
            }
        )

        self.assertFalse(default.confirm_resource_shortfall_from_bag)
        self.assertTrue(enabled.confirm_resource_shortfall_from_bag)
        with self.assertRaisesRegex(ScriptValidationError, "to be a boolean"):
            ResearchPolicy.from_params(
                {
                    "priority": ["development"],
                    "confirm_resource_shortfall_from_bag": "true",
                }
            )


@dataclass
class _FakeResearchContext:
    """Supplies only the typed seams owned by the replacement core."""

    tree: Observation | tuple[Observation, ...]
    start_error: Exception | None = None
    detail_resources: dict[str, bool | None] | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.open_node_calls = 0
        self.start_calls = 0
        self.scroll_calls = 0
        self.close_detail_calls = 0
        self.confirm_resource_shortfall_flags: list[bool] = []
        self._trees = self.tree if isinstance(self.tree, tuple) else (self.tree,)
        self._tree_index = 0

    def open_building(self, target: HomeCityObjectId) -> Observation:
        """Records the typed Institute route."""

        self.calls.append(("open_building", target))
        return make_observation(ScreenType.PNC_INSTITUTE)

    def navigate(self, target: ScreenType) -> Observation:
        """Records the reviewed Development tree edge."""

        self.calls.append(("navigate", target))
        return make_observation(target)

    def observe_content(self, *, expected_screen: ScreenType) -> Observation:
        """Returns one fresh typed research tree."""

        self.calls.append(("observe", expected_screen))
        return self._trees[self._tree_index]

    def scroll_research_tree(self) -> Observation:
        """Advance one bounded fake Development viewport."""

        self.scroll_calls += 1
        self.calls.append(("scroll_research_tree",))
        self._tree_index = min(self._tree_index + 1, len(self._trees) - 1)
        return self._trees[self._tree_index]

    def open_research_node(self, *, title: str, category: ResearchCategory) -> Observation:
        """Records exact node reacquisition and returns an idle detail proof."""

        self.open_node_calls += 1
        self.calls.append(("open_node", title, category))
        sufficient = True if self.detail_resources is None else self.detail_resources.get(title)
        return make_observation(
            ScreenType.PNC_RESEARCH_TREE,
            artifact_path=Path("detail.png"),
            research_start_resources_sufficient=sufficient,
            research_start_queue_available=True,
        )

    def close_research_detail(self) -> Observation:
        """Return the current fake viewport after one non-mutating detail Back."""

        self.close_detail_calls += 1
        self.calls.append(("close_research_detail",))
        return self._trees[self._tree_index]

    def start_research(
        self,
        checkpoint: DailyTaskCheckpoint,
        *,
        confirm_resource_shortfall_from_bag: bool = False,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Records one authorized mutation request and propagates boundary failures."""

        self.start_calls += 1
        self.confirm_resource_shortfall_flags.append(
            confirm_resource_shortfall_from_bag
        )
        self.calls.append(("start", checkpoint))
        if self.start_error is not None:
            raise self.start_error
        return checkpoint, DailyTargetOutcome(
            quest_id=DailyQuestId.UPGRADE_RESEARCH,
            status=DailyTargetOutcomeStatus.SUCCESS,
            message="research started",
        )


def _tree(*entries: DetectedListEntry) -> Observation:
    """Build one typed Development tree observation."""

    return make_observation(ScreenType.PNC_RESEARCH_TREE, list_entries=entries, image_size=(540, 960))


def _complete_entry(
    title: str,
    *,
    category: ResearchCategory = ResearchCategory.DEVELOPMENT,
    current: int = 1,
    limit: int = 5,
) -> DetectedListEntry:
    """Build one complete, observed research row with bounded action geometry."""

    bounds = Bounds(20, 80, 180, 90)
    action_bounds = Bounds(85, 90, 50, 45)
    return DetectedListEntry(
        kind=ListEntryKind.RESEARCH,
        bounds=bounds,
        title_text=title,
        action_point=action_bounds.center(),
        action_bounds=action_bounds,
        metadata={
            "category": category.value,
            "research_access_state": "available",
            "research_progress_state": "incomplete",
            "research_progress_current": current,
            "research_progress_limit": limit,
        },
        row_status=RowRecognitionStatus.COMPLETE,
    )


def _max_entry(title: str) -> DetectedListEntry:
    """Build one fully observed node whose progression is complete."""

    entry = _complete_entry(title)
    return DetectedListEntry(
        kind=entry.kind,
        bounds=entry.bounds,
        title_text=entry.title_text,
        action_point=entry.action_point,
        action_bounds=entry.action_bounds,
        metadata={
            "category": "development",
            "research_access_state": "available",
            "research_progress_state": "max",
        },
        row_status=entry.row_status,
    )


def _locked_entry(title: str) -> DetectedListEntry:
    """Build one incomplete node whose client prerequisite badge is visible."""

    entry = _complete_entry(title)
    return DetectedListEntry(
        kind=entry.kind,
        bounds=entry.bounds,
        title_text=entry.title_text,
        action_point=entry.action_point,
        action_bounds=entry.action_bounds,
        metadata={**entry.metadata, "research_access_state": "locked"},
        row_status=entry.row_status,
    )


def _clipped_entry(title: str) -> DetectedListEntry:
    """Build one Development row whose producer withheld action geometry."""

    return DetectedListEntry(
        kind=ListEntryKind.RESEARCH,
        bounds=Bounds(20, 80, 180, 90),
        title_text=title,
        metadata={
            "category": ResearchCategory.DEVELOPMENT.value,
            "research_access_state": "available",
            "research_progress_state": "incomplete",
        },
        row_status=RowRecognitionStatus.CLIPPED,
    )


if __name__ == "__main__":
    unittest.main()
