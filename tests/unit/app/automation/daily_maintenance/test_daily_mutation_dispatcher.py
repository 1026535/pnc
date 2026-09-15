"""Offline tests for daily mutation authorization and exactly-once dispatch."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationDispatcher,
    MutationOperation,
    MutationReconciliation,
)
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.daily_maintenance import DailyCapabilityPolicy
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationAcknowledgement,
    MutationIntent,
    MutationIntentState,
)
from pnc_automation.app.pnc.domain.building_operations import BuildingMutationKind
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


class DailyMutationDispatcherTests(unittest.TestCase):
    """Covers authorization, dispatch boundaries, reconciliation, and interruption recovery."""

    def setUp(self) -> None:
        """Creates one isolated journal and checkpoint."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))
        self.dispatcher = JournaledMutationDispatcher(self.store)
        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-04",
            game_reset_id="2026-09-04T00",
            account_id="mega_old_acc",
            castle=CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22),
        )
        self.operation = MutationOperation(
            operation_id="arena-1",
            quest_id=DailyQuestId.HERO_ARENA,
            expected_precondition="free attempt visible",
            expected_postcondition="Daily progress increased",
        )

    def test_commits_only_after_fresh_postcondition_proof(self) -> None:
        """Persists dispatch before action and commits after one observed proof."""

        observed_states: list[MutationIntentState] = []

        def dispatch() -> None:
            loaded = self.store.load(
                game_reset_id=self.checkpoint.game_reset_id,
                account_id="mega_old_acc",
                castle=self.checkpoint.castle,
            )
            observed_states.append(loaded.mutation_intents[0].state)

        result = self.dispatcher.execute(
            checkpoint=self.checkpoint,
            operation=self.operation,
            dispatch=dispatch,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=True,
                original_precondition_proven=False,
                artifact_paths=("post.png",),
            ),
        )

        self.assertEqual([MutationIntentState.DISPATCHED], observed_states)
        self.assertTrue(result.committed)
        self.assertEqual(MutationIntentState.COMMITTED, result.checkpoint.mutation_intents[0].state)

    def test_ambiguous_reconciliation_never_replays(self) -> None:
        """Marks an ambiguous post-action result pending clarification."""

        dispatch_count = 0

        def dispatch() -> None:
            nonlocal dispatch_count
            dispatch_count += 1

        result = self.dispatcher.execute(
            checkpoint=self.checkpoint,
            operation=self.operation,
            dispatch=dispatch,
            reconcile=lambda: MutationReconciliation(False, False, artifact_paths=("unknown.png",)),
        )

        self.assertEqual(1, dispatch_count)
        self.assertTrue(result.pending_clarification)
        self.assertFalse(result.retry_permitted)
        self.assertEqual(MutationIntentState.RECONCILED, result.checkpoint.mutation_intents[0].state)

    def test_interrupted_dispatched_intent_is_reconciled_without_dispatch(self) -> None:
        """Resumes a dispatched operation by observation only."""

        checkpoint = self.store.prepare_intent(
            self.checkpoint,
            MutationIntent(
                operation_id="arena-1",
                quest_id=DailyQuestId.HERO_ARENA,
                state=MutationIntentState.PREPARED,
                expected_precondition="free attempt visible",
                expected_postcondition="Daily progress increased",
            ),
        )
        checkpoint = self.store.transition_intent(checkpoint, "arena-1", MutationIntentState.DISPATCHED)

        result = self.dispatcher.reconcile_existing(
            checkpoint=checkpoint,
            operation_id="arena-1",
            reconcile=lambda: MutationReconciliation(True, False),
        )

        self.assertTrue(result.committed)

    def test_prepared_building_intent_promotes_once_after_precondition_revalidation(self) -> None:
        """A building-only resume transitions durably before one dispatch and never replays."""

        operation = MutationOperation(
            operation_id="building-prepared-1",
            quest_id=None,
            expected_precondition="exact target control visible",
            expected_postcondition="building receipt observed",
            action_kind=BuildingMutationKind.UPGRADE,
            target={"building": "institute", "instance_key": "home:institute:1"},
        )
        checkpoint = self.store.prepare_intent(
            self.checkpoint,
            MutationIntent(
                operation_id=operation.operation_id,
                quest_id=None,
                state=MutationIntentState.PREPARED,
                expected_precondition=operation.expected_precondition,
                expected_postcondition=operation.expected_postcondition,
                action_kind=operation.action_kind.value,
                target=operation.target,
            ),
        )
        dispatch_count = 0

        def dispatch() -> None:
            nonlocal dispatch_count
            dispatch_count += 1

        result = self.dispatcher.execute(
            checkpoint=checkpoint,
            operation=operation,
            dispatch=dispatch,
            revalidate_precondition=lambda: True,
            reconcile=lambda: MutationReconciliation(True, False),
        )
        replay = self.dispatcher.execute(
            checkpoint=result.checkpoint,
            operation=operation,
            dispatch=dispatch,
            revalidate_precondition=lambda: True,
            reconcile=lambda: MutationReconciliation(True, False),
        )

        self.assertEqual(1, dispatch_count)
        self.assertTrue(result.committed)
        self.assertTrue(replay.committed)
        self.assertEqual(MutationIntentState.COMMITTED, replay.checkpoint.mutation_intents[0].state)


class DailyMutationAuthorizerTests(unittest.TestCase):
    """Covers exact acknowledgement lookup and claim budgets."""

    def test_requires_exact_capability_acknowledgement(self) -> None:
        """Rejects a live operation when no exact acknowledgement exists."""

        policy = DailyCapabilityPolicy(DailyQuestId.HERO_ARENA, TaskId.HERO_ARENA, 3)
        authorizer = DailyMutationAuthorizer()

        with self.assertRaisesRegex(PermissionError, "exactly one"):
            authorizer.require(
                account_id="mega_old_acc",
                castle_ref="npc_2",
                policy=policy,
                maintenance_date=date(2026, 9, 4),
            )

    def test_claim_acknowledgement_is_separate_and_bounded(self) -> None:
        """Uses a dedicated claim-completed capability and exact maximum count."""

        acknowledgement = MutationAcknowledgement(
            account_id="mega_old_acc",
            castle_ref="npc_2",
            quest_id=DailyQuestId.CLAIM_COMPLETED,
            maintenance_date=date(2026, 9, 4),
            max_mutations=100,
            max_diamond_spend=0,
        )
        authorizer = DailyMutationAuthorizer((acknowledgement,))

        self.assertEqual(
            acknowledgement,
            authorizer.require_claims(
                account_id="mega_old_acc",
                castle_ref="npc_2",
                maintenance_date=date(2026, 9, 4),
                max_claims=100,
            ),
        )


if __name__ == "__main__":
    unittest.main()
