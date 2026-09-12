"""Offline tests for daily-maintenance mutation acknowledgements and journals."""

from __future__ import annotations

import errno
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import call, patch

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.authoring.config.mutation_acknowledgement import (
    parse_mutation_acknowledgement,
)
from pnc_automation.app.authoring.config.daily_maintenance import DailyCapabilityPolicy
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationDispatcher,
    MutationOperation,
    MutationReconciliation,
)
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationIntent,
    MutationIntentState,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence import daily_run_journal_store
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

    @staticmethod
    def _windows_replace_error(winerror: int) -> PermissionError:
        """Builds a deterministic Windows replacement error on every test host."""

        error = PermissionError(f"Windows replacement error {winerror}")
        error.winerror = winerror
        return error

    def _journal_path(self) -> Path:
        """Returns the isolated journal path used by the fixture checkpoint."""

        return self.store.checkpoint_path(
            game_reset_id=self.checkpoint.game_reset_id,
            account_id=self.checkpoint.account_id,
            castle=self.castle,
        )

    def _assert_no_temporary_journals(self, path: Path) -> None:
        """Confirms failed atomic writes do not leave replacement payloads behind."""

        self.assertEqual((), tuple(path.parent.glob("journal-*.tmp")))

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

    def test_save_retries_transient_windows_replacement_and_persists_full_payload(self) -> None:
        """Retries Windows access and sharing denials against the same flushed payload."""

        path = self._journal_path()
        self.store.save(self.checkpoint)
        updated = replace(
            self.checkpoint,
            maintenance_date="2026-09-05",
            current_quest_id=DailyQuestId.HERO_ARENA,
            completed_quest_ids=(DailyQuestId.CLAIM_COMPLETED,),
            mutation_intents=(
                MutationIntent(
                    operation_id="arena-1",
                    quest_id=DailyQuestId.HERO_ARENA,
                    state=MutationIntentState.PREPARED,
                    expected_precondition="free attempt visible",
                    expected_postcondition="Daily progress increased",
                ),
            ),
            consumed_recovery_stages=("hero_arena:reread",),
            last_typed_screen=ScreenType.PNC_SETTINGS,
        )
        real_replace = daily_run_journal_store.os.replace
        transient_errors = [
            self._windows_replace_error(5),
            self._windows_replace_error(32),
            self._windows_replace_error(33),
        ]

        def replace_with_transient_errors(source: Path, destination: Path) -> None:
            if transient_errors:
                raise transient_errors.pop(0)
            real_replace(source, destination)

        with (
            patch.object(daily_run_journal_store.os, "replace", side_effect=replace_with_transient_errors) as replace_mock,
            patch.object(daily_run_journal_store, "sleep") as sleep_mock,
        ):
            self.store.save(updated)

        loaded = self.store.load(
            game_reset_id=updated.game_reset_id,
            account_id=updated.account_id,
            castle=updated.castle,
        )
        self.assertEqual(updated, loaded)
        self.assertEqual(4, replace_mock.call_count)
        attempted_sources = {item.args[0] for item in replace_mock.call_args_list}
        attempted_destinations = {item.args[1] for item in replace_mock.call_args_list}
        self.assertEqual(1, len(attempted_sources))
        self.assertEqual({path}, attempted_destinations)
        self.assertFalse(transient_errors)
        self.assertEqual(
            [call(0.01), call(0.02), call(0.04)],
            sleep_mock.call_args_list,
        )
        self._assert_no_temporary_journals(path)

    def test_save_stops_after_seven_persistent_windows_denials_and_preserves_old_journal(self) -> None:
        """Stops after the bounded retry budget while preserving the last complete journal."""

        path = self._journal_path()
        self.store.save(self.checkpoint)
        old_payload = path.read_text(encoding="utf-8")
        failure = self._windows_replace_error(5)

        with (
            patch.object(daily_run_journal_store.os, "replace", side_effect=failure) as replace_mock,
            patch.object(daily_run_journal_store, "sleep") as sleep_mock,
        ):
            with self.assertRaises(PermissionError) as raised:
                self.store.save(replace(self.checkpoint, maintenance_date="2026-09-05"))

        self.assertEqual(5, raised.exception.winerror)
        self.assertEqual(7, replace_mock.call_count)
        self.assertEqual(
            [call(0.01), call(0.02), call(0.04), call(0.08), call(0.16), call(0.32)],
            sleep_mock.call_args_list,
        )
        self.assertEqual(old_payload, path.read_text(encoding="utf-8"))
        self._assert_no_temporary_journals(path)

    def test_save_propagates_non_windows_replacement_errors_without_retry(self) -> None:
        """Propagates generic permission and disk failures without sleeping or retrying."""

        path = self._journal_path()
        self.store.save(self.checkpoint)
        old_payload = path.read_text(encoding="utf-8")
        failures = (
            ("generic_permission", PermissionError("generic permission failure")),
            ("disk_full", OSError(errno.ENOSPC, "disk full")),
        )

        for name, failure in failures:
            with self.subTest(name=name):
                with (
                    patch.object(daily_run_journal_store.os, "replace", side_effect=failure) as replace_mock,
                    patch.object(daily_run_journal_store, "sleep") as sleep_mock,
                ):
                    with self.assertRaises(type(failure)):
                        self.store.save(replace(self.checkpoint, maintenance_date="2026-09-05"))

                replace_mock.assert_called_once()
                sleep_mock.assert_not_called()
                self.assertEqual(old_payload, path.read_text(encoding="utf-8"))
                self._assert_no_temporary_journals(path)

    def test_persistent_journal_failure_blocks_dispatch_before_game_action(self) -> None:
        """Refuses to dispatch when the prepared intent cannot be durably journaled."""

        self.store.save(self.checkpoint)
        dispatcher = JournaledMutationDispatcher(self.store)
        operation = MutationOperation(
            operation_id="arena-1",
            quest_id=DailyQuestId.HERO_ARENA,
            expected_precondition="free attempt visible",
            expected_postcondition="Daily progress increased",
        )
        dispatch_count = 0

        def dispatch() -> None:
            nonlocal dispatch_count
            dispatch_count += 1

        with (
            patch.object(daily_run_journal_store.os, "replace", side_effect=self._windows_replace_error(32)) as replace_mock,
            patch.object(daily_run_journal_store, "sleep") as sleep_mock,
        ):
            with self.assertRaises(PermissionError):
                dispatcher.execute(
                    checkpoint=self.checkpoint,
                    operation=operation,
                    dispatch=dispatch,
                    reconcile=lambda: MutationReconciliation(True, False),
                )

        self.assertEqual(0, dispatch_count)
        self.assertEqual(7, replace_mock.call_count)
        self.assertEqual(6, sleep_mock.call_count)

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
