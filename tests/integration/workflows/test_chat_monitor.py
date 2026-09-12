"""Kingdom chat monitor tests covering archive persistence and heartbeat task behavior."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    CredentialSource,
    DefaultsConfig,
    ResolvedCredentials,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, ChatEntryKind, ObservedChatEntry

from tests.support.core.logging import build_logger


class ChatMonitorTests(unittest.TestCase):
    """Validates durable Kingdom Chat archiving and the heartbeat task contract."""

    def setUp(self) -> None:
        """Builds the shared account, defaults, and flow planner used by chat monitor tests."""

        self.account = AccountConfig(
            id="testing",
            instance_id="bs-main",
            pnc_account_id="user@example.com",
            credentials=ResolvedCredentials(
                username="user@example.com",
                password="secret",
                source=CredentialSource.INLINE,
            ),
        )
        self.defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        self.logger = build_logger()
        self.target_castle = CastleIdentity(kingdom="K304", castle_name="K304554ca2797", castle_level=12)

    def test_chat_archive_store_appends_first_snapshot_and_writes_screenshot(self) -> None:
        """Writes the initial daily transcript, state, and change screenshot under the durable archive root."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            snapshot = store.build_snapshot(
                (
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "Hello there", 0),
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Cutie Voj", "Need help on rally?", 1),
                )
            )

            update = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=snapshot,
                screenshot_payload=b"fake_png_payload",
            )

            transcript = update.transcript_path.read_text(encoding="utf-8")
            self.assertTrue(update.changed)
            self.assertFalse(update.gap_detected)
            self.assertEqual(len(update.appended_entries), 2)
            self.assertTrue(update.screenshot_path is not None and update.screenshot_path.is_file())
            self.assertTrue(update.state_path.is_file())
            self.assertIn("Enemy Bob: Hello there", transcript)
            self.assertIn("Cutie Voj: Need help on rally?", transcript)
            self.assertEqual(update.directory.parts[-4:], ("2026-03-23", "testing", "k304_k304554ca2797", "kingdom"))

    def test_chat_archive_store_noops_when_snapshot_is_unchanged(self) -> None:
        """Does not append transcript content or write another durable screenshot for an idle repeat heartbeat."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            snapshot = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "Hello there", 0),))
            first = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=snapshot,
                screenshot_payload=b"first_payload",
            )
            second = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 20, 0, tzinfo=UTC),
                snapshot=snapshot,
                screenshot_payload=b"second_payload",
            )

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertIsNone(second.screenshot_path)
            self.assertEqual(first.transcript_path.read_text(encoding="utf-8").count("Enemy Bob"), 1)

    def test_chat_archive_store_retains_player_baseline_across_empty_heartbeat(self) -> None:
        """Does not erase overlap state when one heartbeat sees only announcements or no player rows."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            player_entries = (
                ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "Hello there", 0),
                ObservedChatEntry(ChatEntryKind.PLAYER, "Cutie Voj", "Need help?", 1),
            )
            first_snapshot = store.build_snapshot(player_entries)
            empty_snapshot = store.build_snapshot((
                ObservedChatEntry(ChatEntryKind.ANNOUNCEMENT, None, "Castle battle begins", 0),
            ))
            first = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=first_snapshot,
                screenshot_payload=b"first_payload",
            )
            empty = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 20, 0, tzinfo=UTC),
                snapshot=empty_snapshot,
            )
            empty_state = json.loads(empty.state_path.read_text(encoding="utf-8"))
            repeated = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 25, 0, tzinfo=UTC),
                snapshot=first_snapshot,
            )

            self.assertTrue(first.changed)
            self.assertFalse(empty.changed)
            self.assertEqual((), empty.snapshot.entries)
            self.assertIsNone(empty.screenshot_path)
            self.assertFalse(repeated.changed)
            self.assertEqual((), repeated.appended_entries)
            self.assertEqual(1, first.transcript_path.read_text(encoding="utf-8").count("Enemy Bob"))
            self.assertEqual(2, len(empty_state["snapshot"]["entries"]))
            self.assertEqual("2026-03-23T10:20:00+00:00", empty_state["last_captured_at"])

    def test_chat_archive_store_accepts_initial_empty_snapshot(self) -> None:
        """Persists an initial empty baseline without requiring a change screenshot."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            update = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=store.build_snapshot(()),
            )

            self.assertFalse(update.changed)
            self.assertEqual((), update.snapshot.entries)
            self.assertTrue(update.state_path.is_file())
            self.assertIsNone(update.screenshot_path)

    def test_chat_archive_store_carries_previous_day_overlap_state_into_new_day(self) -> None:
        """Reuses the prior local-day state for overlap decisions when the new day has not written state yet."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            snapshot = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "Hello there", 0),))
            local_before_midnight = datetime.now().astimezone().replace(hour=23, minute=59, second=0, microsecond=0)
            local_after_midnight = local_before_midnight + timedelta(minutes=2)

            first = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=local_before_midnight,
                snapshot=snapshot,
                screenshot_payload=b"first_payload",
            )
            second = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=local_after_midnight,
                snapshot=snapshot,
                screenshot_payload=b"second_payload",
            )

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertIsNone(second.screenshot_path)
            self.assertTrue(second.state_path.is_file())
            self.assertFalse(second.transcript_path.exists())

    def test_chat_archive_store_appends_only_the_non_overlapping_tail(self) -> None:
        """Appends only newly visible player rows once the previous window suffix overlaps the current prefix."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            first_snapshot = store.build_snapshot(
                (
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "One", 0),
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Cutie Voj", "Two", 1),
                )
            )
            second_snapshot = store.build_snapshot(
                (
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Cutie Voj", "Two", 0),
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Alice", "Three", 1),
                )
            )
            store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=first_snapshot,
                screenshot_payload=b"first_payload",
            )

            update = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 20, 0, tzinfo=UTC),
                snapshot=second_snapshot,
                screenshot_payload=b"second_payload",
            )

            self.assertEqual([entry.sender_name for entry in update.appended_entries], ["Enemy Alice"])
            self.assertFalse(update.gap_detected)

    def test_chat_archive_store_marks_gap_when_overlap_is_missing(self) -> None:
        """Flags a visible gap and appends the whole current window when continuity is lost between heartbeats."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            first_snapshot = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "One", 0),))
            second_snapshot = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Alice", "Two", 0),))
            store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=first_snapshot,
                screenshot_payload=b"first_payload",
            )

            update = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 20, 0, tzinfo=UTC),
                snapshot=second_snapshot,
                screenshot_payload=b"second_payload",
            )

            self.assertTrue(update.changed)
            self.assertTrue(update.gap_detected)
            self.assertEqual([entry.sender_name for entry in update.appended_entries], ["Enemy Alice"])

if __name__ == "__main__":
    unittest.main()
