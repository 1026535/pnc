"""Strict chat pending-record codec tests."""

from __future__ import annotations

import hashlib
import unittest
from datetime import UTC, datetime

from pnc_automation.app.pnc.persistence.chat_archive_transaction import (
    ChatArchiveSchemaError,
    ChatStreamIdentity,
    PendingChatTransaction,
    canonical_json_bytes,
    decode_pending_bytes,
)


class ChatArchiveTransactionCodecTests(unittest.TestCase):
    """Validates the immutable byte and digest contract of pending records."""

    def _transaction(self) -> PendingChatTransaction:
        next_state = {
            "gap_detected": False,
            "last_captured_at": "2026-01-01T00:00:00+00:00",
            "snapshot": {"entries": [], "fingerprint": "deadbeef"},
        }
        return PendingChatTransaction(
            operation_id="operation",
            stream_identity=ChatStreamIdentity("account", "castle", "kingdom"),
            archive_day="2026-01-01",
            captured_at=datetime(2026, 1, 1, tzinfo=UTC),
            transcript_existed=False,
            previous_offset=0,
            prefix_sha256=hashlib.sha256(b"").hexdigest(),
            append_bytes=b"[2026-01-01T00:00:00Z] Sender: hi\n",
            prior_target_state_sha256=None,
            next_state=next_state,
            next_state_sha256=hashlib.sha256(
                b'{"gap_detected":false,"last_captured_at":"2026-01-01T00:00:00+00:00","snapshot":{"entries":[],"fingerprint":"deadbeef"}}'
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


if __name__ == "__main__":
    unittest.main()
