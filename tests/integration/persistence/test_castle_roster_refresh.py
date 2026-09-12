"""Castle roster refresh: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.refresh_castle_roster_task import RefreshCastleRosterTask
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.domain.castles import CastleIdentity, CastleRosterOrdering

from tests.support.automation.task_context.roster_refresh_fixtures import RosterRefreshFixtures


class CastleRosterRefreshTests(RosterRefreshFixtures, unittest.TestCase):
    """Proves castle roster refresh."""

    def test_refresh_castle_roster_replaces_stale_cache_membership_with_observed_full_scan(self) -> None:
        """Drops obsolete cached castles instead of upgrading stale membership to `full_scan`."""

        alpha = CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3)
        bravo = CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4)
        stale = CastleIdentity(kingdom="K228", castle_name="Stale", castle_level=2)
        with tempfile.TemporaryDirectory() as temp_directory:
            store = CastleRosterStore(path=Path(temp_directory) / "castles.yaml")
            store.sync(
                self.account.pnc_account_id,
                (self.target_castle, stale, alpha, bravo),
                ordering=CastleRosterOrdering.UNKNOWN,
            )

            result, store, context = self._run_refresh_scan(
                store=store,
                windows=(
                    (alpha, bravo),
                    (bravo, self.target_castle),
                ),
            )

            roster = store.get(self.account.pnc_account_id)
            self.assertEqual(result.status.value, "replan")
            self.assertEqual(context.runtime_state["refresh_phase"], "return_home")
            self.assertIsNotNone(roster)
            self.assertEqual(roster.castles, (alpha, bravo, self.target_castle))
            self.assertEqual(roster.ordering, CastleRosterOrdering.FULL_SCAN)

    def test_refresh_castle_roster_replaces_wrong_partial_order_with_scanned_order(self) -> None:
        """Persists the ordered windows observed during the refresh instead of reusing stale cache order."""

        alpha = CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3)
        bravo = CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4)
        with tempfile.TemporaryDirectory() as temp_directory:
            store = CastleRosterStore(path=Path(temp_directory) / "castles.yaml")
            store.sync(
                self.account.pnc_account_id,
                (self.target_castle, alpha, bravo),
                ordering=CastleRosterOrdering.UNKNOWN,
            )

            self._run_refresh_scan(
                store=store,
                windows=(
                    (alpha, bravo),
                    (bravo, self.target_castle),
                ),
            )

            roster = store.get(self.account.pnc_account_id)
            self.assertIsNotNone(roster)
            self.assertEqual(roster.castles, (alpha, bravo, self.target_castle))

    def test_refresh_castle_roster_persists_exact_scanned_windows_and_backfills_missing_levels(self) -> None:
        """Builds the final full scan from the observed windows while using the pre-refresh cache only for missing levels."""

        alpha = CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3)
        bravo = CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4)
        observed_alpha = CastleIdentity(kingdom="K226", castle_name="Alpha")
        observed_bravo = CastleIdentity(kingdom="K227", castle_name="Bravo")
        observed_main = CastleIdentity(kingdom="K230", castle_name="Main")
        with tempfile.TemporaryDirectory() as temp_directory:
            store = CastleRosterStore(path=Path(temp_directory) / "castles.yaml")
            store.sync(
                self.account.pnc_account_id,
                (alpha, bravo, self.target_castle),
                ordering=CastleRosterOrdering.UNKNOWN,
            )

            self._run_refresh_scan(
                store=store,
                windows=(
                    (observed_alpha, observed_bravo),
                    (observed_bravo, observed_main),
                ),
            )

            roster = store.get(self.account.pnc_account_id)
            self.assertIsNotNone(roster)
            self.assertEqual(roster.castles, (alpha, bravo, self.target_castle))
            self.assertEqual(roster.ordering, CastleRosterOrdering.FULL_SCAN)

    def test_refresh_castle_roster_fails_when_scan_repeats_a_previous_window(self) -> None:
        """Fails fast instead of silently looping when full-scan page progression becomes inconsistent."""

        task = RefreshCastleRosterTask()
        context = self._make_context(params=None, task_id=TaskId.REFRESH_CASTLE_ROSTER)
        top_window = self._make_castle_selection_observation(
            (
                CastleIdentity(kingdom="K226", castle_name="Alpha"),
                CastleIdentity(kingdom="K227", castle_name="Bravo"),
            )
        )
        before = self._make_castle_selection_observation((CastleIdentity(kingdom="K230", castle_name="Main"),))
        task.verify(context, top_window, top_window)
        after = top_window

        result = task.verify(context, before, after)

        self.assertEqual(result.status.value, "failed")
        self.assertIn("repeated", result.message)
