"""Durable archive persistence for heartbeat-polled chat transcripts."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pnc_automation.app.pnc.persistence.artifact_naming import format_account_artifact_directory, format_castle_artifact_directory
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, ObservedChatEntry, chat_channel_archive_directory, normalize_chat_text


@dataclass(frozen=True, slots=True)
class NormalizedPlayerChatEntry:
    """Represents one normalized visible player-chat row used for overlap and transcript writes."""

    sender_name: str
    message_text: str
    visible_order: int

    def content_key(self) -> tuple[str, str]:
        """Returns the normalized sender/message identity used for overlap comparisons."""

        return (normalize_chat_text(self.sender_name), normalize_chat_text(self.message_text))


@dataclass(frozen=True, slots=True)
class VisibleChatSnapshot:
    """Captures one canonical normalized visible-window snapshot for overlap detection."""

    entries: tuple[NormalizedPlayerChatEntry, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ChatArchiveState:
    """Carries the persisted prior visible window used for one channel/day overlap decision."""

    snapshot: VisibleChatSnapshot
    last_captured_at: datetime | None = None
    gap_detected: bool = False


@dataclass(frozen=True, slots=True)
class StoredChatArchiveUpdate:
    """Summarizes one completed archive persistence decision for one heartbeat poll."""

    directory: Path
    transcript_path: Path
    state_path: Path
    screenshot_path: Path | None
    snapshot: VisibleChatSnapshot
    appended_entries: tuple[NormalizedPlayerChatEntry, ...]
    gap_detected: bool

    @property
    def changed(self) -> bool:
        """Returns whether the heartbeat appended player transcript content."""

        return bool(self.appended_entries)


@dataclass(slots=True)
class ChatArchiveStore:
    """Owns canonical daily transcript layout, overlap state, and screenshot-on-change persistence."""

    root: Path

    def __post_init__(self) -> None:
        """Ensures the durable chat archive root exists before use."""

        self.root.mkdir(parents=True, exist_ok=True)

    def build_snapshot(self, entries: tuple[ObservedChatEntry, ...]) -> VisibleChatSnapshot:
        """Builds the canonical normalized visible-window snapshot from player chat rows."""

        normalized_entries = tuple(
            NormalizedPlayerChatEntry(
                sender_name=_require_non_empty_chat_value(entry.sender_name, field_name="sender_name"),
                message_text=_require_non_empty_chat_value(entry.message_text, field_name="message_text"),
                visible_order=entry.visible_order,
            )
            for entry in entries
            if entry.is_player
        )
        payload = "\n".join(
            f"{normalize_chat_text(entry.sender_name)}|{normalize_chat_text(entry.message_text)}"
            for entry in normalized_entries
        ).encode("utf-8")
        fingerprint = hashlib.sha256(payload).hexdigest()[:8]
        return VisibleChatSnapshot(entries=normalized_entries, fingerprint=fingerprint)

    def persist_heartbeat(
        self,
        *,
        account_id: str,
        castle: CastleIdentity,
        channel: ChatChannel,
        captured_at: datetime,
        snapshot: VisibleChatSnapshot,
        screenshot_payload: bytes | None = None,
        screenshot_source_path: Path | None = None,
        screenshot_extension: str = "png",
    ) -> StoredChatArchiveUpdate:
        """Applies one heartbeat snapshot to the durable transcript and returns the resulting archive decision."""

        directory = self._build_directory(
            account_id=account_id,
            castle=castle,
            channel=channel,
            captured_at=captured_at,
        )
        directory.mkdir(parents=True, exist_ok=True)
        transcript_path = directory / "transcript.log"
        state_path = directory / "state.json"
        previous_state = self._load_overlap_baseline_state(
            state_path=state_path,
            account_id=account_id,
            castle=castle,
            channel=channel,
            captured_at=captured_at,
        )
        appended_entries, gap_detected = _compute_snapshot_delta(
            previous=previous_state.snapshot if previous_state is not None else None,
            current=snapshot,
        )
        if appended_entries:
            self._append_transcript(transcript_path, captured_at=captured_at, entries=appended_entries)
        screenshot_path = None
        if appended_entries:
            screenshot_path = self._persist_screenshot(
                directory=directory,
                captured_at=captured_at,
                snapshot=snapshot,
                screenshot_payload=screenshot_payload,
                screenshot_source_path=screenshot_source_path,
                screenshot_extension=screenshot_extension,
            )
        self._write_state(
            state_path,
            ChatArchiveState(
                snapshot=snapshot,
                last_captured_at=captured_at,
                gap_detected=gap_detected,
            ),
        )
        return StoredChatArchiveUpdate(
            directory=directory,
            transcript_path=transcript_path,
            state_path=state_path,
            screenshot_path=screenshot_path,
            snapshot=snapshot,
            appended_entries=appended_entries,
            gap_detected=gap_detected,
        )

    def _build_directory(
        self,
        *,
        account_id: str,
        castle: CastleIdentity,
        channel: ChatChannel,
        captured_at: datetime,
    ) -> Path:
        """Builds the canonical daily archive directory for one account/castle/channel heartbeat stream."""

        local_day = captured_at.astimezone().strftime("%Y-%m-%d")
        return self._build_directory_for_local_day(
            account_id=account_id,
            castle=castle,
            channel=channel,
            local_day=local_day,
        )

    def _build_directory_for_local_day(
        self,
        *,
        account_id: str,
        castle: CastleIdentity,
        channel: ChatChannel,
        local_day: str,
    ) -> Path:
        """Builds the canonical archive directory for one already-resolved local day."""

        return (
            self.root
            / local_day
            / format_account_artifact_directory(account_id=account_id)
            / format_castle_artifact_directory(kingdom=castle.kingdom, castle_name=castle.castle_name)
            / chat_channel_archive_directory(channel)
        )

    def _load_overlap_baseline_state(
        self,
        *,
        state_path: Path,
        account_id: str,
        castle: CastleIdentity,
        channel: ChatChannel,
        captured_at: datetime,
    ) -> ChatArchiveState | None:
        """Loads the current-day overlap state or carries over the prior local day when the new day is empty."""

        current_state = self._load_state(state_path)
        if current_state is not None:
            return current_state
        previous_day = (captured_at.astimezone() - timedelta(days=1)).strftime("%Y-%m-%d")
        previous_state_path = (
            self._build_directory_for_local_day(
                account_id=account_id,
                castle=castle,
                channel=channel,
                local_day=previous_day,
            )
            / "state.json"
        )
        return self._load_state(previous_state_path)

    def _load_state(self, state_path: Path) -> ChatArchiveState | None:
        """Loads the prior persisted state for one day/channel when it exists."""

        if not state_path.is_file():
            return None
        document = json.loads(state_path.read_text(encoding="utf-8"))
        snapshot_document = _require_mapping(document.get("snapshot"), field_name="snapshot")
        entries = tuple(
            NormalizedPlayerChatEntry(
                sender_name=_require_non_empty_chat_value(entry.get("sender_name"), field_name="sender_name"),
                message_text=_require_non_empty_chat_value(entry.get("message_text"), field_name="message_text"),
                visible_order=_require_non_negative_int(entry.get("visible_order"), field_name="visible_order"),
            )
            for entry in _require_sequence(snapshot_document.get("entries"), field_name="snapshot.entries")
        )
        last_captured_at = document.get("last_captured_at")
        return ChatArchiveState(
            snapshot=VisibleChatSnapshot(
                entries=entries,
                fingerprint=_require_non_empty_chat_value(snapshot_document.get("fingerprint"), field_name="snapshot.fingerprint"),
            ),
            last_captured_at=None if last_captured_at is None else datetime.fromisoformat(last_captured_at),
            gap_detected=bool(document.get("gap_detected", False)),
        )

    def _append_transcript(
        self,
        transcript_path: Path,
        *,
        captured_at: datetime,
        entries: tuple[NormalizedPlayerChatEntry, ...],
    ) -> None:
        """Appends one ordered batch of newly visible player rows to the daily transcript file."""

        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = captured_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with transcript_path.open("a", encoding="utf-8", newline="\n") as handle:
            for entry in entries:
                handle.write(f"[{timestamp}] {entry.sender_name}: {entry.message_text}\n")

    def _persist_screenshot(
        self,
        *,
        directory: Path,
        captured_at: datetime,
        snapshot: VisibleChatSnapshot,
        screenshot_payload: bytes | None,
        screenshot_source_path: Path | None,
        screenshot_extension: str,
    ) -> Path:
        """Writes the durable heartbeat screenshot only when player transcript content changed."""

        screenshots_directory = directory / "screenshots"
        screenshots_directory.mkdir(parents=True, exist_ok=True)
        extension = screenshot_extension.lstrip(".") or "png"
        filename = f"{captured_at.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}_{snapshot.fingerprint}.{extension}"
        screenshot_path = screenshots_directory / filename
        if screenshot_payload is not None:
            screenshot_path.write_bytes(screenshot_payload)
            return screenshot_path
        if screenshot_source_path is not None:
            shutil.copyfile(screenshot_source_path, screenshot_path)
            return screenshot_path
        raise ValueError("ChatArchiveStore requires screenshot payload or source path when persisting a change screenshot.")

    def _write_state(self, state_path: Path, state: ChatArchiveState) -> None:
        """Persists the canonical daily overlap state after one heartbeat decision."""

        state_document: dict[str, Any] = {
            "last_captured_at": None if state.last_captured_at is None else state.last_captured_at.isoformat(),
            "gap_detected": state.gap_detected,
            "snapshot": {
                "fingerprint": state.snapshot.fingerprint,
                "entries": [asdict(entry) for entry in state.snapshot.entries],
            },
        }
        state_path.write_text(json.dumps(state_document, indent=2, sort_keys=True), encoding="utf-8")


def _compute_snapshot_delta(
    *,
    previous: VisibleChatSnapshot | None,
    current: VisibleChatSnapshot,
) -> tuple[tuple[NormalizedPlayerChatEntry, ...], bool]:
    """Returns the newly visible player tail and whether the visible window continuity was broken."""

    if previous is None or not previous.entries:
        return current.entries, False
    if previous.fingerprint == current.fingerprint:
        return (), False
    overlap = _find_overlap(previous.entries, current.entries)
    if overlap == 0:
        return current.entries, bool(current.entries)
    return current.entries[overlap:], False


def _find_overlap(
    previous_entries: tuple[NormalizedPlayerChatEntry, ...],
    current_entries: tuple[NormalizedPlayerChatEntry, ...],
) -> int:
    """Returns the maximum suffix/prefix overlap length shared by the two visible snapshots."""

    max_overlap = min(len(previous_entries), len(current_entries))
    for overlap in range(max_overlap, 0, -1):
        if _entries_match(previous_entries[-overlap:], current_entries[:overlap]):
            return overlap
    return 0


def _entries_match(
    previous_entries: tuple[NormalizedPlayerChatEntry, ...],
    current_entries: tuple[NormalizedPlayerChatEntry, ...],
) -> bool:
    """Returns whether the ordered entries describe the same normalized sender/message sequence."""

    return all(previous.content_key() == current.content_key() for previous, current in zip(previous_entries, current_entries, strict=True))


def _require_mapping(value: object, *, field_name: str) -> dict[str, Any]:
    """Returns one required mapping or fails fast when the persisted state is malformed."""

    if isinstance(value, dict):
        return value
    raise ValueError(f"Chat archive state field '{field_name}' must be a mapping.")


def _require_sequence(value: object, *, field_name: str) -> list[dict[str, Any]]:
    """Returns one required list of entry mappings or fails fast when the persisted state is malformed."""

    if isinstance(value, list):
        return [
            _require_mapping(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ValueError(f"Chat archive state field '{field_name}' must be a list.")


def _require_non_empty_chat_value(value: object, *, field_name: str) -> str:
    """Returns one required non-empty string persisted in the chat archive state."""

    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    raise ValueError(f"Chat archive state field '{field_name}' must be a non-empty string.")


def _require_non_negative_int(value: object, *, field_name: str) -> int:
    """Returns one required non-negative integer persisted in the chat archive state."""

    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError(f"Chat archive state field '{field_name}' must be a non-negative integer.")
