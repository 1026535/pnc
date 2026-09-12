"""Offline integration-style tests for the per-castle Daily coordinator."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from dataclasses import replace
from pathlib import Path

from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyCapabilityPolicy,
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.automation.daily_maintenance.coordinator import DailyMaintenanceCoordinator
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
)
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.vision.image.models import Bounds


class DailyMaintenanceCoordinatorTests(unittest.TestCase):
    """Covers claim ordering, exclusions, resume, and bounded scrolling."""

    def setUp(self) -> None:
        """Builds one isolated checkpoint and enabled Arena target."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.castle = CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22)
        self.target = DailyMaintenanceTargetConfig(
            account_id="mega_old_acc",
            castle_ref="npc_2",
            castle=self.castle,
            capabilities=(
                DailyCapabilityPolicy(
                    quest_id=DailyQuestId.HERO_ARENA,
                    task_id=TaskId.HERO_ARENA,
                    max_mutations=3,
                ),
            ),
        )
        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-04",
            game_reset_id="2026-09-04T00",
            account_id="mega_old_acc",
            castle=self.castle,
        )

    def test_claims_before_executing_and_reopens_after_each_mutation(self) -> None:
        """Claims an excluded completed row before running an enabled Go row."""

        claim = _observation(_entry(DailyQuestId.UPGRADE_BUILDING, "claim"))
        arena = _observation(_entry(DailyQuestId.HERO_ARENA, "go"))
        bottom = _observation(_entry(DailyQuestId.HERO_ARENA, "completed", bottom=True))
        session = _FakeSession(observations=[claim, claim, arena, arena, bottom, bottom])
        events: list[str] = []
        coordinator = self._coordinator(
            session=session,
            claim_executor=_FakeClaimExecutor(events),
            capability_executor=_FakeCapabilityExecutor(events),
        )

        result = coordinator.run(target=self.target, checkpoint=self.checkpoint)

        self.assertEqual(["claim:upgrade_building", "execute:hero_arena"], events)
        self.assertIn(DailyQuestId.HERO_ARENA, result.checkpoint.completed_quest_ids)
        self.assertEqual(3, session.open_count)
        self.assertEqual(1, session.home_count)

    def test_never_executes_excluded_go_row(self) -> None:
        """Leaves excluded work untouched even when the game exposes Go."""

        excluded = _observation(_entry(DailyQuestId.UPGRADE_BUILDING, "go", bottom=True))
        session = _FakeSession(observations=[excluded, excluded])
        events: list[str] = []

        result = self._coordinator(
            session=session,
            claim_executor=_FakeClaimExecutor(events),
            capability_executor=_FakeCapabilityExecutor(events),
        ).run(target=self.target, checkpoint=self.checkpoint)

        self.assertEqual([], events)
        self.assertEqual((), result.outcomes)

    def test_completed_checkpoint_prevents_replay(self) -> None:
        """Does not execute an actionable row whose capability already committed."""

        checkpoint = self._store().mark_completed(self.checkpoint, DailyQuestId.HERO_ARENA)
        arena = _observation(_entry(DailyQuestId.HERO_ARENA, "go", bottom=True))
        session = _FakeSession(observations=[arena, arena])
        events: list[str] = []

        result = self._coordinator(
            session=session,
            claim_executor=_FakeClaimExecutor(events),
            capability_executor=_FakeCapabilityExecutor(events),
        ).run(target=self.target, checkpoint=checkpoint)

        self.assertEqual([], events)
        self.assertIn(DailyQuestId.HERO_ARENA, result.checkpoint.completed_quest_ids)

    def test_requires_two_unchanged_swipes_before_bottom_bounce(self) -> None:
        """Uses one adjusted retry before treating an unchanged viewport as exhausted."""

        requirement = _observation(_entry(DailyQuestId.HERO_ARENA, "requirement"))
        session = _FakeSession(observations=[requirement] * 6)

        result = self._coordinator(
            session=session,
            claim_executor=_FakeClaimExecutor([]),
            capability_executor=_FakeCapabilityExecutor([]),
        ).run(target=self.target, checkpoint=self.checkpoint)

        self.assertEqual([False, True], session.scroll_adjustments)
        self.assertEqual(2, result.scanned_viewports)

    def test_ambiguous_claim_halts_castle_without_replay(self) -> None:
        """Returns Home after one ambiguous mutation instead of selecting the row again."""

        claim = _observation(_entry(DailyQuestId.UPGRADE_BUILDING, "claim"))
        session = _FakeSession(observations=[claim, claim])
        events: list[str] = []

        result = self._coordinator(
            session=session,
            claim_executor=_FakeClaimExecutor(events, DailyTargetOutcomeStatus.PENDING_CLARIFICATION),
            capability_executor=_FakeCapabilityExecutor(events),
        ).run(target=self.target, checkpoint=self.checkpoint)

        self.assertEqual(["claim:upgrade_building"], events)
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, result.outcomes[0].status)
        self.assertEqual(1, session.home_count)

    def test_read_only_survey_reports_claim_rows_without_mutating(self) -> None:
        """Traverses and reports a Claim row without invoking either mutation executor."""

        claim = _observation(_entry(DailyQuestId.UPGRADE_BUILDING, "claim", bottom=True))
        session = _FakeSession(observations=[claim, claim])
        events: list[str] = []

        survey = self._coordinator(
            session=session,
            claim_executor=_FakeClaimExecutor(events),
            capability_executor=_FakeCapabilityExecutor(events),
        ).survey_read_only()

        self.assertEqual([], events)
        self.assertEqual(DailyQuestId.UPGRADE_BUILDING, survey.rows[0].quest_id)
        self.assertEqual(1, session.home_count)

    def test_dynamic_daily_frame_gets_one_bounded_settle_reread(self) -> None:
        """Accepts a settled third frame after one animation-induced geometry change."""

        first = _observation(_entry(DailyQuestId.HERO_ARENA, "requirement"))
        moving = replace(
            first,
            list_entries=(replace(first.list_entries[0], bounds=Bounds(9, 374, 518, 99)),),
        )
        session = _FakeSession(observations=[moving, first, first])
        viewport = self._coordinator(
            session=session,
            claim_executor=_FakeClaimExecutor([]),
            capability_executor=_FakeCapabilityExecutor([]),
        )._observe_stable_viewport(label_prefix="settle")

        self.assertAlmostEqual(372 / 960, viewport.rows[0].bounds.y)
        self.assertEqual(0, session.home_count)

    def test_waiting_cooldown_defers_one_capability_and_runs_another(self) -> None:
        """Keeps a Hero Hall cooldown pending while another enabled Daily row proceeds."""

        target = replace(
            self.target,
            capabilities=(
                DailyCapabilityPolicy(DailyQuestId.HERO_HALL, TaskId.HERO_HALL, 5),
                DailyCapabilityPolicy(DailyQuestId.HERO_ARENA, TaskId.HERO_ARENA, 3),
            ),
        )
        first = _observation(
            _entry(DailyQuestId.HERO_HALL, "go"),
            _entry(DailyQuestId.HERO_ARENA, "go"),
        )
        second = _observation(
            _entry(DailyQuestId.HERO_HALL, "go"),
            _entry(DailyQuestId.HERO_ARENA, "completed", bottom=True),
        )
        session = _FakeSession(observations=[first, first, first, first, second, second])
        events: list[str] = []
        result = self._coordinator(
            session=session,
            claim_executor=_FakeClaimExecutor(events),
            capability_executor=_FakeCapabilityExecutor(
                events,
                statuses={DailyQuestId.HERO_HALL: DailyTargetOutcomeStatus.WAITING_COOLDOWN},
            ),
        ).run(target=target, checkpoint=self.checkpoint)

        self.assertEqual(["execute:hero_hall", "execute:hero_arena"], events)
        self.assertNotIn(DailyQuestId.HERO_HALL, result.checkpoint.completed_quest_ids)
        self.assertIn(DailyQuestId.HERO_ARENA, result.checkpoint.completed_quest_ids)

    def _coordinator(self, *, session, claim_executor, capability_executor) -> DailyMaintenanceCoordinator:
        """Builds the coordinator with an isolated atomic journal."""

        return DailyMaintenanceCoordinator(
            session=session,
            claim_executor=claim_executor,
            capability_executor=capability_executor,
            journal_store=self._store(),
            catalog=DailyQuestCatalog(),
        )

    def _store(self) -> DailyRunJournalStore:
        """Returns the test's isolated journal store."""

        return DailyRunJournalStore(Path(self.temporary_directory.name))


