"""Durable archive persistence for collected mail threads."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from pnc_automation.artifact_naming import sanitize_artifact_segment
from pnc_automation.pnc.mail import MailArchiveMode, MailArchiveRecord, thread_partner_directory_name


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
    """Owns canonical mail archive layout, deduplication, and payload persistence."""

    root: Path

    def __post_init__(self) -> None:
        """Ensures the archive root exists before use."""

        self.root.mkdir(parents=True, exist_ok=True)

    def has_fingerprint(
        self,
        *,
        active_castle: str,
        mailbox_type: str,
        fingerprint: str,
    ) -> bool:
        """Returns whether the canonical archive already contains the requested fingerprint."""

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
        """Persists one canonical archive payload or reuses the existing record when dedup applies."""

        existing_directory = self._find_existing_directory(
            active_castle=record.active_castle,
            mailbox_type=record.mailbox_type.value,
            fingerprint=record.fingerprint.value,
        )
        if existing_directory is not None and skip_existing:
            return StoredMailArchiveRecord(
                record=record,
                directory=existing_directory,
                metadata_path=existing_directory / "metadata.json",
                thread_text_path=(existing_directory / "thread.txt") if (existing_directory / "thread.txt").is_file() else None,
                screenshot_path=(existing_directory / "thread.png") if (existing_directory / "thread.png").is_file() else None,
                created=False,
            )
        directory = self._build_directory(record)
        directory.mkdir(parents=True, exist_ok=True)
        metadata_path = directory / "metadata.json"
        thread_text_path: Path | None = None
        screenshot_path: Path | None = None
        metadata_path.write_text(
            json.dumps(
                {
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
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        if archive_mode in {MailArchiveMode.TEXT, MailArchiveMode.BOTH}:
            thread_text_path = directory / "thread.txt"
            thread_text_path.write_text(record.normalized_thread_text, encoding="utf-8")
        if archive_mode in {MailArchiveMode.SCREENSHOT, MailArchiveMode.BOTH} and screenshot_source_path is not None:
            screenshot_path = directory / "thread.png"
            shutil.copyfile(screenshot_source_path, screenshot_path)
        return StoredMailArchiveRecord(
            record=record,
            directory=directory,
            metadata_path=metadata_path,
            thread_text_path=thread_text_path,
            screenshot_path=screenshot_path,
            created=True,
        )

    def _build_directory(self, record: MailArchiveRecord) -> Path:
        """Builds the canonical archive directory path for one mail record."""

        date_directory = record.captured_at.strftime("%Y-%m-%d")
        timestamp_prefix = record.captured_at.strftime("%Y%m%dT%H%M%SZ")
        fingerprint_segment = f"{timestamp_prefix}_{record.fingerprint.value}"
        return (
            self.root
            / date_directory
            / sanitize_artifact_segment(record.active_castle)
            / record.mailbox_type.value
            / thread_partner_directory_name(record.sender_name)
            / fingerprint_segment
        )

    def _find_existing_directory(
        self,
        *,
        active_castle: str,
        mailbox_type: str,
        fingerprint: str,
    ) -> Path | None:
        """Returns the existing archive directory for one canonical fingerprint when present."""

        castle_segment = sanitize_artifact_segment(active_castle)
        search_root = self.root
        if not search_root.exists():
            return None
        pattern = f"*/{castle_segment}/{mailbox_type}/*/*_{fingerprint}"
        matches = sorted(search_root.glob(pattern))
        return matches[0] if matches else None
