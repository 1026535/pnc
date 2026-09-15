"""Focused offline tests for the core Daily maintenance adapter."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.automation.daily_maintenance.core_daily_maintenance import (
    CoreDailyMaintenanceWorkflow,
)
from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.engine.core_workflow import WorkflowContext, WorkflowEffect
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    MutationAcknowledgement,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.vision.image.models import Bounds
from tests.support.pnc.observations import make_observation


class CoreDailyMaintenanceWorkflowTests(unittest.TestCase):
    """Proves the core adapter preserves coordinator traversal and claim semantics."""

    def setUp(self) -> None:
        """Builds one claim-only target and durable test journal."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.castle = CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22)
        self.target = DailyMaintenanceTargetConfig(
            account_id="mega_old_acc",
            castle_ref="npc_2",
            castle=self.castle,
            capabilities=(),
        )
        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-04",
            game_reset_id="2026-09-04T00",
            account_id="mega_old_acc",
            castle=self.castle,
        )
        self.scope = CoreMutationBoundary(
            target=self.target,
            boundary=DailyRunBoundary(date(2026, 9, 4), self.checkpoint.game_reset_id),
            authorizer=DailyMutationAuthorizer((MutationAcknowledgement(
                self.target.account_id, self.target.castle_ref, DailyQuestId.CLAIM_COMPLETED,
                date(2026, 9, 4), self.target.max_claims, 0,
            ),)),
            journal_store=self._journal_store(),
        )

    def test_real_coordinator_traverses_viewports_and_reopens_after_claim(self) -> None:
        """Claims a row found after scrolling, then settles on the reordered final viewport."""

        first = _observation(_entry(DailyQuestId.HERO_ARENA, "requirement"))
        claim = _observation(_entry(DailyQuestId.UPGRADE_BUILDING, "claim", bottom=True))
        final = _observation(_entry(DailyQuestId.UPGRADE_BUILDING, "completed", bottom=True))
        context = _FakeCoreContext(self.scope, [first, first, claim, claim, final, final])

        result = self._workflow().execute(context)

        self.assertEqual(3, result.scanned_viewports)
        self.assertEqual([False], context.scroll_adjustments)
        self.assertEqual([DailyQuestId.UPGRADE_BUILDING], context.claimed_rows)
        self.assertEqual(
            [ScreenType.PNC_QUEST_DAILY, ScreenType.PNC_QUEST_DAILY, ScreenType.PNC_HOME_CITY],
            context.navigations,
        )
        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, result.outcomes[0].status)

    def test_ambiguous_claim_returns_home_without_replay(self) -> None:
        """Stops on one pending claim outcome and never reopens or claims the row again."""

        claim = _observation(_entry(DailyQuestId.UPGRADE_BUILDING, "claim", bottom=True))
        context = _FakeCoreContext(self.scope, [claim, claim], claim_status=DailyTargetOutcomeStatus.PENDING_CLARIFICATION)

        result = self._workflow().execute(context)

        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, result.outcomes[0].status)
        self.assertEqual([DailyQuestId.UPGRADE_BUILDING], context.claimed_rows)
        self.assertEqual([ScreenType.PNC_QUEST_DAILY, ScreenType.PNC_HOME_CITY], context.navigations)

    def test_claim_failure_propagates_without_home_recovery_or_replay(self) -> None:
        """Leaves a failed claim visible to the runner so it cannot replay or hide the error."""

        claim = _observation(_entry(DailyQuestId.UPGRADE_BUILDING, "claim", bottom=True))
        context = _FakeCoreContext(self.scope, [claim, claim], claim_error=RuntimeError("claim verification failed"))

        with self.assertRaisesRegex(RuntimeError, "claim verification failed"):
            self._workflow().execute(context)

        self.assertEqual([DailyQuestId.UPGRADE_BUILDING], context.claimed_rows)
        self.assertEqual([ScreenType.PNC_QUEST_DAILY], context.navigations)

    def test_read_only_context_cannot_run_a_claim_sweep(self) -> None:
        """Even a sweep without claims must use its authorized mutation boundary."""

        context = _FakeCoreContext(self.scope, [])
        context._effect = WorkflowEffect.READ_ONLY
        with self.assertRaises(PermissionError):
            self._workflow().execute(context)
        self.assertEqual([], context.navigations)

    def _workflow(self) -> CoreDailyMaintenanceWorkflow:
        """Builds the workflow while keeping coordinator execution real."""

        return CoreDailyMaintenanceWorkflow(checkpoint=self.checkpoint)

    def _journal_store(self) -> DailyRunJournalStore:
        """Returns the isolated journal store for one test."""

        return DailyRunJournalStore(Path(self.temporary_directory.name))


class _FakeCoreContext(WorkflowContext):
    """Supplies typed core seam behavior while leaving the real coordinator in charge."""

    def __init__(
        self,
        boundary: CoreMutationBoundary,
        observations: list[Observation],
        *,
        claim_status: DailyTargetOutcomeStatus = DailyTargetOutcomeStatus.SUCCESS,
        claim_error: Exception | None = None,
    ) -> None:
        self._effect = WorkflowEffect.RESOURCE_CHANGING
        self._mutation_boundary = boundary
        self.observations = observations
        self.claim_status = claim_status
        self.claim_error = claim_error
        self.navigations: list[ScreenType] = []
        self.scroll_adjustments: list[bool] = []
        self.claimed_rows: list[DailyQuestId] = []

    def navigate(self, target: ScreenType) -> Observation:
        """Records typed navigation and returns a fresh synthetic endpoint."""

        self.navigations.append(target)
        return _observation()

    def observe_content(self, *, expected_screen: ScreenType) -> Observation:
        """Returns the next deterministic content observation."""

        if expected_screen != ScreenType.PNC_QUEST_DAILY:
            raise AssertionError(f"unexpected expected screen: {expected_screen}")
        if not self.observations:
            raise AssertionError("fake core context exhausted observations")
        return self.observations.pop(0)

    def scroll_daily_quest(self, *, adjusted: bool) -> None:
        """Records the bounded normal or adjusted scroll seam."""

        self.scroll_adjustments.append(adjusted)

    def claim_daily_reward(self, row, checkpoint):
        """Returns one configured claim result or propagates its observed failure."""

        self.claimed_rows.append(row.quest_id)
        if self.claim_error is not None:
            raise self.claim_error
        return checkpoint, DailyTargetOutcome(
            quest_id=row.quest_id,
            status=self.claim_status,
            message="claim result",
        )


def _observation(*entries: DetectedListEntry) -> Observation:
    """Builds one typed Daily Quest observation."""

    return make_observation(ScreenType.PNC_QUEST_DAILY, list_entries=entries, image_size=(540, 960))


def _entry(quest_id: DailyQuestId, state: str, *, bottom: bool = False) -> DetectedListEntry:
    """Builds one visually sourced Daily row fixture."""

    return DetectedListEntry(
        kind=ListEntryKind.DAILY_QUEST,
        bounds=Bounds(9, 372, 518, 99),
        title_text=quest_id.value,
        action_point=(454, 421),
        action_bounds=Bounds(430, 400, 60, 40),
        row_status=RowRecognitionStatus.COMPLETE,
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
