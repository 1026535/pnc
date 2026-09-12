"""Deterministic process-interruption and byte-replay tests for chat archives."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, ChatEntryKind, ObservedChatEntry
from pnc_automation.app.pnc.persistence.chat_archive_store import (
    ChatArchiveStore,
    ChatArchiveState,
    VisibleChatSnapshot,
)
from pnc_automation.app.pnc.persistence.chat_archive_transaction import (
    ChatArchiveConsistencyError,
    decode_pending_bytes,
)


class ChatArchiveRecoveryTests(unittest.TestCase):
    """Proves restart recovery preserves exact bytes and state ownership."""

    castle = CastleIdentity("K1", "Castle", 22)
    captured_at = datetime(2026, 1, 1, 23, 59, 58, 123456, tzinfo=UTC)

    def _snapshot(self, *messages: str) -> VisibleChatSnapshot:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        store = ChatArchiveStore(Path(temporary_directory.name))
        return store.build_snapshot(
            tuple(
                ObservedChatEntry(ChatEntryKind.PLAYER, "Bób", message, index)
                for index, message in enumerate(messages)
            )
        )

    def _persist_after_crash(self, root: Path, boundary: str) -> tuple[Path, bytes]:
        snapshot = self._snapshot("first", "second")

        def fault(stage: str) -> None:
            if stage == boundary:
                raise SystemExit(stage)

        store = ChatArchiveStore(root, fault_injector=fault)
        with self.assertRaises(SystemExit):
            store.persist_heartbeat(
                account_id="account",
                castle=self.castle,
                channel=ChatChannel.WORLD,
                captured_at=self.captured_at,
                snapshot=snapshot,
                screenshot_payload=b"screenshot",
            )
        recovered_store = ChatArchiveStore(root)
        update = recovered_store.persist_heartbeat(
            account_id="account",
            castle=self.castle,
            channel=ChatChannel.WORLD,
            captured_at=self.captured_at,
            snapshot=snapshot,
            screenshot_payload=b"same-screenshot",
        )
        self.assertFalse(update.changed)
        self.assertEqual((), tuple((root / ".archive-control").rglob("pending.json")))
        return update.transcript_path, update.transcript_path.read_bytes()

    def test_each_python_interruption_boundary_recovers_without_duplicate_rows(self) -> None:
        """Pending publication, transcript flush, and state publication are restart-safe."""

        for boundary in ("after_pending_publish", "after_transcript_flush", "after_state_publish"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary_directory:
                transcript_path, payload = self._persist_after_crash(Path(temporary_directory), boundary)
                self.assertEqual(2, payload.count(b"B\xc3\xb3b"))
                self.assertEqual(2, payload.count(b"[2026-01-01T23:59:58Z]"))
                self.assertTrue(transcript_path.is_file())

    def test_short_append_replay_is_exact_at_every_byte_position(self) -> None:
        """Recovery accepts valid partial byte tails, including a split UTF-8 sequence."""

        snapshot = self._snapshot("multibyte é row")
        for cut in range(len("[2026-01-01T23:59:58Z] Bób: multibyte é row\n".encode("utf-8"))):
            with self.subTest(cut=cut), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)

                def fault(stage: str) -> None:
                    if stage == "after_pending_publish":
                        raise SystemExit(stage)

                with self.assertRaises(SystemExit):
                    ChatArchiveStore(root, fault_injector=fault).persist_heartbeat(
                        account_id="account",
                        castle=self.castle,
                        channel=ChatChannel.WORLD,
                        captured_at=self.captured_at,
                        snapshot=snapshot,
                        screenshot_payload=b"screenshot",
                    )
                pending_path = next((root / ".archive-control").rglob("pending.json"))
                transaction = decode_pending_bytes(pending_path.read_bytes())
                transcript_path = root / "2026-01-01" / "account" / "k1_castle" / "kingdom" / "transcript.log"
                transcript_path.parent.mkdir(parents=True, exist_ok=True)
                transcript_path.write_bytes(transaction.append_bytes[:cut])
                ChatArchiveStore(root).persist_heartbeat(
                    account_id="account",
                    castle=self.castle,
                    channel=ChatChannel.WORLD,
                    captured_at=self.captured_at,
                    snapshot=snapshot,
                    screenshot_payload=b"ignored",
                )
                self.assertEqual(transaction.append_bytes, transcript_path.read_bytes())

    def test_equal_short_fingerprint_does_not_suppress_different_entries(self) -> None:
        """The compatibility fingerprint is diagnostic; content equality owns overlap."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            first = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "A", "one", 0),))
            second = VisibleChatSnapshot(
                entries=(store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "B", "two", 0),)).entries[0],),
                fingerprint=first.fingerprint,
            )
            store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=first, screenshot_payload=b"one",
            )
            update = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at + timedelta(seconds=1), snapshot=second, screenshot_payload=b"two",
            )
            self.assertEqual(("B",), tuple(entry.sender_name for entry in update.appended_entries))
            self.assertEqual(2, update.transcript_path.read_text(encoding="utf-8").count("\n"))

    def test_malformed_pending_preserves_all_managed_files(self) -> None:
        """A malformed journal fails closed rather than resetting state or transcript."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            snapshot = self._snapshot("one")
            store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"one",
            )
            scope_pending = next((root / ".archive-control").rglob("pending.json"), None)
            self.assertIsNone(scope_pending)
            control = next((root / ".archive-control" / "chat").iterdir())
            pending = control / "pending.json"
            pending.write_bytes(b"{")
            transcript = next(root.rglob("transcript.log"))
            state = next(root.rglob("state.json"))
            before = (transcript.read_bytes(), state.read_bytes())
            with self.assertRaises(ChatArchiveConsistencyError):
                store.persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at + timedelta(seconds=1), snapshot=snapshot,
                )
            self.assertEqual(before, (transcript.read_bytes(), state.read_bytes()))
            self.assertTrue(pending.is_file())

    def test_truncated_state_fails_closed_without_defaulting_to_empty_history(self) -> None:
        """A corrupt existing state cannot turn the next heartbeat into a new baseline."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            snapshot = self._snapshot("one")
            first = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"one",
            )
            transcript_before = first.transcript_path.read_bytes()
            first.state_path.write_bytes(b"{")
            with self.assertRaises(ChatArchiveConsistencyError):
                store.persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at + timedelta(seconds=1), snapshot=snapshot,
                )
            self.assertEqual(transcript_before, first.transcript_path.read_bytes())
            self.assertEqual(b"{", first.state_path.read_bytes())

    def test_stale_observation_is_rejected_before_new_archive_mutation(self) -> None:
        """Recovery and overlap state are never re-dated to an older observation."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            first = self._snapshot("newer")
            older = self._snapshot("older")
            update = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=first, screenshot_payload=b"first",
            )
            before = (update.transcript_path.read_bytes(), update.state_path.read_bytes())
            with self.assertRaises(ChatArchiveConsistencyError):
                store.persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at - timedelta(seconds=1), snapshot=older, screenshot_payload=b"older",
                )
            self.assertEqual(before, (update.transcript_path.read_bytes(), update.state_path.read_bytes()))

    def test_actual_child_process_exit_is_recoverable(self) -> None:
        """A spawned Python process exiting after journal publication leaves recoverable intent."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            worker = Path(__file__).parents[2] / "support" / "pnc" / "persistence" / "chat_archive_crash_worker.py"
            completed = subprocess.run(
                [sys.executable, str(worker), str(root), "after_pending_publish"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=Path(__file__).resolve().parents[3],
            )
            self.assertEqual(23, completed.returncode, completed.stderr)
            snapshot = ChatArchiveStore(root).build_snapshot(
                (ObservedChatEntry(ChatEntryKind.PLAYER, "Child", "child process", 0),)
            )
            update = ChatArchiveStore(root).persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"child",
            )
            self.assertFalse(update.changed)
            self.assertEqual(1, update.transcript_path.read_text(encoding="utf-8").count("\n"))

    def test_distinct_store_objects_serialize_one_stream_transaction(self) -> None:
        """A second object waits for the first object's native stream lock."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            snapshot = self._snapshot("serialized")
            first_ready = threading.Event()
            release_first = threading.Event()
            outcomes: list[object] = []

            def pause_first(stage: str) -> None:
                if stage == "after_pending_publish":
                    first_ready.set()
                    self.assertTrue(release_first.wait(timeout=5))

            def run_first() -> None:
                try:
                    outcomes.append(
                        ChatArchiveStore(root, fault_injector=pause_first).persist_heartbeat(
                            account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                            captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"one",
                        )
                    )
                except BaseException as error:
                    outcomes.append(error)

            first_thread = threading.Thread(target=run_first)
            first_thread.start()
            self.assertTrue(first_ready.wait(timeout=5))
            second_done = threading.Event()

            def run_second() -> None:
                try:
                    outcomes.append(
                        ChatArchiveStore(root).persist_heartbeat(
                            account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                            captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"two",
                        )
                    )
                except BaseException as error:
                    outcomes.append(error)
                finally:
                    second_done.set()

            second_thread = threading.Thread(target=run_second)
            second_thread.start()
            time.sleep(0.1)
            self.assertFalse(second_done.is_set())
            release_first.set()
            first_thread.join(timeout=5)
            second_thread.join(timeout=5)
            self.assertFalse(first_thread.is_alive())
            self.assertFalse(second_thread.is_alive())
            self.assertEqual(2, len(outcomes))
            self.assertTrue(all(not isinstance(outcome, BaseException) for outcome in outcomes))
            transcript = next(root.rglob("transcript.log"))
            self.assertEqual(1, transcript.read_text(encoding="utf-8").count("serialized"))


if __name__ == "__main__":
    unittest.main()
