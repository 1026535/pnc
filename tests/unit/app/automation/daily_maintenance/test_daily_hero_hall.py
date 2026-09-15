"""Offline tests for the bounded Hero Hall free-single canary."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pnc_automation.app.automation.daily_maintenance.hero_hall import (
    HERO_HALL_FREE_SINGLE_COOLDOWN_SECONDS,
    HeroHallRecruitmentExecutor,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationDispatcher,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    MutationIntent,
    MutationIntentState,
)
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore

from tests.support.pnc.observations import make_observation


class _FakeHeroHallSession:
    """Models one deterministic free-single counter without a live emulator."""

    def __init__(self) -> None:
        """Initializes the five-attempt counter and call audit."""

        self.remaining = 5
        self.dispatch_count = 0
        self.daily_complete = False
        self.cooldown_seconds_after_dispatch: int | None = None
        self.use_generic_control = False
        self.omit_attempts = False
        self.disappear_without_receipt = False
        self.blocked = False
        self.observe_count = 0

    def observe_hero_hall(self, label: str) -> Observation:
        """Returns a typed Hero Hall observation with the current counter."""

        del label
        self.observe_count += 1
        visible_ids = []
        # The recruit button remains visible while the daily counter is positive;
        # the counter decrement is the postcondition used by the executor.
        visible_ids.append(UiElementId.PNC_HERO_HALL_RECRUIT_BANNER)
        if self.omit_attempts or (
            self.disappear_without_receipt and self.dispatch_count > 0
        ):
            banner_text = "Hero Hall"
        elif self.cooldown_seconds_after_dispatch is not None and self.dispatch_count > 0:
            banner_text = "Free in 00:10:00"
        else:
            banner_text = f"Daily attempts: {self.remaining}"
        if self.remaining > 0 and (self.cooldown_seconds_after_dispatch is None or self.dispatch_count == 0) and not (
            self.disappear_without_receipt and self.dispatch_count > 0
        ):
            visible_ids.append(
                UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON
                if self.use_generic_control
                else UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON
            )
        return make_observation(
            ScreenType.PNC_HERO_HALL,
            visible_ids=tuple(visible_ids),
            source_kinds=(
                {UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON: VisibleElementSourceKind.GEOMETRY}
                if self.use_generic_control else {}
            ),
            visible_texts={
                UiElementId.PNC_HERO_HALL_RECRUIT_BANNER: banner_text,
            },
            blocking_popup=self.blocked,
        )

    def recruit_free_single(self) -> None:
        """Consumes one synthetic free single."""

        if self.remaining <= 0:
            raise AssertionError("The fake session cannot recruit beyond the daily target.")
        self.dispatch_count += 1
        self.remaining -= 1
        self.daily_complete = self.remaining == 0

    def daily_requirement_completed(self) -> bool:
        """Returns the synthetic Daily completion state."""

        return self.daily_complete

    def artifact_paths(self) -> tuple[str, ...]:
        """Returns no synthetic screenshot paths."""

        return ()


class HeroHallRecruitmentExecutorTests(unittest.TestCase):
    """Protects the five-single target, cooldown, and exactly-once journal behavior."""

    def setUp(self) -> None:
        """Creates an isolated journal, checkpoint, and deterministic clock."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))
        self.session = _FakeHeroHallSession()
        self.current_time = datetime(2026, 9, 9, 0, 0, tzinfo=UTC)
        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-08",
            game_reset_id="pnc-reset-2026-09-09-00",
            account_id="mega_old_acc",
            castle=CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22),
        )

    def test_commits_exactly_five_singles_and_waits_between_them(self) -> None:
        """Requires one fresh dispatch per five-minute interval and no sixth action."""

        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
            now=lambda: self.current_time,
        )
        checkpoint = self.checkpoint
        for expected_count in range(1, 6):
            checkpoint, outcome = executor.execute(checkpoint=checkpoint)
            expected_status = (
                DailyTargetOutcomeStatus.WAITING_COOLDOWN
                if expected_count < 5
                else DailyTargetOutcomeStatus.SUCCESS
            )
            self.assertEqual(expected_status, outcome.status)
            self.assertEqual(expected_count, self.session.dispatch_count)
            if expected_count < 5:
                checkpoint, waiting = executor.execute(checkpoint=checkpoint)
                self.assertEqual(DailyTargetOutcomeStatus.WAITING_COOLDOWN, waiting.status)
                self.assertEqual(expected_count, self.session.dispatch_count)
                self.current_time += timedelta(seconds=HERO_HALL_FREE_SINGLE_COOLDOWN_SECONDS)

        self.assertEqual(5, self.session.dispatch_count)
        self.assertEqual(5, sum(
            intent.state.value == "committed"
            for intent in checkpoint.mutation_intents
            if intent.quest_id == DailyQuestId.HERO_HALL
        ))

    def test_target_cannot_be_changed_to_six(self) -> None:
        """Rejects a caller that attempts to widen the canary mutation contract."""

        with self.assertRaisesRegex(ValueError, "exactly five"):
            HeroHallRecruitmentExecutor(
                session=self.session,
                dispatcher=JournaledMutationDispatcher(self.store),
                target_count=6,
            )

    def test_observed_cooldown_controls_next_ready_at(self) -> None:
        """Stores the live timer when it differs from the reviewed minimum checkpoint."""

        self.session.cooldown_seconds_after_dispatch = 600
        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
            now=lambda: self.current_time,
        )

        checkpoint, outcome = executor.execute(checkpoint=self.checkpoint)

        self.assertEqual(DailyTargetOutcomeStatus.WAITING_COOLDOWN, outcome.status)
        intent = next(
            intent for intent in checkpoint.mutation_intents if intent.quest_id == DailyQuestId.HERO_HALL
        )
        self.assertEqual("2026-09-09T00:10:00+00:00", intent.metadata["next_ready_at"])

    def test_generic_recruit_control_cannot_authorize_free_single(self) -> None:
        """Keeps the generic Recruit 1x geometry from authorizing a mutation."""

        self.session.use_generic_control = True
        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
            now=lambda: self.current_time,
        )

        checkpoint, outcome = executor.execute(checkpoint=self.checkpoint)

        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, outcome.status)
        self.assertEqual(0, self.session.dispatch_count)
        self.assertEqual((), checkpoint.mutation_intents)

    def test_missing_attempts_cannot_dispatch_free_single(self) -> None:
        """Requires a positive observed attempt counter in addition to the free template."""

        self.session.omit_attempts = True
        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
            now=lambda: self.current_time,
        )

        checkpoint, outcome = executor.execute(checkpoint=self.checkpoint)

        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, outcome.status)
        self.assertEqual(0, self.session.dispatch_count)
        self.assertEqual((), checkpoint.mutation_intents)

    def test_disappearance_without_counter_or_cooldown_stays_pending_without_replay(self) -> None:
        """Does not treat disappearance alone as a receipt and never sends a second tap."""

        self.session.disappear_without_receipt = True
        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
            now=lambda: self.current_time,
        )

        checkpoint, first = executor.execute(checkpoint=self.checkpoint)
        checkpoint, second = executor.execute(checkpoint=checkpoint)

        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, first.status)
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, second.status)
        self.assertEqual(1, self.session.dispatch_count)

    def test_reconcile_existing_commits_expired_cooldown_intent_without_recruiting(self) -> None:
        """Reconciles an old dispatched intent once even when its persisted cooldown elapsed."""

        self.session.remaining = 4
        intent = MutationIntent(
            operation_id="hero-hall-recruit-001",
            quest_id=DailyQuestId.HERO_HALL,
            state=MutationIntentState.DISPATCHED,
            expected_precondition="Hero Hall Recruit tab exposes the free 1x single",
            expected_postcondition="one Hero Hall free single is consumed and its cooldown is recorded",
            metadata={
                "before_daily_attempts_remaining": 5,
                "next_ready_at": (self.current_time - timedelta(seconds=1)).isoformat(),
            },
        )
        checkpoint = replace(self.checkpoint, mutation_intents=(intent,))
        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
            now=lambda: self.current_time,
        )

        result = executor.reconcile_existing(
            checkpoint=checkpoint,
            operation_id=intent.operation_id,
        )

        self.assertTrue(result.committed)
        self.assertEqual(0, self.session.dispatch_count)
        self.assertEqual(1, self.session.observe_count)
        self.assertEqual(MutationIntentState.COMMITTED, result.checkpoint.mutation_intents[0].state)

    def test_reconcile_existing_committed_intent_is_idempotent_without_observation(self) -> None:
        """Returns a committed receipt directly without refreshing or dispatching."""

        intent = MutationIntent(
            operation_id="hero-hall-recruit-001",
            quest_id=DailyQuestId.HERO_HALL,
            state=MutationIntentState.COMMITTED,
            expected_precondition="Hero Hall Recruit tab exposes the free 1x single",
            expected_postcondition="one Hero Hall free single is consumed and its cooldown is recorded",
            metadata={"artifact_paths": ["hero-receipt.png"]},
        )
        checkpoint = replace(self.checkpoint, mutation_intents=(intent,))
        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
        )

        result = executor.reconcile_existing(
            checkpoint=checkpoint,
            operation_id=intent.operation_id,
        )

        self.assertTrue(result.committed)
        self.assertEqual(checkpoint, result.checkpoint)
        self.assertEqual(("hero-receipt.png",), result.artifact_paths)
        self.assertEqual(0, self.session.observe_count)
        self.assertEqual(0, self.session.dispatch_count)

    def test_reconcile_existing_rejects_missing_wrong_prepared_and_invalid_intents_before_observation(self) -> None:
        """Requires an exact existing Hero Hall intent in a reconciliable state."""

        cases = (
            ("missing", self.checkpoint, "hero-hall-recruit-001", KeyError),
            (
                "wrong quest",
                replace(
                    self.checkpoint,
                    mutation_intents=(MutationIntent(
                        operation_id="resource-item-001",
                        quest_id=DailyQuestId.USE_RESOURCE_ITEM,
                        state=MutationIntentState.DISPATCHED,
                        expected_precondition="resource item",
                        expected_postcondition="resource item consumed",
                    ),),
                ),
                "resource-item-001",
                ValueError,
            ),
            (
                "prepared",
                replace(self.checkpoint, mutation_intents=(self._hero_intent(MutationIntentState.PREPARED),)),
                "hero-hall-recruit-001",
                ValueError,
            ),
            (
                "invalid state",
                replace(self.checkpoint, mutation_intents=(self._hero_intent("invalid"),)),
                "hero-hall-recruit-001",
                ValueError,
            ),
        )
        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
        )

        for label, checkpoint, operation_id, error_type in cases:
            with self.subTest(label=label):
                with self.assertRaises(error_type):
                    executor.reconcile_existing(checkpoint=checkpoint, operation_id=operation_id)
                self.assertEqual(0, self.session.observe_count)

    def test_reconcile_existing_ambiguous_receipt_stays_reconciled_without_recruiting(self) -> None:
        """Preserves an ambiguous receipt and never turns reconciliation into a new recruit."""

        self.session.dispatch_count = 1
        self.session.disappear_without_receipt = True
        intent = self._hero_intent(MutationIntentState.DISPATCHED)
        checkpoint = replace(self.checkpoint, mutation_intents=(intent,))
        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
        )

        result = executor.reconcile_existing(
            checkpoint=checkpoint,
            operation_id=intent.operation_id,
        )

        self.assertTrue(result.pending_clarification)
        self.assertFalse(result.committed)
        self.assertEqual(MutationIntentState.RECONCILED, result.checkpoint.mutation_intents[0].state)
        self.assertEqual(1, self.session.dispatch_count)

    def _hero_intent(self, state: MutationIntentState | str) -> MutationIntent:
        """Builds a journal intent for public reconciliation validation tests."""

        return MutationIntent(
            operation_id="hero-hall-recruit-001",
            quest_id=DailyQuestId.HERO_HALL,
            state=state,
            expected_precondition="Hero Hall Recruit tab exposes the free 1x single",
            expected_postcondition="one Hero Hall free single is consumed and its cooldown is recorded",
            metadata={"before_daily_attempts_remaining": 5},
        )

    def test_blocked_hero_hall_state_fails_closed(self) -> None:
        """Rejects a popup-owned Hero Hall frame before any dispatch."""

        self.session.blocked = True
        executor = HeroHallRecruitmentExecutor(
            session=self.session,
            dispatcher=JournaledMutationDispatcher(self.store),
            now=lambda: self.current_time,
        )

        with self.assertRaisesRegex(ValueError, "positively clear"):
            executor.execute(checkpoint=self.checkpoint)
        self.assertEqual(0, self.session.dispatch_count)


if __name__ == "__main__":
    unittest.main()
