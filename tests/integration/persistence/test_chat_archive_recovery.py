"""Deterministic process-interruption and byte-replay tests for chat archives."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, ChatEntryKind, ObservedChatEntry
from pnc_automation.app.pnc.persistence.chat_archive_store import (
    ChatArchiveStore,
    ChatArchiveState,
    NormalizedPlayerChatEntry,
    VisibleChatSnapshot,
)
from pnc_automation.app.pnc.persistence.chat_archive_transaction import (
    ChatArchiveConsistencyError,
    canonical_json_bytes,
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

    def test_self_checking_pending_evidence_tamper_preserves_every_managed_file(self) -> None:
        """A pending digest can be internally consistent yet must not authorize bad physical evidence."""

        for disposition in ("absent", "partial", "complete"):
            with self.subTest(disposition=disposition), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                snapshot = self._snapshot("tampered")

                def crash(stage: str) -> None:
                    if stage == "after_pending_publish":
                        raise SystemExit(stage)

                with self.assertRaises(SystemExit):
                    ChatArchiveStore(root, fault_injector=crash).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"screenshot",
                    )
                pending = next((root / ".archive-control").rglob("pending.json"))
                transaction = decode_pending_bytes(pending.read_bytes())
                transcript = root / "2026-01-01" / "account" / "k1_castle" / "kingdom" / "transcript.log"
                if disposition == "partial":
                    transcript.parent.mkdir(parents=True, exist_ok=True)
                    transcript.write_bytes(transaction.append_bytes[: len(transaction.append_bytes) // 2])
                elif disposition == "complete":
                    transcript.parent.mkdir(parents=True, exist_ok=True)
                    transcript.write_bytes(transaction.append_bytes)
                tampered = transaction.to_document()
                tampered["next_state"]["transcript_evidence"]["sha256"] = "0" * 64
                tampered["next_state_sha256"] = hashlib.sha256(
                    canonical_json_bytes(tampered["next_state"])
                ).hexdigest()
                tampered["record_sha256"] = hashlib.sha256(
                    canonical_json_bytes({key: value for key, value in tampered.items() if key != "record_sha256"})
                ).hexdigest()
                pending.write_bytes(canonical_json_bytes(tampered))
                screenshot = root / transaction.screenshot_relative_path
                state = transcript.with_name("state.json")
                before = {
                    "pending": pending.read_bytes(),
                    "screenshot": screenshot.read_bytes(),
                    "transcript": None if not transcript.exists() else transcript.read_bytes(),
                    "state": None if not state.exists() else state.read_bytes(),
                }
                with self.assertRaises(ChatArchiveConsistencyError):
                    ChatArchiveStore(root).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=snapshot,
                    )
                self.assertEqual(before["pending"], pending.read_bytes())
                self.assertEqual(before["screenshot"], screenshot.read_bytes())
                self.assertEqual(before["transcript"], None if not transcript.exists() else transcript.read_bytes())
                self.assertEqual(before["state"], None if not state.exists() else state.read_bytes())

    def test_naive_chat_capture_is_rejected_before_archive_mutation(self) -> None:
        """Naive timestamps cannot create a state document that its codec will reject."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            snapshot = self._snapshot("naive")
            before = tuple(path.relative_to(root) for path in root.rglob("*"))
            with self.assertRaisesRegex(ChatArchiveConsistencyError, "aware datetime"):
                store.persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=datetime(2026, 1, 1, 12), snapshot=snapshot, screenshot_payload=b"naive",
                )
            self.assertEqual(before, tuple(path.relative_to(root) for path in root.rglob("*")))

    def test_archive_day_preserves_host_local_legacy_path_resolution(self) -> None:
        """New writes retain the pre-existing host-local day path contract."""

        captured_at = datetime(2026, 1, 2, 0, 30, tzinfo=timezone(timedelta(hours=14)))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            update = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=captured_at, snapshot=self._snapshot("offset day"), screenshot_payload=b"offset",
            )
            expected_day = captured_at.astimezone().date().isoformat()
            self.assertEqual(expected_day, update.directory.relative_to(root).parts[0])
            repeated = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=captured_at + timedelta(seconds=1), snapshot=update.snapshot,
            )
            self.assertFalse(repeated.changed)

    def test_invalid_snapshot_is_rejected_before_no_delta_archive_mutation(self) -> None:
        """Malformed empty/no-delta snapshots cannot create state or control paths."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            valid = self._snapshot("valid")
            invalid_snapshots = (
                VisibleChatSnapshot(entries=(), fingerprint="not-hex"),
                VisibleChatSnapshot(entries=[], fingerprint=valid.fingerprint),  # type: ignore[arg-type]
                VisibleChatSnapshot(entries=(object(),), fingerprint=valid.fingerprint),  # type: ignore[arg-type]
            )

            def tree_bytes() -> tuple[tuple[str, bool, bytes | None], ...]:
                return tuple(sorted(
                    (
                        path.relative_to(root).as_posix(),
                        path.is_dir(),
                        None if path.is_dir() else path.read_bytes(),
                    )
                    for path in root.rglob("*")
                ))

            for snapshot in invalid_snapshots:
                with self.subTest(snapshot=snapshot):
                    before = tree_bytes()
                    with self.assertRaisesRegex(ChatArchiveConsistencyError, "snapshot is malformed"):
                        store.persist_heartbeat(
                            account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                            captured_at=self.captured_at, snapshot=snapshot,
                        )
                    self.assertEqual(before, tree_bytes())

    def test_screenshot_filename_inputs_are_rejected_before_screenshot_mutation(self) -> None:
        """Screenshot names remain confined to the canonical layout even for public snapshot values."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            valid = self._snapshot("filename")
            unsafe_fingerprint = VisibleChatSnapshot(entries=valid.entries, fingerprint="../escape")
            for snapshot, extension in ((valid, "../escape"), (unsafe_fingerprint, "png")):
                with self.subTest(snapshot=snapshot, extension=extension):
                    with self.assertRaises(ChatArchiveConsistencyError):
                        store.persist_heartbeat(
                            account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                            captured_at=self.captured_at, snapshot=snapshot,
                            screenshot_payload=b"filename", screenshot_extension=extension,
                        )
                    self.assertEqual((), tuple(root.rglob("screenshots")))

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

    def test_actual_child_process_exit_after_flush_and_state_is_recoverable(self) -> None:
        """True child exits cover the later append and state publication boundaries too."""

        worker = Path(__file__).parents[2] / "support" / "pnc" / "persistence" / "chat_archive_crash_worker.py"
        for boundary in ("after_transcript_flush", "after_state_publish"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                completed = subprocess.run(
                    [sys.executable, str(worker), str(root), boundary],
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
                    captured_at=self.captured_at, snapshot=snapshot,
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

    def test_same_stream_ordered_overlap_snapshot_replays_after_recovery(self) -> None:
        """A later ordered-overlap snapshot sees recovered state and appends only its new row."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_snapshot = self._snapshot("A")
            second_snapshot = self._snapshot("A", "B")
            first_ready = threading.Event()
            release_first = threading.Event()
            outcomes: list[object] = []

            def pause_first(stage: str) -> None:
                if stage == "after_pending_publish":
                    first_ready.set()
                    self.assertTrue(release_first.wait(timeout=5))

            def run_first() -> None:
                try:
                    outcomes.append(ChatArchiveStore(root, fault_injector=pause_first).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=first_snapshot, screenshot_payload=b"one",
                    ))
                except BaseException as error:
                    outcomes.append(error)

            first_thread = threading.Thread(target=run_first)
            first_thread.start()
            self.assertTrue(first_ready.wait(timeout=5))
            second_result: list[object] = []
            second_done = threading.Event()

            def run_second() -> None:
                try:
                    second_result.append(ChatArchiveStore(root).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at + timedelta(seconds=1),
                        snapshot=second_snapshot, screenshot_payload=b"two",
                    ))
                except BaseException as error:
                    second_result.append(error)
                finally:
                    second_done.set()

            second_thread = threading.Thread(target=run_second)
            second_thread.start()
            self.assertFalse(second_done.wait(timeout=0.1))
            release_first.set()
            first_thread.join(timeout=5)
            second_thread.join(timeout=5)
            self.assertFalse(first_thread.is_alive())
            self.assertFalse(second_thread.is_alive())
            self.assertTrue(all(not isinstance(outcome, BaseException) for outcome in outcomes))
            self.assertEqual(1, len(second_result))
            self.assertFalse(isinstance(second_result[0], BaseException))
            update = second_result[0]
            self.assertEqual(("B",), tuple(entry.message_text for entry in update.appended_entries))
            self.assertEqual(1, update.transcript_path.read_text(encoding="utf-8").count(": A\n"))
            self.assertEqual(1, update.transcript_path.read_text(encoding="utf-8").count(": B\n"))

    def test_separate_streams_do_not_share_a_writer_lock(self) -> None:
        """An unrelated chat channel can publish while another stream is paused."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_ready = threading.Event()
            release_first = threading.Event()
            second_done = threading.Event()
            outcomes: list[object] = []

            def pause_first(stage: str) -> None:
                if stage == "after_pending_publish":
                    first_ready.set()
                    self.assertTrue(release_first.wait(timeout=5))

            def run_first() -> None:
                try:
                    outcomes.append(ChatArchiveStore(root, fault_injector=pause_first).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=self._snapshot("world"), screenshot_payload=b"world",
                    ))
                except BaseException as error:
                    outcomes.append(error)

            def run_second() -> None:
                try:
                    outcomes.append(ChatArchiveStore(root).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.ALLIANCE,
                        captured_at=self.captured_at, snapshot=self._snapshot("alliance"), screenshot_payload=b"alliance",
                    ))
                except BaseException as error:
                    outcomes.append(error)
                finally:
                    second_done.set()

            first_thread = threading.Thread(target=run_first)
            first_thread.start()
            self.assertTrue(first_ready.wait(timeout=5))
            second_thread = threading.Thread(target=run_second)
            second_thread.start()
            self.assertTrue(second_done.wait(timeout=5))
            release_first.set()
            first_thread.join(timeout=5)
            second_thread.join(timeout=5)
            self.assertFalse(first_thread.is_alive())
            self.assertFalse(second_thread.is_alive())
            self.assertEqual(2, len(outcomes))
            self.assertTrue(all(not isinstance(outcome, BaseException) for outcome in outcomes))
            self.assertEqual(2, len(tuple(root.rglob("transcript.log"))))

    def test_current_state_evidence_rejects_missing_transcript_before_no_delta(self) -> None:
        """A nonempty state cannot advance while its target-day transcript is missing."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            snapshot = self._snapshot("same")
            first = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"first",
            )
            state_before = first.state_path.read_bytes()
            first.transcript_path.unlink()
            with self.assertRaises(ChatArchiveConsistencyError):
                store.persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at + timedelta(seconds=1), snapshot=snapshot,
                )
            self.assertEqual(state_before, first.state_path.read_bytes())
            self.assertFalse(first.transcript_path.exists())

    def test_midnight_overlap_state_starts_new_transcript_at_zero(self) -> None:
        """Inherited overlap with no rows creates explicit no-transcript state for the new day."""

        zone = ZoneInfo("America/Toronto")
        before_midnight = datetime(2026, 1, 1, 23, 59, tzinfo=zone)
        after_midnight = before_midnight + timedelta(minutes=2)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            first_snapshot = self._snapshot("A")
            second_snapshot = self._snapshot("A", "B")
            store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=before_midnight, snapshot=first_snapshot, screenshot_payload=b"first",
            )
            unchanged = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=after_midnight, snapshot=first_snapshot,
            )
            self.assertFalse(unchanged.transcript_path.exists())
            self.assertIsNone(json.loads(unchanged.state_path.read_text(encoding="utf-8"))["transcript_evidence"])
            appended = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=after_midnight + timedelta(minutes=1), snapshot=second_snapshot, screenshot_payload=b"second",
            )
            self.assertEqual(("B",), tuple(entry.message_text for entry in appended.appended_entries))
            self.assertEqual("B", appended.transcript_path.read_text(encoding="utf-8").split(": ", 1)[1].splitlines()[0])

    def test_dst_local_day_overlap_keeps_target_day_transcript_boundary(self) -> None:
        """Spring-forward local dates retain the prior-day overlap without borrowing its bytes."""

        zone = ZoneInfo("America/Toronto")
        before_dst_day = datetime(2026, 3, 7, 23, 59, tzinfo=zone)
        on_dst_day = datetime(2026, 3, 8, 3, 1, tzinfo=zone)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            first_snapshot = self._snapshot("A")
            second_snapshot = self._snapshot("A", "B")
            store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=before_dst_day, snapshot=first_snapshot, screenshot_payload=b"first",
            )
            inherited = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=on_dst_day, snapshot=first_snapshot,
            )
            self.assertFalse(inherited.transcript_path.exists())
            appended = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=on_dst_day + timedelta(minutes=1), snapshot=second_snapshot, screenshot_payload=b"second",
            )
            self.assertEqual(("B",), tuple(entry.message_text for entry in appended.appended_entries))
            self.assertEqual(1, appended.transcript_path.read_text(encoding="utf-8").count(": B\n"))

    def test_equal_timestamp_uses_normalized_content_and_retains_empty_baseline(self) -> None:
        """Whitespace/order-only changes and repeated empty observations remain idempotent."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            snapshot = self._snapshot("same")
            reordered = VisibleChatSnapshot(
                entries=(NormalizedPlayerChatEntry(" Bób ", " same ", 99),),
                fingerprint=snapshot.fingerprint,
            )
            different = self._snapshot("different")
            store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"first",
            )
            empty = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=store.build_snapshot(()),
            )
            self.assertFalse(empty.changed)
            self.assertFalse(store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=reordered,
            ).changed)
            with self.assertRaises(ChatArchiveConsistencyError):
                store.persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=different,
                )

            empty_root = Path(temporary_directory) / "empty-first"
            empty_first = ChatArchiveStore(empty_root)
            empty_first.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=empty_first.build_snapshot(()),
            )
            with self.assertRaises(ChatArchiveConsistencyError):
                empty_first.persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=snapshot,
                )

    def test_recovered_rows_are_not_reported_as_current_call_rows(self) -> None:
        """Recovery completes old work while result counts describe only the current observation."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = self._snapshot("A")
            current = self._snapshot("A", "B")

            def crash(stage: str) -> None:
                if stage == "after_pending_publish":
                    raise SystemExit(stage)

            with self.assertRaises(SystemExit):
                ChatArchiveStore(root, fault_injector=crash).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=first, screenshot_payload=b"first",
                )
            update = ChatArchiveStore(root).persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at + timedelta(seconds=1), snapshot=current, screenshot_payload=b"current",
            )
            self.assertEqual(("B",), tuple(entry.message_text for entry in update.appended_entries))
            self.assertEqual(2, update.transcript_path.read_text(encoding="utf-8").count("\n"))

    def test_recovered_future_transaction_rejects_current_stale_observation(self) -> None:
        """A skipped-day lookup cannot hide a pending transaction captured in the future."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            future = self.captured_at + timedelta(days=2)
            snapshot = self._snapshot("future")

            def crash(stage: str) -> None:
                if stage == "after_pending_publish":
                    raise SystemExit(stage)

            with self.assertRaises(SystemExit):
                ChatArchiveStore(root, fault_injector=crash).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=future, snapshot=snapshot, screenshot_payload=b"future",
                )
            with self.assertRaises(ChatArchiveConsistencyError):
                ChatArchiveStore(root).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=snapshot,
                )

    def test_complete_append_flush_failure_is_reflushed_on_recovery(self) -> None:
        """A flush failure after complete append does not permit state publication without a retry flush."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            snapshot = self._snapshot("flush")

            def fail_flush(stage: str) -> None:
                if stage == "after_transcript_flush":
                    raise OSError("injected flush failure")

            with self.assertRaisesRegex(OSError, "flush failure"):
                ChatArchiveStore(root, fault_injector=fail_flush).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"flush",
                )
            update = ChatArchiveStore(root).persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=snapshot,
            )
            self.assertFalse(update.changed)
            self.assertEqual(1, update.transcript_path.read_text(encoding="utf-8").count("\n"))

    def test_state_publication_failure_leaves_pending_and_retry_recovers(self) -> None:
        """A failed state publisher leaves a valid pending record for the next store."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            snapshot = self._snapshot("state failure")
            module = __import__(
                "pnc_automation.app.pnc.persistence.chat_archive_store",
                fromlist=["atomic_write_bytes"],
            )
            real_atomic_write = module.atomic_write_bytes

            def fail_state(destination: Path, payload: bytes, **kwargs: object) -> None:
                if destination.name == "state.json":
                    raise OSError("injected state publication failure")
                real_atomic_write(destination, payload, **kwargs)

            with patch.object(module, "atomic_write_bytes", side_effect=fail_state):
                with self.assertRaisesRegex(OSError, "state publication"):
                    ChatArchiveStore(root).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"state",
                    )
            pending = next((root / ".archive-control").rglob("pending.json"))
            update = ChatArchiveStore(root).persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=snapshot,
            )
            self.assertFalse(update.changed)
            self.assertFalse(pending.exists())
            self.assertEqual(1, update.transcript_path.read_text(encoding="utf-8").count("\n"))

    def test_state_replace_effect_then_error_is_recovered_from_bytes(self) -> None:
        """A state replacement that reports an error after taking effect is classified by recovery."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            snapshot = self._snapshot("replace effect")
            module = __import__(
                "pnc_automation.app.pnc.persistence.chat_archive_store",
                fromlist=["atomic_write_bytes"],
            )
            real_atomic_write = module.atomic_write_bytes

            def replace_then_fail(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
                os.replace(source, target)
                raise OSError("injected post-replace state error")

            def fail_after_state_replace(destination: Path, payload: bytes, **kwargs: object) -> None:
                if destination.name == "state.json":
                    kwargs["replace"] = replace_then_fail
                real_atomic_write(destination, payload, **kwargs)

            with patch.object(module, "atomic_write_bytes", side_effect=fail_after_state_replace):
                with self.assertRaisesRegex(OSError, "post-replace state"):
                    ChatArchiveStore(root).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"replace",
                    )
            update = ChatArchiveStore(root).persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=snapshot,
            )
            self.assertFalse(update.changed)
            self.assertEqual(1, update.transcript_path.read_text(encoding="utf-8").count("\n"))

    def test_missing_pending_screenshot_fails_closed_and_preserves_pending(self) -> None:
        """Recovery never treats missing screenshot evidence as a completed append."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            snapshot = self._snapshot("missing screenshot")

            def crash(stage: str) -> None:
                if stage == "after_pending_publish":
                    raise SystemExit(stage)

            with self.assertRaises(SystemExit):
                ChatArchiveStore(root, fault_injector=crash).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"missing",
                )
            pending = next((root / ".archive-control").rglob("pending.json"))
            transaction = decode_pending_bytes(pending.read_bytes())
            screenshot = root / transaction.screenshot_relative_path
            screenshot.unlink()
            with self.assertRaises(ChatArchiveConsistencyError):
                ChatArchiveStore(root).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=snapshot,
                )
            self.assertTrue(pending.exists())

    def test_recovery_interrupted_at_each_boundary_is_retryable_by_third_store(self) -> None:
        """Each recovery write boundary remains resolvable by a fresh store."""

        for boundary in ("after_transcript_flush", "after_state_publish", "before_pending_retire"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                snapshot = self._snapshot("retry recovery")

                def crash(stage: str) -> None:
                    if stage == "after_pending_publish":
                        raise SystemExit(stage)

                with self.assertRaises(SystemExit):
                    ChatArchiveStore(root, fault_injector=crash).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"retry",
                    )

                def interrupt_recovery(stage: str) -> None:
                    if stage == boundary:
                        raise SystemExit(stage)

                with self.assertRaises(SystemExit):
                    ChatArchiveStore(root, fault_injector=interrupt_recovery).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=snapshot,
                    )
                update = ChatArchiveStore(root).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=snapshot,
                )
                self.assertFalse(update.changed)
                self.assertEqual(1, update.transcript_path.read_text(encoding="utf-8").count("\n"))

    def test_pending_retirement_failure_leaves_recoverable_completion(self) -> None:
        """A retirement error does not discard the already committed transcript and state."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            snapshot = self._snapshot("retire")

            def fail_retire(stage: str) -> None:
                if stage == "before_pending_retire":
                    raise OSError("injected pending retirement failure")

            with self.assertRaisesRegex(OSError, "retirement failure"):
                ChatArchiveStore(root, fault_injector=fail_retire).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"retire",
                )
            pending = next((root / ".archive-control").rglob("pending.json"))
            update = ChatArchiveStore(root).persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=snapshot,
            )
            self.assertFalse(update.changed)
            self.assertFalse(pending.exists())

    def test_recovery_rejects_extra_tail_wrong_prefix_and_incomplete_next_state(self) -> None:
        """Unsupported physical byte/state combinations remain untouched."""

        for disposition in ("extra_tail", "wrong_prefix", "next_state_partial"):
            with self.subTest(disposition=disposition), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                snapshot = self._snapshot("unsafe")

                def crash(stage: str) -> None:
                    if stage == "after_pending_publish":
                        raise SystemExit(stage)

                with self.assertRaises(SystemExit):
                    ChatArchiveStore(root, fault_injector=crash).persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=snapshot, screenshot_payload=b"unsafe",
                    )
                pending_path = next((root / ".archive-control").rglob("pending.json"))
                transaction = decode_pending_bytes(pending_path.read_bytes())
                store = ChatArchiveStore(root)
                directory = store._build_directory(account_id="account", castle=self.castle, channel=ChatChannel.WORLD, captured_at=self.captured_at)
                transcript = directory / "transcript.log"
                state = directory / "state.json"
                if disposition == "extra_tail":
                    transcript.write_bytes(transaction.append_bytes + b"unexpected")
                elif disposition == "wrong_prefix":
                    transcript.write_bytes(b"x" + transaction.append_bytes[1:])
                else:
                    transcript.write_bytes(transaction.append_bytes[:3])
                    state.write_bytes(canonical_json_bytes(transaction.next_state))
                before = (transcript.read_bytes(), state.read_bytes() if state.exists() else None, pending_path.read_bytes())
                with self.assertRaises(ChatArchiveConsistencyError):
                    store.persist_heartbeat(
                        account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                        captured_at=self.captured_at, snapshot=snapshot,
                    )
                self.assertEqual(before, (transcript.read_bytes(), state.read_bytes() if state.exists() else None, pending_path.read_bytes()))

    def test_recovery_rejects_truncated_old_transcript_without_truncating_further(self) -> None:
        """A transaction whose recorded old prefix was truncated fails closed."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ChatArchiveStore(root)
            first = self._snapshot("old")
            second = self._snapshot("old", "new")
            initial = store.persist_heartbeat(
                account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                captured_at=self.captured_at, snapshot=first, screenshot_payload=b"old",
            )

            def crash(stage: str) -> None:
                if stage == "after_pending_publish":
                    raise SystemExit(stage)

            with self.assertRaises(SystemExit):
                ChatArchiveStore(root, fault_injector=crash).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at + timedelta(seconds=1), snapshot=second, screenshot_payload=b"new",
                )
            truncated = initial.transcript_path.read_bytes()[:-1]
            initial.transcript_path.write_bytes(truncated)
            pending = next((root / ".archive-control").rglob("pending.json"))
            pending_before = pending.read_bytes()
            with self.assertRaises(ChatArchiveConsistencyError):
                ChatArchiveStore(root).persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at + timedelta(seconds=1), snapshot=second,
                )
            self.assertEqual(truncated, initial.transcript_path.read_bytes())
            self.assertEqual(pending_before, pending.read_bytes())

    def test_managed_transcript_symlink_is_rejected_without_touching_target(self) -> None:
        """A managed chat path cannot redirect archive writes outside the configured root."""

        if not hasattr(os, "symlink"):
            self.skipTest("symlink creation is unavailable")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "root"
            outside = Path(temporary_directory) / "outside.log"
            root.mkdir()
            outside.write_bytes(b"outside")
            store = ChatArchiveStore(root)
            directory = store._build_directory(account_id="account", castle=self.castle, channel=ChatChannel.WORLD, captured_at=self.captured_at)
            directory.mkdir(parents=True)
            try:
                (directory / "transcript.log").symlink_to(outside)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            with self.assertRaises(ChatArchiveConsistencyError):
                store.persist_heartbeat(
                    account_id="account", castle=self.castle, channel=ChatChannel.WORLD,
                    captured_at=self.captured_at, snapshot=self._snapshot("blocked"), screenshot_payload=b"blocked",
                )
            self.assertEqual(b"outside", outside.read_bytes())


if __name__ == "__main__":
    unittest.main()
