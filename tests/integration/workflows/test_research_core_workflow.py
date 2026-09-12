"""Focused offline coverage for the typed Development research workflow."""

from __future__ import annotations

from dataclasses import dataclass
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
from pnc_automation.core.errors import TaskVerificationError
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

    def test_ambiguous_or_clipped_node_is_denied_before_research_start(self) -> None:
        """Refuses incomplete or duplicate Development geometry without opening or starting a node."""

        for entries in (
            (_complete_entry("Construction I"), _complete_entry("Construction II")),
            (_clipped_entry("Construction I"),),
        ):
            with self.subTest(entries=entries):
                context = _FakeResearchContext(_tree(*entries))
                workflow = ResearchWorkflow(
                    policy=ResearchPolicy(priority=(ResearchCategory.DEVELOPMENT,)),
                    checkpoint=self.checkpoint,
                )
                with self.assertRaises(TaskVerificationError):
                    workflow.execute(context)
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


@dataclass
class _FakeResearchContext:
    """Supplies only the typed seams owned by the replacement core."""

    tree: Observation
    start_error: Exception | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.open_node_calls = 0
        self.start_calls = 0

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
        return self.tree

    def open_research_node(self, *, title: str, category: ResearchCategory) -> Observation:
        """Records exact node reacquisition and returns an idle detail proof."""

        self.open_node_calls += 1
        self.calls.append(("open_node", title, category))
        return make_observation(ScreenType.PNC_RESEARCH_TREE, artifact_path=Path("detail.png"))

    def start_research(
        self, checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Records one authorized mutation request and propagates boundary failures."""

        self.start_calls += 1
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


def _complete_entry(title: str, *, category: ResearchCategory = ResearchCategory.DEVELOPMENT) -> DetectedListEntry:
    """Build one complete, observed research row with bounded action geometry."""

    bounds = Bounds(20, 80, 180, 90)
    action_bounds = Bounds(85, 90, 50, 45)
    return DetectedListEntry(
        kind=ListEntryKind.RESEARCH,
        bounds=bounds,
        title_text=title,
        action_point=action_bounds.center(),
        action_bounds=action_bounds,
        metadata={"category": category.value},
        row_status=RowRecognitionStatus.COMPLETE,
    )


def _clipped_entry(title: str) -> DetectedListEntry:
    """Build one Development row whose producer withheld action geometry."""

    return DetectedListEntry(
        kind=ListEntryKind.RESEARCH,
        bounds=Bounds(20, 80, 180, 90),
        title_text=title,
        metadata={"category": ResearchCategory.DEVELOPMENT.value},
        row_status=RowRecognitionStatus.CLIPPED,
    )


if __name__ == "__main__":
    unittest.main()
