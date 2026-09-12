"""Deterministic chat-domain receipt matching tests."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import count_matching_player_chat_entries
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind
from tests.support.pnc.observations import make_entry


def _player_entry(*, sender: str, message: str, order: int) -> DetectedListEntry:
    """Builds one typed player row for receipt matching tests."""

    return make_entry(
        ListEntryKind.CHAT_MESSAGE,
        title=sender,
        metadata={
            "chat_entry_kind": "player",
            "message_text": message,
            "visible_order": order,
        },
    )


class ChatReceiptMatchingTests(unittest.TestCase):
    """Covers OCR whitespace tolerance without weakening receipt identity."""

    def test_alliance_receipt_ignores_ocr_whitespace_only(self) -> None:
        """Matches the live-style collapsed OCR message against the requested spacing."""

        entries = (_player_entry(sender="[NAX] freecookies", message="testfrom bot", order=0),)

        self.assertEqual(
            1,
            count_matching_player_chat_entries(
                entries,
                message="test from bot",
                castle=CastleIdentity("K1", "free cookies"),
            ),
        )

    def test_receipt_whitespace_tolerance_preserves_punctuation_case_and_sender(self) -> None:
        """Rejects punctuation, case, and sender changes despite matching message characters."""

        entries = (
            _player_entry(sender="[NAX] freecookies", message="testfrom bot!", order=0),
            _player_entry(sender="[NAX] FreeCookies", message="Testfrom bot", order=1),
            _player_entry(sender="other player", message="testfrom bot", order=2),
        )

        self.assertEqual(
            0,
            count_matching_player_chat_entries(
                entries,
                message="test from bot",
                castle=CastleIdentity("K1", "free cookies"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