@dataclass(slots=True)
class _FakeSession:
    """Supplies deterministic observation frames and records navigation calls."""

    observations: list[Observation]
    open_count: int = 0
    home_count: int = 0
    scroll_adjustments: list[bool] = field(default_factory=list)

    def open_daily_quest(self) -> None:
        """Records one open or reopen operation."""

        self.open_count += 1

    def observe_daily_quest(self, label: str) -> Observation:
        """Returns the next deterministic frame."""

        del label
        if not self.observations:
            raise AssertionError("Fake Daily session exhausted its observations.")
        return self.observations.pop(0)

    def scroll_daily_quest(self, *, adjusted: bool) -> None:
        """Records normal and adjusted scroll attempts."""

        self.scroll_adjustments.append(adjusted)

    def return_to_home(self) -> None:
        """Records the final safe-root return."""

        self.home_count += 1


@dataclass(slots=True)
class _FakeClaimExecutor:
    """Records claim ordering and returns a successful observed outcome."""

    events: list[str]
    status: DailyTargetOutcomeStatus = DailyTargetOutcomeStatus.SUCCESS

    def claim(self, *, row, checkpoint):
        """Returns one successful fake claim."""

        self.events.append(f"claim:{row.quest_id.value}")
        return checkpoint, DailyTargetOutcome(
            quest_id=row.quest_id,
            status=self.status,
            message="claimed",
        )


