"""Deterministic tests for the typed replacement-core Kingdom Chat workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import unittest

from pnc_automation.app.automation.collect_kingdom_chat import (
    CollectKingdomChatResult,
    CollectKingdomChatWorkflow,
)
from pnc_automation.app.pnc.domain.chat import ChatChannel, ChatEntryKind
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.core.vision.image.models import Bounds
from tests.support.pnc.observations import make_observation


class CollectKingdomChatCoreWorkflowTests(unittest.TestCase):
    """Covers exact channel alignment, fail-closed parsing, and archive results."""

    def test_aligns_kingdom_and_archives_only_player_rows(self) -> None:
        """Selects Kingdom from Alliance and persists the canonical player snapshot."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "chat.png"
            source.write_bytes(b"png")
            alliance = _chat(ChatChannel.ALLIANCE, (), source)
            kingdom = _chat(
                ChatChannel.WORLD,
                (_entry(ChatEntryKind.PLAYER, "Player", "Hello", 0), _entry(ChatEntryKind.ANNOUNCEMENT, "System", "Notice", 1)),
                source,
            )
            context = _FakeChatContext(content=alliance, selected=kingdom)
            result = _workflow(temporary_directory).execute(context)

            self.assertEqual(ChatChannel.WORLD, result.channel)
            self.assertEqual(1, result.visible_player_count)
            self.assertEqual(1, result.appended_count)
            self.assertTrue(result.changed)
            self.assertTrue(result.screenshot_archived)
            self.assertEqual(
                [("navigate", ScreenType.PNC_CHAT), ("observe", ScreenType.PNC_CHAT), ("select", ChatChannel.WORLD)],
                context.calls,
            )
            transcript = next(Path(temporary_directory).rglob("transcript.log"))
            self.assertIn("Player: Hello", transcript.read_text(encoding="utf-8"))

    def test_unchanged_snapshot_reports_no_append_or_screenshot(self) -> None:
        """A repeated visible window updates state without duplicating transcript content."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "chat.png"
            source.write_bytes(b"png")
            observation = _chat(ChatChannel.WORLD, (_entry(ChatEntryKind.PLAYER, "Player", "Hello", 0),), source)
            workflow = _workflow(temporary_directory)
            first = workflow.execute(_FakeChatContext(observation, observation))
            second = workflow.execute(_FakeChatContext(observation, observation))

            self.assertEqual(1, first.appended_count)
            self.assertEqual(0, second.appended_count)
            self.assertFalse(second.changed)
            self.assertFalse(second.screenshot_archived)

    def test_unsupported_row_fails_before_archive_write(self) -> None:
        """An ambiguous transcript row cannot advance archive state."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "chat.png"
            source.write_bytes(b"png")
            observation = _chat(
                ChatChannel.WORLD,
                (_entry(ChatEntryKind.UNSUPPORTED, None, "fragment", 0),),
                source,
            )
            workflow = _workflow(temporary_directory)

            with self.assertRaisesRegex(TaskVerificationError, "unsupported transcript rows"):
                workflow.execute(_FakeChatContext(observation, observation))

            self.assertFalse(any(Path(temporary_directory).rglob("state.json")))

    def test_empty_transcript_fails_before_archive_write(self) -> None:
        """A completely unparsed Chat viewport cannot create or replace an archive baseline."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "chat.png"
            source.write_bytes(b"png")
            observation = _chat(ChatChannel.WORLD, (), source)

            with self.assertRaisesRegex(TaskVerificationError, "no typed chat rows"):
                _workflow(temporary_directory).execute(_FakeChatContext(observation, observation))

            self.assertFalse(any(Path(temporary_directory).rglob("state.json")))

    def test_result_rejects_inconsistent_screenshot_flag(self) -> None:
        """A typed result cannot claim appended rows without a change screenshot."""

        observation = make_observation(ScreenType.PNC_CHAT, active_chat_channel=ChatChannel.WORLD)
        with self.assertRaisesRegex(ValueError, "screenshot"):
            CollectKingdomChatResult(
                channel=ChatChannel.WORLD,
                captured_at=observation.captured_at,
                visible_player_count=1,
                appended_count=1,
                gap_detected=False,
                snapshot_fingerprint="fingerprint",
                screenshot_archived=False,
            )


@dataclass
class _FakeChatContext:
    """Provides only the constrained operations used by the workflow."""

    content: Observation
    selected: Observation
    calls: list[tuple[str, object]] = field(default_factory=list)

    def navigate(self, target: ScreenType) -> Observation:
        self.calls.append(("navigate", target))
        return self.content

    def observe_content(self, *, expected_screen: ScreenType) -> Observation:
        self.calls.append(("observe", expected_screen))
        return self.content

    def select_chat_channel(self, channel: ChatChannel) -> Observation:
        self.calls.append(("select", channel))
        return self.selected


def _workflow(root: str) -> CollectKingdomChatWorkflow:
    return CollectKingdomChatWorkflow(
        account_id="account",
        active_castle=CastleIdentity("K1", "Castle", 22),
        archive_store=ChatArchiveStore(Path(root) / "chat"),
    )


def _chat(
    channel: ChatChannel,
    entries: tuple[DetectedListEntry, ...],
    artifact_path: Path,
) -> Observation:
    return make_observation(
        ScreenType.PNC_CHAT,
        active_chat_channel=channel,
        list_entries=entries,
        artifact_path=artifact_path,
    )


def _entry(kind: ChatEntryKind, sender: str | None, message: str, order: int) -> DetectedListEntry:
    return DetectedListEntry(
        kind=ListEntryKind.CHAT_MESSAGE,
        bounds=Bounds(10, 20 + order * 20, 100, 18),
        title_text=sender,
        metadata={
            "chat_entry_kind": kind.value,
            "message_text": message,
            "visible_order": order,
            **({"unsupported_reason": "message_only"} if kind == ChatEntryKind.UNSUPPORTED else {}),
        },
    )


if __name__ == "__main__":
    unittest.main()
