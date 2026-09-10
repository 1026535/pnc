"""Offline tests for daily-maintenance mutation acknowledgements and journals."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.authoring.config.mutation_acknowledgement import parse_mutation_acknowledgement
from pnc_automation.app.authoring.config.daily_maintenance import DailyCapabilityPolicy
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationIntent,
    MutationIntentState,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.errors import ConfigurationError


class MutationAcknowledgementTests(unittest.TestCase):
    """Covers exact target/date/count/premium acknowledgement binding."""

    def test_exact_acknowledgement_authorizes_matching_policy(self) -> None:
        """Accepts only the capability policy encoded by the invocation acknowledgement."""

        acknowledgement = parse_mutation_acknowledgement(
            '{"account_id":"mega_old_acc","castle_ref":"npc_2",'
            '"capability":"hero_arena","maintenance_date":"2026-09-04",'
            '"max_mutations":3,"max_diamond_spend":0}'
        )
        policy = DailyCapabilityPolicy(
            quest_id=DailyQuestId.HERO_ARENA,
            task_id=TaskId.HERO_ARENA,
            max_mutations=3,
        )

        acknowledgement.authorize(
            account_id="mega_old_acc",
            castle_ref="npc_2",
            quest_id=policy.quest_id,
            max_mutations=policy.max_mutations,
            max_diamond_spend=policy.max_diamond_spend,
            maintenance_date=date(2026, 9, 4),
        )

    def test_rejects_broader_or_stale_acknowledgement(self) -> None:
        """Rejects a date or count mismatch before ADB connection."""

        acknowledgement = parse_mutation_acknowledgement(
            '{"account_id":"mega_old_acc","castle_ref":"npc_2",'
            '"capability":"hero_arena","maintenance_date":"2026-09-03",'
            '"max_mutations":4,"max_diamond_spend":0}'
        )
        policy = DailyCapabilityPolicy(
            quest_id=DailyQuestId.HERO_ARENA,
            task_id=TaskId.HERO_ARENA,
            max_mutations=3,
        )

        with self.assertRaisesRegex(ValueError, "does not match"):
            acknowledgement.authorize(
                account_id="mega_old_acc",
                castle_ref="npc_2",
                quest_id=policy.quest_id,
                max_mutations=policy.max_mutations,
                max_diamond_spend=policy.max_diamond_spend,
                maintenance_date=date(2026, 9, 4),
            )

    def test_rejects_incomplete_acknowledgement_schema(self) -> None:
        """Prevents an unbounded acknowledgement from reaching live setup."""

        with self.assertRaisesRegex(ConfigurationError, "exact schema"):
            parse_mutation_acknowledgement('{"account_id":"mega_old_acc"}')


class DailyRunJournalStoreTests(unittest.TestCase):
    """Covers atomic persistence and forward-only operation transitions."""

    def setUp(self) -> None:
        """Creates one isolated store and initial checkpoint."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))
        self.castle = CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22)
        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-04",
            game_reset_id="2026-09-04T00",
            account_id="mega_old_acc",
            castle=self.castle,
            last_typed_screen=ScreenType.PNC_HOME_CITY,
        )

    def test_persists_complete_operation_lifecycle(self) -> None:
        """Writes prepared, dispatched, reconciled, and committed states durably."""

        intent = MutationIntent(
            operation_id="arena-attempt-1",
            quest_id=DailyQuestId.HERO_ARENA,
            state=MutationIntentState.PREPARED,
            expected_precondition="one free Arena attempt is visible",
            expected_postcondition="Daily Arena progress increases by one",
        )
        checkpoint = self.store.prepare_intent(self.checkpoint, intent)
        for state in (
            MutationIntentState.DISPATCHED,
            MutationIntentState.RECONCILED,
            MutationIntentState.COMMITTED,
        ):
            checkpoint = self.store.transition_intent(checkpoint, intent.operation_id, state)

        loaded = self.store.load(
            game_reset_id=self.checkpoint.game_reset_id,
            account_id="mega_old_acc",
            castle=self.castle,
        )
        self.assertEqual(MutationIntentState.COMMITTED, loaded.mutation_intents[0].state)
        self.assertFalse(self.store.checkpoint_path(
            game_reset_id=self.checkpoint.game_reset_id,
            account_id="mega_old_acc",
            castle=self.castle,
        ).with_suffix(".tmp").exists())

    def test_local_midnight_does_not_reset_game_day_receipts(self) -> None:
        """Keeps one journal when Toronto's date changes inside the same UTC game day."""

        self.store.save(self.checkpoint)
        next_local_date = replace(self.checkpoint, maintenance_date="2026-09-05")
        self.assertEqual(self.store.save(self.checkpoint), self.store.save(next_local_date))
        loaded = self.store.load(
            game_reset_id=self.checkpoint.game_reset_id,
            account_id=self.checkpoint.account_id, castle=self.castle,
        )
        self.assertEqual("2026-09-05", loaded.maintenance_date)

    def test_rejects_skipped_or_repeated_transitions(self) -> None:
        """Prevents blind replay or cyclic mutation state changes."""

        checkpoint = self.store.prepare_intent(
            self.checkpoint,
            MutationIntent(
                operation_id="gift-1",
                quest_id=DailyQuestId.ALLIANCE_GIFT,
                state=MutationIntentState.PREPARED,
                expected_precondition="eligible gift is visible",
                expected_postcondition="gift is opened",
            ),
        )

        with self.assertRaisesRegex(ValueError, "cannot transition"):
            self.store.transition_intent(checkpoint, "gift-1", MutationIntentState.RECONCILED)

    def test_consumes_each_recovery_stage_once(self) -> None:
        """Rejects recovery cycles for one checkpoint."""

        checkpoint = self.store.consume_recovery_stage(self.checkpoint, "hero_arena:reread")
        with self.assertRaisesRegex(ValueError, "already consumed"):
            self.store.consume_recovery_stage(checkpoint, "hero_arena:reread")

    def test_rejects_overspent_premium_budget_during_transition(self) -> None:
        """Stops journal updates that would exceed the authorized diamond cap."""

        checkpoint = self.store.prepare_intent(
            self.checkpoint,
            MutationIntent(
                operation_id="boost-1",
                quest_id=DailyQuestId.RESOURCE_BUILDING_BOOST,
                state=MutationIntentState.PREPARED,
                expected_precondition="boost item is absent and 200-diamond option is visible",
                expected_postcondition="boost timer is active",
                diamond_budget=200,
            ),
        )
        with self.assertRaisesRegex(ValueError, "beyond its diamond budget"):
            self.store.transition_intent(
                checkpoint,
                "boost-1",
                MutationIntentState.DISPATCHED,
                diamonds_spent=201,
            )


if __name__ == "__main__":
    unittest.main()
