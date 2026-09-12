"""Durable, payload-first persistence for collected mail threads."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pnc_automation.app.pnc.domain.mail import (
    MailArchiveMode,
    MailArchiveRecord,
    MailThreadFingerprint,
    compute_mail_thread_fingerprint,
    thread_partner_directory_name,
)
from pnc_automation.app.pnc.enums.mail import MailboxType
from pnc_automation.app.pnc.persistence.archive_ownership import (
    ArchiveOwnershipError,
    mail_archive_scope,
    validate_managed_path,
)
from pnc_automation.core.infra.storage.atomic_file import atomic_write_bytes
from pnc_automation.core.infra.storage.file_lock import NativePathLockManager
from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


class MailArchiveStorageError(RuntimeError):
    """Raised when a mail archive cannot prove a complete matching record."""


class MailArchiveCandidateStatus(StrEnum):
    """Content-free classification used while inspecting mail candidates."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    CORRUPT = "corrupt"
    CONTRADICTORY = "contradictory"


@dataclass(frozen=True, slots=True)
class MailArchiveCandidateDiagnostic:
    """Identifies one candidate disposition without exposing metadata or payload content."""

    candidate_name: str
    status: MailArchiveCandidateStatus


@dataclass(frozen=True, slots=True)
class _MailArchiveCandidateClassification:
    """Carries candidate diagnostics plus selection-only verification state."""

    status: MailArchiveCandidateStatus
    versioned_verified: bool = False


@dataclass(frozen=True, slots=True)
class StoredMailArchiveRecord:
    """Describes one archive record persisted or resolved from an existing fingerprint."""

    record: MailArchiveRecord
    directory: Path
    metadata_path: Path
    thread_text_path: Path | None
    screenshot_path: Path | None
    created: bool


