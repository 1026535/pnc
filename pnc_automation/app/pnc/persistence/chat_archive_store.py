"""Durable, recoverable persistence for heartbeat-polled chat transcripts."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, ObservedChatEntry, chat_channel_archive_directory, normalize_chat_text
from pnc_automation.app.pnc.persistence.archive_ownership import (
    ArchiveOwnershipError,
    ArchiveOwnershipScope,
    chat_archive_scope,
    validate_chat_archive_directory,
    validate_chat_archive_file,
    validate_managed_path,
)
from pnc_automation.app.pnc.persistence.artifact_naming import format_castle_artifact_directory
from pnc_automation.app.pnc.persistence.chat_archive_state import (
    ChatArchiveSchemaError,
    ChatArchiveState,
    ChatTranscriptEvidence,
    NormalizedPlayerChatEntry,
    VisibleChatSnapshot,
    canonical_json_bytes,
    decode_json_object,
    decode_state_document,
    state_document,
    state_bytes,
    validate_snapshot,
)
from pnc_automation.app.pnc.persistence.chat_archive_transaction import (
    ChatArchiveConsistencyError,
    ChatArchivePublicationError,
    ChatStreamIdentity,
    PendingChatTransaction,
    load_pending,
    parse_archive_day,
    resolve_root_relative,
    write_pending,
)
from pnc_automation.core.infra.storage.atomic_file import atomic_write_bytes
from pnc_automation.core.infra.storage.artifact_naming import format_account_artifact_directory
from pnc_automation.core.infra.storage.file_lock import NativePathLockManager


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


@dataclass(frozen=True, slots=True)
class ChatRecoveryResult:
    """Reports a completed recovery without mixing its rows into the current call."""

    archive_day: str
    captured_at: datetime
    snapshot: VisibleChatSnapshot
    transcript_path: Path
    state_path: Path


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

        _validate_captured_at(captured_at)
        try:
            snapshot = validate_snapshot(snapshot)
        except ChatArchiveSchemaError as error:
            raise ChatArchiveConsistencyError("Chat snapshot is malformed.") from error
        archive_day = captured_at.astimezone().date().isoformat()
        directory = self._build_directory_for_local_day(
            account_id=account_id,
            castle=castle,
            channel=channel,
            local_day=archive_day,
        )
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
            recovered = self._recover_pending(scope=scope, account_id=account_id, castle=castle, channel=channel)
            if recovered is not None:
                self._reject_stale_observation(
                    ChatArchiveState(snapshot=recovered.snapshot, last_captured_at=recovered.captured_at),
                    captured_at,
                    snapshot,
                )
            self._validate_chat_directory(directory)
            directory.mkdir(parents=True, exist_ok=True)
            current_state = self._load_state(
                state_path,
                transcript_path=transcript_path,
                archive_day=archive_day,
            )
            previous_state = current_state
            if previous_state is None:
                previous_day = (date.fromisoformat(archive_day) - timedelta(days=1)).isoformat()
                previous_directory = self._build_directory_for_local_day(
                    account_id=account_id,
                    castle=castle,
                    channel=channel,
                    local_day=previous_day,
                )
                previous_state = self._load_state(
                    previous_directory / "state.json",
                    transcript_path=previous_directory / "transcript.log",
                    archive_day=previous_day,
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
                retained_evidence = None if current_state is None else current_state.transcript_evidence
                self._write_state(
                    state_path,
                    ChatArchiveState(
                        snapshot=persisted_snapshot,
                        last_captured_at=captured_at,
                        gap_detected=gap_detected,
                        transcript_evidence=retained_evidence,
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

        self._validate_chat_file(transcript_path, allowed_names={"transcript.log"}, allow_missing=True)
        self._validate_chat_file(state_path, allowed_names={"state.json"}, allow_missing=True)
        self._validate_managed_file(screenshot_path, allow_missing=False)
        existing_transcript = transcript_path.read_bytes() if transcript_path.exists() else b""
        if transcript_path.exists():
            _validate_transcript_bytes(existing_transcript)
        prior_state_bytes = state_path.read_bytes() if state_path.is_file() else None
        if prior_state_bytes is not None:
            decode_state_document(decode_json_object(prior_state_bytes, field_name="state"), allow_legacy=True)
        next_transcript_length = len(existing_transcript)
        append_bytes = _format_append_bytes(captured_at=captured_at, entries=appended_entries)
        next_state = ChatArchiveState(
            snapshot=snapshot,
            last_captured_at=captured_at,
            gap_detected=gap_detected,
            transcript_evidence=ChatTranscriptEvidence(
                exists=True,
                length=next_transcript_length + len(append_bytes),
                sha256=hashlib.sha256(existing_transcript + append_bytes).hexdigest(),
            ),
        )
        next_state_document = state_document(next_state)
        next_state_bytes = state_bytes(next_state)
        relative_screenshot = screenshot_path.absolute().relative_to(self.root).as_posix()
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

    def _recover_pending(
        self,
        *,
        scope: ArchiveOwnershipScope,
        account_id: str,
        castle: CastleIdentity,
        channel: ChatChannel,
    ) -> ChatRecoveryResult | None:
        """Finishes one published pending record exactly once or fails closed."""

        self._validate_control_file(scope.pending_path, allow_missing=True)
        if not scope.pending_path.exists():
            return None
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
        self._validate_chat_directory(directory)
        self._validate_chat_file(transcript_path, allowed_names={"transcript.log"}, allow_missing=True)
        self._validate_chat_file(state_path, allowed_names={"state.json"}, allow_missing=True)
        if screenshot_path.parent != (directory / "screenshots").absolute():
            raise ChatArchiveConsistencyError("Chat pending screenshot path does not match its recorded stream and day.")
        try:
            self._validate_managed_file(screenshot_path, allow_missing=False)
        except ArchiveOwnershipError as error:
            raise ChatArchiveConsistencyError("Chat pending screenshot path is not a safe managed file.") from error
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
        status = _validate_pending_transcript_evidence(transcript_path, transaction)
        if next_state:
            if status != "complete":
                raise ChatArchiveConsistencyError("Chat target state is published before its complete transcript append.")
            self._flush_validated_transcript(transcript_path)
            self._retire_pending(scope.pending_path)
            return ChatRecoveryResult(
                archive_day=transaction.archive_day,
                captured_at=transaction.captured_at,
                snapshot=_state_from_document(transaction.next_state).snapshot,
                transcript_path=transcript_path,
                state_path=state_path,
            )
        if status != "complete":
            self._append_pending_bytes(transcript_path, transaction)
        else:
            self._flush_validated_transcript(transcript_path)
        atomic_write_bytes(state_path, canonical_json_bytes(transaction.next_state), prefix="state-", suffix=".tmp")
        self._fault("after_state_publish")
        self._retire_pending(scope.pending_path)
        return ChatRecoveryResult(
            archive_day=transaction.archive_day,
            captured_at=transaction.captured_at,
            snapshot=_state_from_document(transaction.next_state).snapshot,
            transcript_path=transcript_path,
            state_path=state_path,
        )

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
            self._validate_chat_file(transcript_path, allowed_names={"transcript.log"}, allow_missing=True)
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

    def _flush_validated_transcript(self, transcript_path: Path) -> None:
        """Re-flushes complete bytes before state publication or journal retirement."""

        with transcript_path.open("r+b", buffering=0) as handle:
            handle.flush()
            os.fsync(handle.fileno())
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
            local_day=captured_at.astimezone().date().isoformat(),
        )

    def _build_directory_for_local_day(self, *, account_id: str, castle: CastleIdentity, channel: ChatChannel, local_day: str) -> Path:
        """Builds the canonical archive directory for one already-resolved local day."""

        try:
            local_day = parse_archive_day(local_day)
        except ChatArchiveSchemaError as error:
            raise ChatArchiveConsistencyError("Chat archive day is not a valid calendar date.") from error
        return self.root / local_day / format_account_artifact_directory(account_id=account_id) / format_castle_artifact_directory(
            kingdom=castle.kingdom,
            castle_name=castle.castle_name,
        ) / chat_channel_archive_directory(channel)

    def _load_state(self, state_path: Path, *, transcript_path: Path, archive_day: str) -> ChatArchiveState | None:
        """Loads and strictly validates one complete persisted state document."""

        try:
            parse_archive_day(archive_day)
        except ChatArchiveSchemaError as error:
            raise ChatArchiveConsistencyError("Chat archive day is not a valid calendar date.") from error
        try:
            self._validate_chat_file(state_path, allowed_names={"state.json"}, allow_missing=True)
            self._validate_chat_file(transcript_path, allowed_names={"transcript.log"}, allow_missing=True)
        except ArchiveOwnershipError as error:
            raise ChatArchiveConsistencyError("Chat archive state or transcript path is not a safe managed path.") from error
        if not state_path.exists():
            if transcript_path.exists():
                raise ChatArchiveConsistencyError("Chat archive transcript exists without a validating state document.")
            return None
        try:
            decoded = decode_state_document(decode_json_object(state_path.read_bytes(), field_name="state"), allow_legacy=True)
            state = decoded.state
            if decoded.legacy:
                if state.snapshot.entries:
                    evidence = _read_complete_transcript_evidence(transcript_path)
                    state = ChatArchiveState(
                        snapshot=state.snapshot,
                        last_captured_at=state.last_captured_at,
                        gap_detected=state.gap_detected,
                        transcript_evidence=evidence,
                    )
                elif transcript_path.exists():
                    raise ChatArchiveConsistencyError("Legacy empty chat state has an unexpected target-day transcript.")
            else:
                _validate_state_transcript_evidence(state, transcript_path)
            return state
        except (OSError, ChatArchiveSchemaError, ValueError, TypeError) as error:
            raise ChatArchiveConsistencyError("Chat archive state is malformed.") from error

    def _write_state(self, state_path: Path, state: ChatArchiveState) -> None:
        self._validate_chat_file(state_path, allowed_names={"state.json"}, allow_missing=True)
        atomic_write_bytes(state_path, state_bytes(state), prefix="state-", suffix=".tmp")

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

        if not isinstance(screenshot_extension, str):
            raise ChatArchiveConsistencyError("Chat screenshot extension must be a safe filename segment.")
        if screenshot_extension == "":
            extension = "png"
        elif screenshot_extension.startswith("."):
            extension = screenshot_extension[1:]
        else:
            extension = screenshot_extension
        if re.fullmatch(r"[A-Za-z0-9]{1,16}", extension) is None:
            raise ChatArchiveConsistencyError("Chat screenshot extension must be a safe filename segment.")
        if not isinstance(snapshot.fingerprint, str) or re.fullmatch(r"[0-9a-f]{8}", snapshot.fingerprint) is None:
            raise ChatArchiveConsistencyError("Chat snapshot fingerprint is not a canonical filename identity.")
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
        self._validate_chat_directory(directory)
        validate_managed_path(self.root, screenshots_directory, allow_missing_leaf=True)
        screenshots_directory.mkdir(parents=True, exist_ok=True)
        validate_managed_path(self.root, screenshots_directory, require_directory=True)
        candidate = screenshots_directory / f"{captured_at.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}_{snapshot.fingerprint}.{extension}"
        digest = hashlib.sha256(screenshot_payload).hexdigest()
        for suffix in range(10000):
            selected = candidate if suffix == 0 else screenshots_directory / f"{candidate.stem}-{suffix}{candidate.suffix}"
            self._validate_managed_file(selected, allow_missing=True)
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
        if (
            captured_at == previous_state.last_captured_at
            and not _equal_timestamp_observation_is_allowed(previous_state.snapshot, snapshot)
        ):
            raise ChatArchiveConsistencyError("Chat observation timestamp is reused with different content.")

    def _validate_chat_directory(self, directory: Path) -> None:
        try:
            validate_chat_archive_directory(self.root, directory, allow_missing=True)
        except ArchiveOwnershipError as error:
            raise ChatArchiveConsistencyError("Chat archive directory is not a safe canonical path.") from error

    def _validate_chat_file(self, path: Path, *, allowed_names: set[str], allow_missing: bool) -> None:
        try:
            validate_chat_archive_file(self.root, path, allowed_names=allowed_names, allow_missing=allow_missing)
        except ArchiveOwnershipError as error:
            raise ChatArchiveConsistencyError("Chat archive file is not a safe canonical path.") from error

    def _validate_control_file(self, path: Path, *, allow_missing: bool) -> None:
        try:
            validate_managed_path(self.root, path, allow_missing_leaf=allow_missing, require_file=not allow_missing)
        except ArchiveOwnershipError as error:
            raise ChatArchiveConsistencyError("Chat archive control path is not safe.") from error

    def _validate_managed_file(self, path: Path, *, allow_missing: bool) -> None:
        try:
            validate_managed_path(self.root, path, allow_missing_leaf=allow_missing, require_file=not allow_missing)
        except ArchiveOwnershipError as error:
            raise ChatArchiveConsistencyError("Chat archive managed path is not safe.") from error


def _state_from_document(document: dict[str, Any]) -> ChatArchiveState:
    return decode_state_document(document, allow_legacy=True).state


def _validate_state_bytes(payload: bytes) -> None:
    decode_state_document(decode_json_object(payload, field_name="state"), allow_legacy=False)


def _read_complete_transcript_evidence(path: Path) -> ChatTranscriptEvidence:
    """Validates and fingerprints one legacy transcript before state upgrade."""

    if not path.exists() or not path.is_file():
        raise ChatArchiveConsistencyError("Legacy chat state claims history but its transcript is missing.")
    data = path.read_bytes()
    _validate_transcript_bytes(data)
    return ChatTranscriptEvidence(exists=True, length=len(data), sha256=hashlib.sha256(data).hexdigest())


def _validate_state_transcript_evidence(state: ChatArchiveState | dict[str, Any], transcript_path: Path) -> None:
    """Checks target-day transcript bytes against the canonical state evidence."""

    typed_state = state if isinstance(state, ChatArchiveState) else _state_from_document(state)
    evidence = typed_state.transcript_evidence
    if evidence is None:
        if transcript_path.exists():
            raise ChatArchiveConsistencyError("Chat state declares no target-day transcript, but transcript bytes exist.")
        return
    if not transcript_path.exists() or not transcript_path.is_file():
        raise ChatArchiveConsistencyError("Chat state transcript evidence points to a missing transcript.")
    data = transcript_path.read_bytes()
    _validate_transcript_bytes(data)
    if len(data) != evidence.length or hashlib.sha256(data).hexdigest() != evidence.sha256:
        raise ChatArchiveConsistencyError("Chat state transcript evidence does not match the committed transcript.")


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


def _equal_timestamp_observation_is_allowed(previous: VisibleChatSnapshot, current: VisibleChatSnapshot) -> bool:
    """Allows only normalized repeats and empty observations retaining history."""

    if _entries_match(previous.entries, current.entries):
        return True
    return bool(previous.entries) and not current.entries


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


def _validate_pending_transcript_evidence(path: Path, transaction: PendingChatTransaction) -> str:
    """Validates the complete next transcript and state evidence before any recovery write."""

    status = _classify_transcript(path, transaction)
    current = path.read_bytes() if path.exists() else b""
    prefix = current[: transaction.previous_offset]
    expected = prefix + transaction.append_bytes
    expected_length = transaction.previous_offset + transaction.append_length
    if len(expected) != expected_length:
        raise ChatArchiveConsistencyError("Chat pending transcript evidence length is inconsistent with its append.")
    _validate_transcript_bytes(expected)
    next_state = _state_from_document(transaction.next_state)
    evidence = next_state.transcript_evidence
    if evidence is None:
        raise ChatArchiveConsistencyError("Chat pending next state does not identify transcript evidence.")
    expected_sha256 = hashlib.sha256(expected).hexdigest()
    if evidence.length != expected_length or evidence.sha256 != expected_sha256:
        raise ChatArchiveConsistencyError("Chat pending next state transcript evidence does not match the validated append.")
    return status


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


def _require_non_empty_chat_value(value: object, *, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ChatArchiveSchemaError(f"Chat archive state field '{field_name}' must be a non-empty string.")


def _require_non_negative_int(value: object, *, field_name: str) -> int:
    if type(value) is int and value >= 0:
        return value
    raise ChatArchiveSchemaError(f"Chat archive state field '{field_name}' must be a non-negative integer.")


def _validate_captured_at(captured_at: object) -> None:
    """Rejects timestamps that cannot be represented consistently by archive codecs."""

    if not isinstance(captured_at, datetime) or captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ChatArchiveConsistencyError("Chat captured_at must be an aware datetime.")
