"""Durable, recoverable persistence for heartbeat-polled chat transcripts."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, ObservedChatEntry, chat_channel_archive_directory, normalize_chat_text
from pnc_automation.app.pnc.persistence.archive_ownership import ArchiveOwnershipScope, chat_archive_scope
from pnc_automation.app.pnc.persistence.artifact_naming import format_castle_artifact_directory
from pnc_automation.app.pnc.persistence.chat_archive_transaction import (
    ChatArchiveConsistencyError,
    ChatArchivePublicationError,
    ChatArchiveSchemaError,
    ChatStreamIdentity,
    PendingChatTransaction,
    canonical_json_bytes,
    decode_json_object,
    load_pending,
    resolve_root_relative,
    write_pending,
)
from pnc_automation.core.infra.storage.atomic_file import atomic_write_bytes
from pnc_automation.core.infra.storage.artifact_naming import format_account_artifact_directory
from pnc_automation.core.infra.storage.file_lock import NativePathLockManager


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
    """Owns chat layout, overlap state, stream locking, and recoverable append transactions."""

    root: Path
    lock_manager: NativePathLockManager = field(default_factory=NativePathLockManager, repr=False)
    fault_injector: Callable[[str], None] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Resolves and creates the durable chat archive root."""

        self.root = self.root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def build_snapshot(self, entries: tuple[ObservedChatEntry, ...]) -> VisibleChatSnapshot:
        """Builds the canonical normalized visible-window snapshot from player chat rows."""

        normalized_entries = tuple(
            NormalizedPlayerChatEntry(
                sender_name=_require_non_empty_chat_value(entry.sender_name, field_name="sender_name"),
                message_text=_require_non_empty_chat_value(entry.message_text, field_name="message_text"),
                visible_order=_require_non_negative_int(entry.visible_order, field_name="visible_order"),
            )
            for entry in entries
            if entry.is_player
        )
        payload = "\n".join(
            f"{normalize_chat_text(entry.sender_name)}|{normalize_chat_text(entry.message_text)}"
            for entry in normalized_entries
        ).encode("utf-8")
        return VisibleChatSnapshot(entries=normalized_entries, fingerprint=hashlib.sha256(payload).hexdigest()[:8])

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
        """Recovers prior work and persists one current heartbeat under one stream lock."""

        directory = self._build_directory(account_id=account_id, castle=castle, channel=channel, captured_at=captured_at)
        state_path = directory / "state.json"
        transcript_path = directory / "transcript.log"
        scope = chat_archive_scope(
            self.root,
            account_id=account_id,
            castle=castle,
            channel=channel,
            lock_manager=self.lock_manager,
        )
        with scope.lock():
            self._recover_pending(scope=scope, account_id=account_id, castle=castle, channel=channel)
            directory.mkdir(parents=True, exist_ok=True)
            previous_state = self._load_overlap_baseline_state(
                state_path=state_path,
                account_id=account_id,
                castle=castle,
                channel=channel,
                captured_at=captured_at,
            )
            self._reject_stale_observation(previous_state, captured_at, snapshot)
            persisted_snapshot = previous_state.snapshot if previous_state is not None and not snapshot.entries else snapshot
            appended_entries, gap_detected = _compute_snapshot_delta(
                previous=previous_state.snapshot if previous_state is not None else None,
                current=snapshot,
            )
            screenshot_path: Path | None = None
            if appended_entries:
                screenshot_path = self._persist_screenshot(
                    directory=directory,
                    captured_at=captured_at,
                    snapshot=snapshot,
                    screenshot_payload=screenshot_payload,
                    screenshot_source_path=screenshot_source_path,
                    screenshot_extension=screenshot_extension,
                )
                self._persist_append_transaction(
                    scope=scope,
                    directory=directory,
                    transcript_path=transcript_path,
                    state_path=state_path,
                    captured_at=captured_at,
                    snapshot=persisted_snapshot,
                    appended_entries=appended_entries,
                    gap_detected=gap_detected,
                    screenshot_path=screenshot_path,
                )
            else:
                self._write_state(
                    state_path,
                    ChatArchiveState(snapshot=persisted_snapshot, last_captured_at=captured_at, gap_detected=gap_detected),
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

    def _persist_append_transaction(
        self,
        *,
        scope: ArchiveOwnershipScope,
        directory: Path,
        transcript_path: Path,
        state_path: Path,
        captured_at: datetime,
        snapshot: VisibleChatSnapshot,
        appended_entries: tuple[NormalizedPlayerChatEntry, ...],
        gap_detected: bool,
        screenshot_path: Path,
    ) -> None:
        """Prepares, appends, publishes state, and retires one chat transaction."""

        existing_transcript = transcript_path.read_bytes() if transcript_path.exists() else b""
        if transcript_path.exists():
            _validate_transcript_bytes(existing_transcript)
        prior_state_bytes = state_path.read_bytes() if state_path.is_file() else None
        prior_state: ChatArchiveState | None = None
        if prior_state_bytes is not None:
            prior_state = _state_from_document(decode_json_object(prior_state_bytes, field_name="state"))
            if prior_state.snapshot.entries and not transcript_path.exists():
                raise ChatArchiveConsistencyError("Chat archive state has visible rows but its transcript is missing.")
        next_state = ChatArchiveState(snapshot=snapshot, last_captured_at=captured_at, gap_detected=gap_detected)
        next_state_document = _state_document(next_state)
        next_state_bytes = canonical_json_bytes(next_state_document)
        append_bytes = _format_append_bytes(captured_at=captured_at, entries=appended_entries)
        relative_screenshot = screenshot_path.resolve().relative_to(self.root).as_posix()
        transaction = PendingChatTransaction(
            operation_id=uuid.uuid4().hex,
            stream_identity=ChatStreamIdentity(
                account_segment=scope.identity.components[0],
                castle_segment=scope.identity.components[1],
                channel=scope.identity.components[2],
            ),
            archive_day=directory.relative_to(self.root).parts[0],
            captured_at=captured_at,
            transcript_existed=transcript_path.exists(),
            previous_offset=len(existing_transcript),
            prefix_sha256=hashlib.sha256(existing_transcript).hexdigest(),
            append_bytes=append_bytes,
            prior_target_state_sha256=(None if prior_state_bytes is None else hashlib.sha256(prior_state_bytes).hexdigest()),
            next_state=next_state_document,
            next_state_sha256=hashlib.sha256(next_state_bytes).hexdigest(),
            screenshot_relative_path=relative_screenshot,
            screenshot_length=screenshot_path.stat().st_size,
            screenshot_sha256=_sha256_file(screenshot_path),
        )
        write_pending(scope.pending_path, transaction)
        self._fault("after_pending_publish")
        self._append_pending_bytes(transcript_path, transaction)
        atomic_write_bytes(state_path, next_state_bytes, prefix="state-", suffix=".tmp")
        self._fault("after_state_publish")
        self._retire_pending(scope.pending_path)

    def _recover_pending(self, *, scope: ArchiveOwnershipScope, account_id: str, castle: CastleIdentity, channel: ChatChannel) -> None:
        """Finishes one published pending record exactly once or fails closed."""

        if not scope.pending_path.exists():
            return
        transaction = load_pending(scope.pending_path)
        _validate_state_bytes(canonical_json_bytes(transaction.next_state))
        expected_identity = ChatStreamIdentity(
            account_segment=scope.identity.components[0],
            castle_segment=scope.identity.components[1],
            channel=scope.identity.components[2],
        )
        if transaction.stream_identity != expected_identity:
            raise ChatArchiveConsistencyError("Chat pending record identity does not match its control path.")
        directory = self._build_directory_for_local_day(
            account_id=account_id,
            castle=castle,
            channel=channel,
            local_day=transaction.archive_day,
        )
        transcript_path = directory / "transcript.log"
        state_path = directory / "state.json"
        screenshot_path = resolve_root_relative(self.root, transaction.screenshot_relative_path)
        if screenshot_path.parent != (directory / "screenshots").resolve():
            raise ChatArchiveConsistencyError("Chat pending screenshot path does not match its recorded stream and day.")
        if not screenshot_path.is_file() or screenshot_path.stat().st_size != transaction.screenshot_length:
            raise ChatArchiveConsistencyError("Chat pending screenshot is missing or incomplete.")
        if _sha256_file(screenshot_path) != transaction.screenshot_sha256:
            raise ChatArchiveConsistencyError("Chat pending screenshot digest does not match its record.")
        current_state_bytes = state_path.read_bytes() if state_path.is_file() else None
        old_state = (
            current_state_bytes is None
            if transaction.prior_target_state_sha256 is None
            else current_state_bytes is not None and hashlib.sha256(current_state_bytes).hexdigest() == transaction.prior_target_state_sha256
        )
        next_state = current_state_bytes is not None and hashlib.sha256(current_state_bytes).hexdigest() == transaction.next_state_sha256
        if not old_state and not next_state:
            raise ChatArchiveConsistencyError("Chat pending recovery found an unrelated or corrupt target state.")
        status = _classify_transcript(transcript_path, transaction)
        if next_state:
            if status != "complete":
                raise ChatArchiveConsistencyError("Chat target state is published before its complete transcript append.")
            self._retire_pending(scope.pending_path)
            return
        if status != "complete":
            self._append_pending_bytes(transcript_path, transaction)
        atomic_write_bytes(state_path, canonical_json_bytes(transaction.next_state), prefix="state-", suffix=".tmp")
        self._fault("after_state_publish")
        self._retire_pending(scope.pending_path)

    def _append_pending_bytes(self, transcript_path: Path, transaction: PendingChatTransaction) -> None:
        """Appends only the still-missing tail of an exact pending byte payload."""

        current = transcript_path.read_bytes() if transcript_path.exists() else b""
        if len(current) < transaction.previous_offset:
            raise ChatArchiveConsistencyError("Chat transcript is shorter than its recorded transaction prefix.")
        prefix = current[: transaction.previous_offset]
        _validate_transcript_prefix(prefix, transaction.previous_offset)
        if hashlib.sha256(prefix).hexdigest() != transaction.prefix_sha256:
            raise ChatArchiveConsistencyError("Chat transcript prefix changed before recovery.")
        if len(current) > transaction.previous_offset + transaction.append_length:
            raise ChatArchiveConsistencyError("Chat transcript contains bytes beyond the recorded transaction.")
        suffix_length = len(current) - transaction.previous_offset
        if current[transaction.previous_offset:] != transaction.append_bytes[:suffix_length]:
            raise ChatArchiveConsistencyError("Chat transcript contains an unexpected pending suffix.")
        remaining = transaction.append_bytes[suffix_length:]
        if remaining:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            with transcript_path.open("r+b" if transcript_path.exists() else "w+b", buffering=0) as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell() != len(current):
                    raise ChatArchiveConsistencyError("Chat transcript changed while preparing its pending append.")
                _write_all(handle, remaining)
                handle.flush()
                os.fsync(handle.fileno())
        else:
            with transcript_path.open("r+b", buffering=0) as handle:
                handle.flush()
                os.fsync(handle.fileno())
        final_bytes = transcript_path.read_bytes()
        _validate_transcript_bytes(final_bytes)
        if len(final_bytes) != transaction.previous_offset + transaction.append_length:
            raise ChatArchiveConsistencyError("Chat transcript append did not reach its recorded byte length.")
        self._fault("after_transcript_flush")

    def _retire_pending(self, pending_path: Path) -> None:
        self._fault("before_pending_retire")
        try:
            pending_path.unlink()
        except OSError as error:
            raise ChatArchivePublicationError("Chat transaction completed but pending-record retirement failed.") from error

    def _fault(self, boundary: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector(boundary)

    def _build_directory(self, *, account_id: str, castle: CastleIdentity, channel: ChatChannel, captured_at: datetime) -> Path:
        """Builds the canonical daily archive directory for one chat stream."""

        return self._build_directory_for_local_day(
            account_id=account_id,
            castle=castle,
            channel=channel,
            local_day=captured_at.astimezone().strftime("%Y-%m-%d"),
        )

    def _build_directory_for_local_day(self, *, account_id: str, castle: CastleIdentity, channel: ChatChannel, local_day: str) -> Path:
        """Builds the canonical archive directory for one already-resolved local day."""

        return self.root / local_day / format_account_artifact_directory(account_id=account_id) / format_castle_artifact_directory(
            kingdom=castle.kingdom,
            castle_name=castle.castle_name,
        ) / chat_channel_archive_directory(channel)

    def _load_overlap_baseline_state(
        self,
        *,
        state_path: Path,
        account_id: str,
        castle: CastleIdentity,
        channel: ChatChannel,
        captured_at: datetime,
    ) -> ChatArchiveState | None:
        """Loads current-day state or the immediate prior-day overlap baseline."""

        current_state = self._load_state(state_path)
        if current_state is not None:
            return current_state
        previous_day = (captured_at.astimezone() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._load_state(
            self._build_directory_for_local_day(
                account_id=account_id,
                castle=castle,
                channel=channel,
                local_day=previous_day,
            ) / "state.json"
        )

    def _load_state(self, state_path: Path) -> ChatArchiveState | None:
        """Loads and strictly validates one complete persisted state document."""

        if not state_path.is_file():
            return None
        try:
            return _state_from_document(decode_json_object(state_path.read_bytes(), field_name="state"))
        except (OSError, ChatArchiveSchemaError, ValueError, TypeError) as error:
            raise ChatArchiveConsistencyError("Chat archive state is malformed.") from error

    def _write_state(self, state_path: Path, state: ChatArchiveState) -> None:
        atomic_write_bytes(state_path, canonical_json_bytes(_state_document(state)), prefix="state-", suffix=".tmp")

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
        """Publishes complete collision-safe screenshot evidence before transcript bytes."""

        if screenshot_payload is None and screenshot_source_path is None:
            raise ValueError("ChatArchiveStore requires screenshot payload or source path when persisting a change screenshot.")
        if screenshot_payload is None:
            assert screenshot_source_path is not None
            if not screenshot_source_path.is_file():
                raise ValueError("ChatArchiveStore screenshot source path does not exist.")
            screenshot_payload = screenshot_source_path.read_bytes()
        if not screenshot_payload:
            raise ValueError("ChatArchiveStore requires a non-empty screenshot payload for a change.")
        screenshots_directory = directory / "screenshots"
        screenshots_directory.mkdir(parents=True, exist_ok=True)
        extension = screenshot_extension.lstrip(".") or "png"
        candidate = screenshots_directory / f"{captured_at.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}_{snapshot.fingerprint}.{extension}"
        digest = hashlib.sha256(screenshot_payload).hexdigest()
        for suffix in range(10000):
            selected = candidate if suffix == 0 else screenshots_directory / f"{candidate.stem}-{suffix}{candidate.suffix}"
            if selected.exists():
                if selected.is_file() and selected.stat().st_size == len(screenshot_payload) and _sha256_file(selected) == digest:
                    return selected
                continue
            atomic_write_bytes(selected, screenshot_payload, prefix="screenshot-", suffix=".tmp")
            return selected
        raise ChatArchivePublicationError("Unable to allocate a collision-safe chat screenshot path.")

    def _reject_stale_observation(self, previous_state: ChatArchiveState | None, captured_at: datetime, snapshot: VisibleChatSnapshot) -> None:
        if previous_state is None or previous_state.last_captured_at is None:
            return
        if captured_at < previous_state.last_captured_at:
            raise ChatArchiveConsistencyError("Chat observation is older than the recovered archive baseline.")
        if captured_at == previous_state.last_captured_at and snapshot.entries != previous_state.snapshot.entries:
            raise ChatArchiveConsistencyError("Chat observation timestamp is reused with different content.")


def _state_document(state: ChatArchiveState) -> dict[str, Any]:
    return {
        "last_captured_at": None if state.last_captured_at is None else state.last_captured_at.isoformat(),
        "gap_detected": state.gap_detected,
        "snapshot": {"fingerprint": state.snapshot.fingerprint, "entries": [asdict(entry) for entry in state.snapshot.entries]},
    }


def _state_from_document(document: dict[str, Any]) -> ChatArchiveState:
    if set(document) - {"last_captured_at", "gap_detected", "snapshot"} or "snapshot" not in document:
        raise ChatArchiveSchemaError("Chat archive state has an unsupported or missing field.")
    snapshot_document = _require_mapping(document["snapshot"], field_name="snapshot")
    if set(snapshot_document) != {"fingerprint", "entries"} or not isinstance(snapshot_document["entries"], list):
        raise ChatArchiveSchemaError("Chat archive state snapshot has an invalid schema.")
    entries: list[NormalizedPlayerChatEntry] = []
    for index, item in enumerate(snapshot_document["entries"]):
        if not isinstance(item, dict):
            raise ChatArchiveSchemaError(f"Chat archive state snapshot entry {index} must be a mapping.")
        entries.append(
            NormalizedPlayerChatEntry(
                sender_name=_require_non_empty_chat_value(item.get("sender_name"), field_name="sender_name"),
                message_text=_require_non_empty_chat_value(item.get("message_text"), field_name="message_text"),
                visible_order=_require_non_negative_int(item.get("visible_order"), field_name="visible_order"),
            )
        )
    captured = document.get("last_captured_at")
    if captured is not None and not isinstance(captured, str):
        raise ChatArchiveSchemaError("Chat archive state last_captured_at must be an ISO timestamp or null.")
    last_captured_at = None if captured is None else datetime.fromisoformat(captured)
    if last_captured_at is not None and (last_captured_at.tzinfo is None or last_captured_at.utcoffset() is None):
        raise ChatArchiveSchemaError("Chat archive state last_captured_at must include a timezone.")
    gap_detected = document.get("gap_detected", False)
    if type(gap_detected) is not bool:
        raise ChatArchiveSchemaError("Chat archive state gap_detected must be a boolean.")
    return ChatArchiveState(
        snapshot=VisibleChatSnapshot(
            entries=tuple(entries),
            fingerprint=_require_non_empty_chat_value(snapshot_document["fingerprint"], field_name="fingerprint"),
        ),
        last_captured_at=last_captured_at,
        gap_detected=gap_detected,
    )


def _validate_state_bytes(payload: bytes) -> None:
    _state_from_document(decode_json_object(payload, field_name="state"))


def _compute_snapshot_delta(*, previous: VisibleChatSnapshot | None, current: VisibleChatSnapshot) -> tuple[tuple[NormalizedPlayerChatEntry, ...], bool]:
    """Returns the newly visible player tail using normalized content, never a short hash."""

    if previous is None or not previous.entries:
        return current.entries, False
    if _entries_match(previous.entries, current.entries):
        return (), False
    overlap = _find_overlap(previous.entries, current.entries)
    return (current.entries if overlap == 0 else current.entries[overlap:], bool(current.entries) if overlap == 0 else False)


def _find_overlap(previous_entries: tuple[NormalizedPlayerChatEntry, ...], current_entries: tuple[NormalizedPlayerChatEntry, ...]) -> int:
    max_overlap = min(len(previous_entries), len(current_entries))
    for overlap in range(max_overlap, 0, -1):
        if _entries_match(previous_entries[-overlap:], current_entries[:overlap]):
            return overlap
    return 0


def _entries_match(previous_entries: tuple[NormalizedPlayerChatEntry, ...], current_entries: tuple[NormalizedPlayerChatEntry, ...]) -> bool:
    if len(previous_entries) != len(current_entries):
        return False
    return all(previous.content_key() == current.content_key() for previous, current in zip(previous_entries, current_entries, strict=True))


def _format_append_bytes(*, captured_at: datetime, entries: tuple[NormalizedPlayerChatEntry, ...]) -> bytes:
    timestamp = captured_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "".join(f"[{timestamp}] {entry.sender_name}: {entry.message_text}\n" for entry in entries).encode("utf-8")


def _classify_transcript(path: Path, transaction: PendingChatTransaction) -> str:
    if not path.exists():
        if transaction.transcript_existed:
            raise ChatArchiveConsistencyError("Chat transcript recorded before the transaction is missing.")
        data = b""
    else:
        if not path.is_file():
            raise ChatArchiveConsistencyError("Chat transcript path is not a regular file.")
        data = path.read_bytes()
    if len(data) < transaction.previous_offset:
        raise ChatArchiveConsistencyError("Chat transcript is shorter than its recorded transaction prefix.")
    prefix = data[: transaction.previous_offset]
    _validate_transcript_prefix(prefix, transaction.previous_offset)
    if hashlib.sha256(prefix).hexdigest() != transaction.prefix_sha256:
        raise ChatArchiveConsistencyError("Chat transcript prefix digest does not match the pending record.")
    if len(data) > transaction.previous_offset + transaction.append_length:
        raise ChatArchiveConsistencyError("Chat transcript contains bytes beyond the pending append.")
    suffix = data[transaction.previous_offset:]
    if suffix != transaction.append_bytes[: len(suffix)]:
        raise ChatArchiveConsistencyError("Chat transcript suffix does not match the pending append.")
    if len(suffix) == transaction.append_length:
        _validate_transcript_bytes(data)
        return "complete"
    return "partial"


def _validate_transcript_prefix(data: bytes, expected_offset: int) -> None:
    if len(data) != expected_offset:
        raise ChatArchiveConsistencyError("Chat transcript prefix length is inconsistent.")
    if data:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ChatArchiveConsistencyError("Chat transcript prefix is not valid UTF-8.") from error
        if not text.endswith("\n"):
            raise ChatArchiveConsistencyError("Chat transcript prefix does not end at a complete line.")


def _validate_transcript_bytes(data: bytes) -> None:
    _validate_transcript_prefix(data, len(data))
    if not data:
        return
    for line in data.decode("utf-8").splitlines():
        if not line.startswith("[") or "] " not in line or ": " not in line:
            raise ChatArchiveConsistencyError("Chat transcript contains a malformed legacy line.")


def _write_all(handle: object, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = handle.write(payload[offset:])  # type: ignore[attr-defined]
        if not isinstance(written, int) or written <= 0:
            raise OSError("Chat transcript write made no progress.")
        offset += written


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_mapping(value: object, *, field_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise ChatArchiveSchemaError(f"Chat archive state field '{field_name}' must be a mapping.")


def _require_non_empty_chat_value(value: object, *, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ChatArchiveSchemaError(f"Chat archive state field '{field_name}' must be a non-empty string.")


def _require_non_negative_int(value: object, *, field_name: str) -> int:
    if type(value) is int and value >= 0:
        return value
    raise ChatArchiveSchemaError(f"Chat archive state field '{field_name}' must be a non-negative integer.")
