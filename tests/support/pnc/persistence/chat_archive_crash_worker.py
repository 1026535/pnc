"""Child process used only by deterministic chat archive crash tests."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, ChatEntryKind, ObservedChatEntry
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore


def main() -> int:
    root = Path(sys.argv[1])
    boundary = sys.argv[2]

    def fault(stage: str) -> None:
        if stage == boundary:
            os._exit(23)

    store = ChatArchiveStore(root, fault_injector=fault)
    snapshot = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "Child", "child process", 0),))
    store.persist_heartbeat(
        account_id="account",
        castle=CastleIdentity("K1", "Castle", 22),
        channel=ChatChannel.WORLD,
        captured_at=datetime(2026, 1, 1, 23, 59, 58, tzinfo=UTC),
        snapshot=snapshot,
        screenshot_payload=b"child",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
