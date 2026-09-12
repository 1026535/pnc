"""Adversarial tests for the canonical chat state codec."""

from __future__ import annotations

import hashlib
import unittest
from datetime import UTC, datetime

from pnc_automation.app.pnc.persistence.chat_archive_state import (
    ChatArchiveSchemaError,
    ChatArchiveState,
    ChatTranscriptEvidence,
    NormalizedPlayerChatEntry,
    VisibleChatSnapshot,
    decode_state_document,
    state_document,
)


class ChatArchiveStateCodecTests(unittest.TestCase):
    """Rejects ambiguous state shapes while retaining the old shape for migration."""

    def _state(self) -> ChatArchiveState:
        transcript = b"[2026-01-01T12:00:00Z] Alice: hello\n"
        return ChatArchiveState(
            snapshot=VisibleChatSnapshot(
                entries=(NormalizedPlayerChatEntry("Alice", "hello", 0),),
                fingerprint="deadbeef",
            ),
            last_captured_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
            transcript_evidence=ChatTranscriptEvidence(
                exists=True,
                length=len(transcript),
                sha256=hashlib.sha256(transcript).hexdigest(),
            ),
        )

    def test_version_two_round_trip_requires_evidence(self) -> None:
        decoded = decode_state_document(state_document(self._state()), allow_legacy=False)
        self.assertFalse(decoded.legacy)
        self.assertEqual(self._state(), decoded.state)

    def test_extra_nested_entry_field_is_rejected(self) -> None:
        document = state_document(self._state())
        document["snapshot"]["entries"][0]["extra"] = "reject"
        with self.assertRaises(ChatArchiveSchemaError):
            decode_state_document(document, allow_legacy=False)

    def test_nonempty_current_state_without_evidence_is_explicitly_allowed_only_for_inherited_state(self) -> None:
        document = state_document(self._state())
        document["transcript_evidence"] = None
        decoded = decode_state_document(document, allow_legacy=False)
        self.assertIsNone(decoded.state.transcript_evidence)

    def test_legacy_state_is_marked_for_store_owned_upgrade(self) -> None:
        legacy = {
            "last_captured_at": "2026-01-01T12:00:00+00:00",
            "gap_detected": False,
            "snapshot": {
                "fingerprint": "deadbeef",
                "entries": [{"sender_name": "Alice", "message_text": "hello", "visible_order": 0}],
            },
        }
        decoded = decode_state_document(legacy, allow_legacy=True)
        self.assertTrue(decoded.legacy)
        with self.assertRaises(ChatArchiveSchemaError):
            decode_state_document(legacy, allow_legacy=False)


if __name__ == "__main__":
    unittest.main()
