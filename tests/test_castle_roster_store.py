"""Castle-roster cache persistence tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.authoring.config.models import CastleIdentity, CastleRosterOrdering, PncAccountCastleRosterConfig


class CastleRosterStoreTests(unittest.TestCase):
    """Validates trusted-order metadata and merge behavior for cached rosters."""

    def test_partial_sync_keeps_existing_order_but_marks_ordering_unknown(self) -> None:
        """Persists partial windows without claiming they preserve canonical in-game ordering."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = CastleRosterStore(
                path=Path(temp_directory) / "castles.yaml",
                rosters=(
                    PncAccountCastleRosterConfig(
                        pnc_account_id="inline_user",
                        castles=(
                            CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3),
                            CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4),
                        ),
                        ordering=CastleRosterOrdering.UNKNOWN,
                    ),
                ),
            )

            roster = store.sync(
                "inline_user",
                (
                    CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=5),
                    CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8),
                ),
            )

            self.assertEqual(roster.ordering, CastleRosterOrdering.UNKNOWN)
            self.assertEqual(
                roster.castles,
                (
                    CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3),
                    CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=5),
                    CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8),
                ),
            )

    def test_partial_sync_downgrades_full_scan_when_new_castles_break_the_canonical_order(self) -> None:
        """Stops advertising trusted ordering once partial observations invalidate the last full scan."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = CastleRosterStore(
                path=Path(temp_directory) / "castles.yaml",
                rosters=(
                    PncAccountCastleRosterConfig(
                        pnc_account_id="inline_user",
                        castles=(
                            CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3),
                            CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4),
                        ),
                        ordering=CastleRosterOrdering.FULL_SCAN,
                    ),
                ),
            )

            roster = store.sync(
                "inline_user",
                (
                    CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8),
                ),
            )

            self.assertEqual(roster.ordering, CastleRosterOrdering.UNKNOWN)

    def test_full_scan_sync_replaces_the_canonical_roster_order(self) -> None:
        """Uses explicit full scans as the only source of directional scrolling order."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = CastleRosterStore(path=Path(temp_directory) / "castles.yaml")

            roster = store.sync(
                "inline_user",
                (
                    CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8),
                    CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3),
                ),
                ordering=CastleRosterOrdering.FULL_SCAN,
            )

            self.assertEqual(roster.ordering, CastleRosterOrdering.FULL_SCAN)
            self.assertEqual(
                roster.castles,
                (
                    CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8),
                    CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3),
                ),
            )


if __name__ == "__main__":
    unittest.main()