@dataclass(slots=True)
class _FakeCapabilityExecutor:
    """Records capability ordering and returns a successful observed outcome."""

    events: list[str]
    statuses: dict[DailyQuestId, DailyTargetOutcomeStatus] = field(default_factory=dict)

    def execute(self, *, row, target, checkpoint):
        """Returns one successful fake capability execution."""

        del target
        self.events.append(f"execute:{row.quest_id.value}")
        return checkpoint, DailyTargetOutcome(
            quest_id=row.quest_id,
            status=self.statuses.get(row.quest_id, DailyTargetOutcomeStatus.SUCCESS),
            message="executed",
        )


def _observation(*entries: DetectedListEntry) -> Observation:
    """Builds one typed Daily Quest observation."""

    return Observation(
        screen_type=ScreenType.PNC_QUEST_DAILY,
        visible_elements={},
        list_entries=entries,
        image_size=(540, 960),
    )


def _entry(quest_id: DailyQuestId, state: str, *, bottom: bool = False) -> DetectedListEntry:
    """Builds one visually sourced Daily row fixture."""

    return DetectedListEntry(
        kind=ListEntryKind.DAILY_QUEST,
        bounds=Bounds(9, 372, 518, 99),
        title_text=quest_id.value,
        action_point=(454, 421),
        metadata={
            "quest_id": quest_id.value,
            "row_state": state,
            "coordinate_provenance": "visual_geometry",
            "observation_fingerprint": f"fingerprint-{quest_id.value}-{state}",
            "progress_current": 0,
            "progress_required": 1,
            "bottom_marker": bottom,
        },
    )


if __name__ == "__main__":
    unittest.main()