@dataclass(slots=True)
class MailArchiveStore:
    """Owns canonical mail layout, completion validation, locking, and payload persistence."""

    root: Path
    lock_manager: NativePathLockManager = field(default_factory=NativePathLockManager, repr=False)
    _last_candidate_diagnostics: tuple[MailArchiveCandidateDiagnostic, ...] = field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        """Resolves and creates the durable mail archive root."""

        self.root = self.root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def last_candidate_diagnostics(self) -> tuple[MailArchiveCandidateDiagnostic, ...]:
        """Returns content-free dispositions from the most recent fingerprint inspection."""

        return self._last_candidate_diagnostics

    def has_fingerprint(self, *, active_castle: str, mailbox_type: str, fingerprint: str) -> bool:
        """Returns whether one fully validated legacy or versioned capture exists."""

        scope = mail_archive_scope(
            self.root,
            active_castle=active_castle,
            mailbox_type=mailbox_type,
            fingerprint=fingerprint,
            lock_manager=self.lock_manager,
        )
        with scope.lock():
            return self._find_existing_directory(
                active_castle=active_castle,
                mailbox_type=mailbox_type,
                fingerprint=fingerprint,
            ) is not None

    def persist(
        self,
        *,
        record: MailArchiveRecord,
        archive_mode: MailArchiveMode,
        screenshot_source_path: Path | None = None,
        skip_existing: bool = True,
    ) -> StoredMailArchiveRecord:
        """Publishes all required payloads before the completion metadata marker."""

        if not isinstance(archive_mode, MailArchiveMode):
            raise TypeError("MailArchiveStore.archive_mode must be a MailArchiveMode.")
        _validate_record_for_persistence(record)
        requires_screenshot = archive_mode in {MailArchiveMode.SCREENSHOT, MailArchiveMode.BOTH}
        scope = mail_archive_scope(
            self.root,
            active_castle=record.active_castle,
            mailbox_type=record.mailbox_type.value,
            fingerprint=record.fingerprint.value,
            lock_manager=self.lock_manager,
        )
        with scope.lock():
            existing_directory = self._find_existing_directory(
                active_castle=record.active_castle,
                mailbox_type=record.mailbox_type.value,
                fingerprint=record.fingerprint.value,
            )
            if existing_directory is not None and skip_existing:
                return self._stored_record(record, existing_directory, created=False)
            screenshot_bytes: bytes | None = None
            if requires_screenshot:
                if screenshot_source_path is None or not screenshot_source_path.is_file():
                    raise MailArchiveStorageError("Mail screenshot archive mode requires an existing source payload.")
                screenshot_bytes = screenshot_source_path.read_bytes()
                if not screenshot_bytes:
                    raise MailArchiveStorageError("Mail screenshot archive mode requires a non-empty source payload.")
            text_bytes = (
                record.normalized_thread_text.encode("utf-8")
                if archive_mode in {MailArchiveMode.TEXT, MailArchiveMode.BOTH}
                else None
            )
            directory = self._allocate_directory(record)
            directory.mkdir(parents=True, exist_ok=False)
            try:
                validate_managed_path(self.root, directory, require_directory=True)
            except ArchiveOwnershipError as error:
                raise MailArchiveStorageError("Mail archive destination became an unsafe managed path.") from error
            thread_text_path: Path | None = None
            screenshot_path: Path | None = None
            if text_bytes is not None:
                thread_text_path = directory / "thread.txt"
                validate_managed_path(self.root, thread_text_path, allow_missing_leaf=True)
                atomic_write_bytes(thread_text_path, text_bytes, prefix="thread-", suffix=".tmp")
            if screenshot_bytes is not None:
                screenshot_path = directory / "thread.png"
                validate_managed_path(self.root, screenshot_path, allow_missing_leaf=True)
                atomic_write_bytes(screenshot_path, screenshot_bytes, prefix="screenshot-", suffix=".tmp")
            metadata = self._metadata_document(
                record=record,
                archive_mode=archive_mode,
                thread_text_path=thread_text_path,
                screenshot_path=screenshot_path,
            )
            metadata_path = directory / "metadata.json"
            validate_managed_path(self.root, metadata_path, allow_missing_leaf=True)
            atomic_write_bytes(
                metadata_path,
                (json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                prefix="metadata-",
                suffix=".tmp",
            )
            return StoredMailArchiveRecord(
                record=record,
                directory=directory,
                metadata_path=directory / "metadata.json",
                thread_text_path=thread_text_path,
                screenshot_path=screenshot_path,
                created=True,
            )

    def _stored_record(self, record: MailArchiveRecord, directory: Path, *, created: bool) -> StoredMailArchiveRecord:
        return StoredMailArchiveRecord(
            record=record,
            directory=directory,
            metadata_path=directory / "metadata.json",
            thread_text_path=(directory / "thread.txt") if (directory / "thread.txt").is_file() else None,
            screenshot_path=(directory / "thread.png") if (directory / "thread.png").is_file() else None,
            created=created,
        )

    def _metadata_document(
        self,
        *,
        record: MailArchiveRecord,
        archive_mode: MailArchiveMode,
        thread_text_path: Path | None,
        screenshot_path: Path | None,
    ) -> dict[str, Any]:
        manifest: list[dict[str, Any]] = []
        for path in (thread_text_path, screenshot_path):
            if path is None:
                continue
            manifest.append(
                {
                    "path": path.name,
                    "length": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
        return {
            "schema_version": 2,
            "archive_mode": archive_mode.value,
            "account_id": record.account_id,
            "pnc_account_id": record.pnc_account_id,
            "active_castle": record.active_castle,
            "mailbox_type": record.mailbox_type.value,
            "sender_name": record.sender_name,
            "thread_timestamp_text": record.thread_timestamp_text,
            "fingerprint": record.fingerprint.value,
            "captured_at": record.captured_at.isoformat(),
            "normalized_thread_text": record.normalized_thread_text,
            "source_artifact_paths": [str(path) for path in record.source_artifact_paths],
            "manifest": manifest,
        }

    def _allocate_directory(self, record: MailArchiveRecord) -> Path:
        base = self._build_directory(record)
        try:
            validate_managed_path(self.root, base.parent, allow_missing_leaf=True)
        except ArchiveOwnershipError as error:
            raise MailArchiveStorageError("Mail archive destination has an unsafe managed path.") from error
        for suffix in range(10000):
            candidate = base if suffix == 0 else base.with_name(f"{base.name}-{suffix}")
            if os.path.lexists(candidate):
                try:
                    validate_managed_path(self.root, candidate, require_directory=True)
                except ArchiveOwnershipError as error:
                    raise MailArchiveStorageError("Mail archive destination has an unsafe managed path.") from error
                continue
            try:
                validate_managed_path(self.root, candidate, allow_missing_leaf=True)
            except ArchiveOwnershipError as error:
                raise MailArchiveStorageError("Mail archive destination has an unsafe managed path.") from error
            if not os.path.lexists(candidate):
                return candidate
        raise MailArchiveStorageError("Unable to allocate a collision-safe mail archive directory.")

    def _build_directory(self, record: MailArchiveRecord) -> Path:
        """Builds the canonical archive directory path for one mail record."""

        date_directory = record.captured_at.astimezone(UTC).strftime("%Y-%m-%d")
        timestamp_prefix = record.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        fingerprint_segment = f"{timestamp_prefix}_{record.fingerprint.value}"
        return (
            self.root
            / date_directory
            / sanitize_artifact_segment(record.active_castle)
            / record.mailbox_type.value
            / thread_partner_directory_name(record.sender_name)
            / fingerprint_segment
        )

    def _find_existing_directory(self, *, active_castle: str, mailbox_type: str, fingerprint: str) -> Path | None:
        """Finds only a candidate whose identity and required payloads validate."""

        castle_segment = sanitize_artifact_segment(active_castle)
        if not self.root.exists():
            self._last_candidate_diagnostics = ()
            return None
        candidates: list[tuple[Path, bool]] = []
        diagnostics: list[MailArchiveCandidateDiagnostic] = []
        pattern = re.compile(rf"^\d{{8}}T\d{{6}}Z_{re.escape(fingerprint)}(?:-\d+)?$")
        for metadata_path in self.root.rglob("metadata.json"):
            directory = metadata_path.parent
            if directory.name == ".archive-control" or not pattern.fullmatch(directory.name):
                continue
            relative = directory.relative_to(self.root).parts
            if (
                len(relative) != 5
                or os.path.normcase(relative[1]) != os.path.normcase(castle_segment)
                or os.path.normcase(relative[2]) != os.path.normcase(mailbox_type)
            ):
                continue
            try:
                validate_managed_path(self.root, directory, require_directory=True)
                classification = _classify_candidate(
                    directory,
                    active_castle=active_castle,
                    mailbox_type=mailbox_type,
                    fingerprint=fingerprint,
                    root=self.root,
                )
            except ArchiveOwnershipError:
                classification = _MailArchiveCandidateClassification(MailArchiveCandidateStatus.CORRUPT)
            status = classification.status
            diagnostics.append(MailArchiveCandidateDiagnostic(candidate_name=directory.name, status=status))
            if status == MailArchiveCandidateStatus.COMPLETE:
                candidates.append((directory, classification.versioned_verified))
        self._last_candidate_diagnostics = tuple(sorted(diagnostics, key=lambda item: item.candidate_name))
        return min(candidates, key=lambda item: (not item[1], item[0].as_posix()))[0] if candidates else None


def _classify_candidate(
    directory: Path,
    *,
    active_castle: str,
    mailbox_type: str,
    fingerprint: str,
    root: Path,
) -> _MailArchiveCandidateClassification:
    metadata_path = directory / "metadata.json"
    try:
        validate_managed_path(root, metadata_path, require_file=True)
        metadata = _read_json_object(metadata_path.read_bytes())
    except (ArchiveOwnershipError, OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return _MailArchiveCandidateClassification(MailArchiveCandidateStatus.CORRUPT)
    try:
        if not (
            isinstance(metadata.get("active_castle"), str)
            and os.path.normcase(metadata["active_castle"]) == os.path.normcase(active_castle)
            and isinstance(metadata.get("mailbox_type"), str)
            and os.path.normcase(metadata["mailbox_type"]) == os.path.normcase(mailbox_type)
            and metadata.get("fingerprint") == fingerprint
        ):
            return _MailArchiveCandidateClassification(MailArchiveCandidateStatus.CONTRADICTORY)
        if metadata.get("schema_version") == 2:
            status = _classify_versioned_candidate(directory, metadata, root=root)
            return _MailArchiveCandidateClassification(
                status=status,
                versioned_verified=status == MailArchiveCandidateStatus.COMPLETE,
            )
        if "schema_version" in metadata:
            return _MailArchiveCandidateClassification(MailArchiveCandidateStatus.CORRUPT)
        return _MailArchiveCandidateClassification(_classify_legacy_candidate(directory, metadata, root=root))
    except (OSError, UnicodeError, ValueError, TypeError):
        return _MailArchiveCandidateClassification(MailArchiveCandidateStatus.CORRUPT)


def _classify_versioned_candidate(
    directory: Path,
    metadata: dict[str, Any],
    *,
    root: Path,
) -> MailArchiveCandidateStatus:
    expected_keys = {
        "schema_version",
        "archive_mode",
        "account_id",
        "pnc_account_id",
        "active_castle",
        "mailbox_type",
        "sender_name",
        "thread_timestamp_text",
        "fingerprint",
        "captured_at",
        "normalized_thread_text",
        "source_artifact_paths",
        "manifest",
    }
    if set(metadata) != expected_keys or type(metadata.get("schema_version")) is not int or metadata["schema_version"] != 2:
        return MailArchiveCandidateStatus.CORRUPT
    try:
        mode = MailArchiveMode(metadata["archive_mode"])
    except (KeyError, ValueError, TypeError):
        return MailArchiveCandidateStatus.CORRUPT
    if not all(
        isinstance(metadata.get(field), str) and bool(metadata[field].strip())
        for field in ("account_id", "pnc_account_id", "active_castle", "mailbox_type", "sender_name", "fingerprint", "captured_at")
    ) or not isinstance(metadata.get("normalized_thread_text"), str):
        return MailArchiveCandidateStatus.CORRUPT
    if not _valid_fingerprint(metadata["fingerprint"]):
        return MailArchiveCandidateStatus.CORRUPT
    try:
        captured_at = datetime.fromisoformat(metadata["captured_at"])
    except ValueError:
        return MailArchiveCandidateStatus.CORRUPT
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        return MailArchiveCandidateStatus.CORRUPT
    if metadata.get("thread_timestamp_text") is not None and not isinstance(metadata["thread_timestamp_text"], str):
        return MailArchiveCandidateStatus.CORRUPT
    try:
        mailbox = MailboxType(metadata["mailbox_type"])
    except (ValueError, TypeError):
        return MailArchiveCandidateStatus.CORRUPT
    relative = directory.relative_to(root).parts
    directory_match = re.fullmatch(
        r"(?P<timestamp>\d{8}T\d{6}Z)_(?P<fingerprint>[0-9a-f]{8})(?:-\d+)?",
        directory.name,
    )
    expected_captured_at = captured_at.astimezone(UTC)
    expected_fingerprint = compute_mail_thread_fingerprint(
        mailbox_type=mailbox,
        sender_name=metadata["sender_name"],
        timestamp_text=metadata["thread_timestamp_text"],
        normalized_thread_text=metadata["normalized_thread_text"],
    ).value
    if (
        len(relative) != 5
        or relative[0] != expected_captured_at.strftime("%Y-%m-%d")
        or os.path.normcase(relative[1]) != os.path.normcase(sanitize_artifact_segment(metadata["active_castle"]))
        or relative[2] != mailbox.value
        or os.path.normcase(relative[3]) != os.path.normcase(thread_partner_directory_name(metadata["sender_name"]))
        or directory_match is None
        or directory_match.group("timestamp") != expected_captured_at.strftime("%Y%m%dT%H%M%SZ")
        or directory_match.group("fingerprint") != metadata["fingerprint"]
        or metadata["fingerprint"] != expected_fingerprint
    ):
        return MailArchiveCandidateStatus.CONTRADICTORY
    if not isinstance(metadata.get("source_artifact_paths"), list) or not all(isinstance(item, str) for item in metadata["source_artifact_paths"]):
        return MailArchiveCandidateStatus.CORRUPT
    manifest = metadata.get("manifest")
    if not isinstance(manifest, list):
        return MailArchiveCandidateStatus.CORRUPT
    required = {"thread.txt"} if mode == MailArchiveMode.TEXT else {"thread.png"} if mode == MailArchiveMode.SCREENSHOT else {"thread.txt", "thread.png"}
    entries: dict[str, dict[str, Any]] = {}
    for item in manifest:
        if not isinstance(item, dict) or set(item) != {"path", "length", "sha256"}:
            return MailArchiveCandidateStatus.CORRUPT
        path = item.get("path")
        if not isinstance(path, str) or path not in {"thread.txt", "thread.png"}:
            return MailArchiveCandidateStatus.CORRUPT
        if path in entries or type(item.get("length")) is not int or item["length"] < 0 or not _valid_sha(item.get("sha256")):
            return MailArchiveCandidateStatus.CORRUPT
        entries[path] = item
    if set(entries) != required:
        return MailArchiveCandidateStatus.INCOMPLETE
    for name, item in entries.items():
        path = directory / name
        try:
            validate_managed_path(root, path, require_file=True)
        except ArchiveOwnershipError:
            return MailArchiveCandidateStatus.INCOMPLETE
        if not path.is_file() or path.stat().st_size != item["length"] or _sha256_file(path) != item["sha256"]:
            return MailArchiveCandidateStatus.INCOMPLETE
        if name == "thread.png" and item["length"] == 0:
            return MailArchiveCandidateStatus.INCOMPLETE
    text_path = directory / "thread.txt"
    if text_path.is_file():
        try:
            if text_path.read_text(encoding="utf-8") != metadata.get("normalized_thread_text"):
                return MailArchiveCandidateStatus.CORRUPT
        except (OSError, UnicodeDecodeError):
            return MailArchiveCandidateStatus.INCOMPLETE
    return MailArchiveCandidateStatus.COMPLETE


def _classify_legacy_candidate(
    directory: Path,
    metadata: dict[str, Any],
    *,
    root: Path,
) -> MailArchiveCandidateStatus:
    text_path = directory / "thread.txt"
    screenshot_path = directory / "thread.png"
    try:
        text_exists = os.path.lexists(text_path)
        screenshot_exists = os.path.lexists(screenshot_path)
        if text_exists:
            validate_managed_path(root, text_path, require_file=True)
        if screenshot_exists:
            validate_managed_path(root, screenshot_path, require_file=True)
    except ArchiveOwnershipError:
        return MailArchiveCandidateStatus.CORRUPT
    if not text_path.is_file() and not screenshot_path.is_file():
        return MailArchiveCandidateStatus.INCOMPLETE
    if text_path.is_file():
        try:
            if text_path.stat().st_size == 0 or not isinstance(metadata.get("normalized_thread_text"), str):
                return MailArchiveCandidateStatus.INCOMPLETE
            if text_path.read_text(encoding="utf-8") != metadata["normalized_thread_text"]:
                return MailArchiveCandidateStatus.CORRUPT
        except (OSError, UnicodeDecodeError):
            return MailArchiveCandidateStatus.INCOMPLETE
    if screenshot_path.is_file() and screenshot_path.stat().st_size == 0:
        return MailArchiveCandidateStatus.INCOMPLETE
    return MailArchiveCandidateStatus.COMPLETE


def _read_json_object(payload: bytes) -> dict[str, Any]:
    """Decodes metadata and rejects non-object top-level JSON values."""

    document = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
    if not isinstance(document, dict):
        raise ValueError("Mail metadata must be a JSON object.")
    return document


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not supported in mail metadata.")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(f"Unsupported JSON constant: {value}")


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _valid_fingerprint(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{8}", value) is not None


def _validate_record_for_persistence(record: object) -> None:
    """Validates record identity before control paths, allocation, or payload reads are touched."""

    if not isinstance(record, MailArchiveRecord):
        raise MailArchiveStorageError("Mail archive record must be a MailArchiveRecord.")
    for field_name in ("account_id", "pnc_account_id", "active_castle", "sender_name"):
        value = getattr(record, field_name)
        if not isinstance(value, str) or not value.strip():
            raise MailArchiveStorageError(f"Mail archive record field '{field_name}' must be a non-empty string.")
    if not isinstance(record.mailbox_type, MailboxType):
        raise MailArchiveStorageError("Mail archive record mailbox_type is invalid.")
    if not isinstance(record.fingerprint, MailThreadFingerprint) or not _valid_fingerprint(record.fingerprint.value):
        raise MailArchiveStorageError("Mail archive record fingerprint must be eight lowercase hexadecimal characters.")
    if not isinstance(record.captured_at, datetime) or record.captured_at.tzinfo is None or record.captured_at.utcoffset() is None:
        raise MailArchiveStorageError("Mail archive record captured_at must be an aware datetime.")
    if record.thread_timestamp_text is not None and not isinstance(record.thread_timestamp_text, str):
        raise MailArchiveStorageError("Mail archive record thread_timestamp_text must be text or None.")
    if not isinstance(record.normalized_thread_text, str):
        raise MailArchiveStorageError("Mail archive record normalized_thread_text must be text.")
    if not isinstance(record.source_artifact_paths, tuple) or not all(
        isinstance(path, Path) for path in record.source_artifact_paths
    ):
        raise MailArchiveStorageError("Mail archive record source_artifact_paths must be Path values.")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
