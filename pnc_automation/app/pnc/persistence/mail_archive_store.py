"""Durable, payload-first persistence for collected mail threads."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

from pnc_automation.app.pnc.domain.mail import MailArchiveMode, MailArchiveRecord, thread_partner_directory_name
from pnc_automation.app.pnc.persistence.archive_ownership import mail_archive_scope
from pnc_automation.core.infra.storage.atomic_file import atomic_write_bytes
from pnc_automation.core.infra.storage.file_lock import NativePathLockManager
from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


class MailArchiveStorageError(RuntimeError):
    """Raised when a mail archive cannot prove a complete matching record."""


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

    def __post_init__(self) -> None:
        """Resolves and creates the durable mail archive root."""

        self.root = self.root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

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
        requires_screenshot = archive_mode in {MailArchiveMode.SCREENSHOT, MailArchiveMode.BOTH}
        screenshot_bytes: bytes | None = None
        if requires_screenshot:
            if screenshot_source_path is None or not screenshot_source_path.is_file():
                raise MailArchiveStorageError("Mail screenshot archive mode requires an existing source payload.")
            screenshot_bytes = screenshot_source_path.read_bytes()
        text_bytes = record.normalized_thread_text.encode("utf-8") if archive_mode in {MailArchiveMode.TEXT, MailArchiveMode.BOTH} else None
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
            directory = self._allocate_directory(record)
            directory.mkdir(parents=True, exist_ok=False)
            thread_text_path: Path | None = None
            screenshot_path: Path | None = None
            if text_bytes is not None:
                thread_text_path = directory / "thread.txt"
                atomic_write_bytes(thread_text_path, text_bytes, prefix="thread-", suffix=".tmp")
            if screenshot_bytes is not None:
                screenshot_path = directory / "thread.png"
                atomic_write_bytes(screenshot_path, screenshot_bytes, prefix="screenshot-", suffix=".tmp")
            metadata = self._metadata_document(
                record=record,
                archive_mode=archive_mode,
                thread_text_path=thread_text_path,
                screenshot_path=screenshot_path,
            )
            atomic_write_bytes(
                directory / "metadata.json",
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
        for suffix in range(10000):
            candidate = base if suffix == 0 else base.with_name(f"{base.name}-{suffix}")
            if not candidate.exists():
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
            return None
        candidates = []
        pattern = re.compile(rf"^\d{{8}}T\d{{6}}Z_{re.escape(fingerprint)}(?:-\d+)?$")
        for metadata_path in self.root.rglob("metadata.json"):
            directory = metadata_path.parent
            if directory.name == ".archive-control" or not pattern.fullmatch(directory.name):
                continue
            relative = directory.relative_to(self.root).parts
            if len(relative) != 5 or relative[1] != castle_segment or relative[2] != mailbox_type:
                continue
            status = _classify_candidate(
                directory,
                active_castle=active_castle,
                mailbox_type=mailbox_type,
                fingerprint=fingerprint,
            )
            if status == "complete":
                candidates.append(directory)
        return sorted(candidates)[0] if candidates else None


def _classify_candidate(directory: Path, *, active_castle: str, mailbox_type: str, fingerprint: str) -> str:
    metadata_path = directory / "metadata.json"
    try:
        metadata = _read_json_object(metadata_path.read_bytes())
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return "invalid"
    if any(metadata.get(field) != expected for field, expected in {
        "active_castle": active_castle,
        "mailbox_type": mailbox_type,
        "fingerprint": fingerprint,
    }.items()):
        return "contradictory"
    if metadata.get("schema_version") == 2:
        return _classify_versioned_candidate(directory, metadata)
    if "schema_version" in metadata:
        return "invalid"
    return _classify_legacy_candidate(directory, metadata)


def _classify_versioned_candidate(directory: Path, metadata: dict[str, Any]) -> str:
    if type(metadata.get("schema_version")) is not int or metadata["schema_version"] != 2:
        return "invalid"
    try:
        mode = MailArchiveMode(metadata["archive_mode"])
    except (KeyError, ValueError, TypeError):
        return "invalid"
    manifest = metadata.get("manifest")
    if not isinstance(manifest, list):
        return "invalid"
    required = {"thread.txt"} if mode == MailArchiveMode.TEXT else {"thread.png"} if mode == MailArchiveMode.SCREENSHOT else {"thread.txt", "thread.png"}
    entries: dict[str, dict[str, Any]] = {}
    for item in manifest:
        if not isinstance(item, dict) or set(item) != {"path", "length", "sha256"}:
            return "invalid"
        path = item.get("path")
        if not isinstance(path, str) or path not in {"thread.txt", "thread.png"}:
            return "invalid"
        if path in entries or type(item.get("length")) is not int or item["length"] < 0 or not _valid_sha(item.get("sha256")):
            return "invalid"
        entries[path] = item
    if set(entries) != required:
        return "incomplete"
    for name, item in entries.items():
        path = directory / name
        if not path.is_file() or path.stat().st_size != item["length"] or _sha256_file(path) != item["sha256"]:
            return "incomplete"
    text_path = directory / "thread.txt"
    if text_path.is_file():
        try:
            if text_path.read_text(encoding="utf-8") != metadata.get("normalized_thread_text"):
                return "invalid"
        except (OSError, UnicodeDecodeError):
            return "incomplete"
    return "complete"


def _classify_legacy_candidate(directory: Path, metadata: dict[str, Any]) -> str:
    text_path = directory / "thread.txt"
    screenshot_path = directory / "thread.png"
    if not text_path.is_file() and not screenshot_path.is_file():
        return "incomplete"
    if text_path.is_file():
        try:
            if text_path.read_text(encoding="utf-8") != metadata.get("normalized_thread_text"):
                return "invalid"
        except (OSError, UnicodeDecodeError):
            return "incomplete"
    return "complete"


def _read_json_object(payload: bytes) -> dict[str, Any]:
    return json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
