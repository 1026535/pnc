"""Offline exactly-once tests for visual Daily reward claims."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.claim_executor import (
    JournaledDailyClaimExecutor,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationDispatcher,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    CoordinateProvenance,
    DailyQuestId,
    DailyQuestRow,
    DailyQuestRowState,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    MutationIntentState,
    NormalizedBounds,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    Observation,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


class DailyClaimExecutorTests(unittest.TestCase):
    """Proves fresh fingerprint selection and ambiguous-result replay prevention."""

    def setUp(self) -> None:
        """Creates one isolated journal and checkpoint."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))
        self.checkpoint = DailyTaskCheckpoint(
            maintenance_date="2026-09-04",
            game_reset_id="reset",
            account_id="account",
            castle=CastleIdentity("K1", "Castle"),
        )
        self.row = DailyQuestRow(
            quest_id=DailyQuestId.UPGRADE_BUILDING,
            normalized_title="UPGRADEBUILDING",
            state=DailyQuestRowState.CLAIM,
            bounds=NormalizedBounds(0.01, 0.38, 0.96, 0.1),
            observation_fingerprint="fingerprint",
            progress_current=1,
            progress_required=1,
            coordinate_provenance=CoordinateProvenance.VISUAL_GEOMETRY,
        )

    def tearDown(self) -> None:
        """Removes isolated journal files."""

        self.temporary_directory.cleanup()

    def test_commits_only_after_fresh_row_changes_out_of_claim_state(self) -> None:
        """Persists dispatch before tapping and commits a proved claim transition."""

        session = _ClaimSession((_observation("claim"), _observation("completed")))
        action_executor = Mock()
        checkpoint, outcome = self._executor(session, action_executor).claim(
            row=self.row,
            checkpoint=self.checkpoint,
        )
        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, outcome.status)
        self.assertEqual(MutationIntentState.COMMITTED, checkpoint.mutation_intents[0].state)
        action_executor.execute_action.assert_called_once()

    def test_ambiguous_missing_row_is_not_committed_or_replayed(self) -> None:
        """Leaves one durable reconciled intent when the row disappears ambiguously."""

        session = _ClaimSession((_observation("claim"), _empty_observation()))
        checkpoint, outcome = self._executor(session, Mock()).claim(
            row=self.row,
            checkpoint=self.checkpoint,
        )
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, outcome.status)
        self.assertEqual(MutationIntentState.RECONCILED, checkpoint.mutation_intents[0].state)
        persisted = self.store.load(
            game_reset_id=self.checkpoint.game_reset_id,
            account_id="account",
            castle=self.checkpoint.castle,
        )
        self.assertEqual(MutationIntentState.RECONCILED, persisted.mutation_intents[0].state)

    def test_unrecognized_action_does_not_prove_reward_claimed(self) -> None:
        """Keeps a claim unresolved when OCR cannot read the post-action row control."""

        session = _ClaimSession((_observation("claim"), _observation("unknown_action")))
        action_executor = Mock()

        checkpoint, outcome = self._executor(session, action_executor).claim(
            row=self.row,
            checkpoint=self.checkpoint,
        )

        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, outcome.status)
        self.assertEqual(MutationIntentState.RECONCILED, checkpoint.mutation_intents[0].state)
        action_executor.execute_action.assert_called_once()

    def test_changed_fingerprint_fails_before_tap_and_leaves_dispatched_receipt(self) -> None:
        """Does not tap stale geometry after another frame changes the row fingerprint."""

        executor = self._executor(_ClaimSession((_observation("claim", fingerprint="changed"),)), Mock())
        with self.assertRaisesRegex(RuntimeError, "changed before dispatch"):
            executor.claim(row=self.row, checkpoint=self.checkpoint)
        persisted = self.store.load(
            game_reset_id=self.checkpoint.game_reset_id,
            account_id="account",
            castle=self.checkpoint.castle,
        )
        self.assertEqual(MutationIntentState.DISPATCHED, persisted.mutation_intents[0].state)

    def _executor(self, session, action_executor) -> JournaledDailyClaimExecutor:
        """Builds one claim executor around the test journal."""

        return JournaledDailyClaimExecutor(
            session=session,
            action_executor=action_executor,
            dispatcher=JournaledMutationDispatcher(self.store),
            maximum_claims=2,
        )


class _ClaimSession:
    """Returns a bounded sequence of fresh Daily observations."""

    def __init__(self, observations: tuple[Observation, ...]) -> None:
        """Stores observations in call order."""

        self.observations = list(observations)

    def observe_daily_quest(self, label: str) -> Observation:
        """Returns the next observation."""

        del label
        return self.observations.pop(0)


def _observation(state: str, *, fingerprint: str = "fingerprint") -> Observation:
    """Builds one typed Daily row observation."""

    return Observation(
        screen_type=ScreenType.PNC_QUEST_DAILY,
        visible_elements={},
        list_entries=(
            DetectedListEntry(
                kind=ListEntryKind.DAILY_QUEST,
                bounds=Bounds(9, 372, 518, 99),
                title_text="Upgrade Building",
                action_point=(454, 421),
                metadata={
                    "quest_id": DailyQuestId.UPGRADE_BUILDING.value,
                    "row_state": state,
                    "coordinate_provenance": "visual_geometry",
                    "observation_fingerprint": fingerprint,
                },
            ),
        ),
        image_size=(540, 960),
    )


def _empty_observation() -> Observation:
    """Builds a typed Daily observation where the source row is absent."""

    return Observation(
        screen_type=ScreenType.PNC_QUEST_DAILY,
        visible_elements={},
        list_entries=(),
        image_size=(540, 960),
    )


if __name__ == "__main__":
    unittest.main()
