"""Strict chat pending-record codec tests."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from pnc_automation.app.pnc.persistence.chat_archive_transaction import (
    MAX_PENDING_BYTES,
    ChatArchiveConsistencyError,
    ChatArchiveSchemaError,
    ChatStreamIdentity,
    PendingChatTransaction,
    canonical_json_bytes,
    decode_pending_bytes,
    load_pending,
)


class ChatArchiveTransactionCodecTests(unittest.TestCase):
    """Validates the immutable byte and digest contract of pending records."""

    def _transaction(self) -> PendingChatTransaction:
        next_state = {
            "gap_detected": False,
            "last_captured_at": "2026-01-01T12:00:00+00:00",
            "schema_version": 2,
            "snapshot": {"entries": [], "fingerprint": "deadbeef"},
            "transcript_evidence": {
                "exists": True,
                "length": len(b"[2026-01-01T12:00:00Z] Sender: hi\n"),
                "sha256": hashlib.sha256(b"[2026-01-01T12:00:00Z] Sender: hi\n").hexdigest(),
            },
        }
        return PendingChatTransaction(
            operation_id="operation",
            stream_identity=ChatStreamIdentity("account", "castle", "kingdom"),
            archive_day="2026-01-01",
            captured_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
            transcript_existed=False,
            previous_offset=0,
            prefix_sha256=hashlib.sha256(b"").hexdigest(),
            append_bytes=b"[2026-01-01T12:00:00Z] Sender: hi\n",
            prior_target_state_sha256=None,
            next_state=next_state,
            next_state_sha256=hashlib.sha256(
                canonical_json_bytes(next_state)
            ).hexdigest(),
            screenshot_relative_path="2026-01-01/account/castle/kingdom/screenshots/frame.png",
            screenshot_length=3,
            screenshot_sha256=hashlib.sha256(b"png").hexdigest(),
        )

    def test_round_trip_preserves_exact_append_bytes(self) -> None:
        transaction = self._transaction()
        decoded = decode_pending_bytes(transaction.to_bytes())
        self.assertEqual(transaction, decoded)
        self.assertEqual(transaction.append_bytes, decoded.append_bytes)

    def test_duplicate_keys_and_boolean_schema_version_are_rejected(self) -> None:
        transaction = self._transaction()
        payload = transaction.to_bytes().replace(b'"operation_id":"operation"', b'"operation_id":"operation","operation_id":"other"')
        with self.assertRaises(ChatArchiveSchemaError):
            decode_pending_bytes(payload)
        boolean_version = transaction.to_document()
        boolean_version["schema_version"] = True
        boolean_version["record_sha256"] = hashlib.sha256(
            canonical_json_bytes({key: value for key, value in boolean_version.items() if key != "record_sha256"})
        ).hexdigest()
        with self.assertRaises(ChatArchiveSchemaError):
            decode_pending_bytes(canonical_json_bytes(boolean_version))

    def test_pending_date_mismatch_and_oversized_read_fail_before_mutation(self) -> None:
        transaction = self._transaction()
        mismatched = transaction.to_document()
        mismatched["archive_day"] = "2026-01-02"
        mismatched["record_sha256"] = hashlib.sha256(
            canonical_json_bytes({key: value for key, value in mismatched.items() if key != "record_sha256"})
        ).hexdigest()
        with self.assertRaises(ChatArchiveSchemaError):
            decode_pending_bytes(canonical_json_bytes(mismatched))
        with tempfile.TemporaryDirectory() as temporary_directory:
            pending = Path(temporary_directory) / "pending.json"
            pending.write_bytes(b"x" * (MAX_PENDING_BYTES + 1))
            before = pending.read_bytes()
            with self.assertRaises(ChatArchiveConsistencyError):
                load_pending(pending)
            self.assertEqual(before, pending.read_bytes())

    def test_pending_next_state_without_evidence_is_rejected(self) -> None:
        transaction = self._transaction()
        invalid = transaction.to_document()
        invalid["next_state"]["transcript_evidence"] = None
        invalid["next_state_sha256"] = hashlib.sha256(canonical_json_bytes(invalid["next_state"])).hexdigest()
        invalid["record_sha256"] = hashlib.sha256(
            canonical_json_bytes({key: value for key, value in invalid.items() if key != "record_sha256"})
        ).hexdigest()
        with self.assertRaises(ChatArchiveSchemaError):
            decode_pending_bytes(canonical_json_bytes(invalid))

    def test_pending_stored_path_rejects_windows_alias_forms(self) -> None:
        transaction = self._transaction()
        invalid = transaction.to_document()
        invalid["screenshot"]["path"] = "C:outside.png"
        invalid["record_sha256"] = hashlib.sha256(
            canonical_json_bytes({key: value for key, value in invalid.items() if key != "record_sha256"})
        ).hexdigest()
        with self.assertRaises(ChatArchiveSchemaError):
            decode_pending_bytes(canonical_json_bytes(invalid))


if __name__ == "__main__":
    unittest.main()
