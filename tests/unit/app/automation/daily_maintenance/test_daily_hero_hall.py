"""Offline tests for the bounded Hero Hall free-single canary."""

from __future__ import annotations

import tempfile
import unittest
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
)
from pnc_automation.app.pnc.domain.observation import Observation
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

    def observe_hero_hall(self, label: str) -> Observation:
        """Returns a typed Hero Hall observation with the current counter."""

        del label
        visible_ids = []
        # The recruit button remains visible while the daily counter is positive;
        # the counter decrement is the postcondition used by the executor.
        visible_ids.append(UiElementId.PNC_HERO_HALL_RECRUIT_BANNER)
        if self.cooldown_seconds_after_dispatch is not None and self.dispatch_count > 0:
            banner_text = "Free in 00:10:00"
        else:
            banner_text = f"Daily attempts: {self.remaining}"
        if self.remaining > 0 and (self.cooldown_seconds_after_dispatch is None or self.dispatch_count == 0):
            visible_ids.append(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON)
        return make_observation(
            ScreenType.PNC_HERO_HALL,
            visible_ids=tuple(visible_ids),
            visible_texts={
                UiElementId.PNC_HERO_HALL_RECRUIT_BANNER: banner_text,
            },
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


if __name__ == "__main__":
    unittest.main()
