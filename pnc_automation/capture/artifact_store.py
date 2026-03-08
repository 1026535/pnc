"""Persisted artifact storage for screenshots and diagnostics."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """Describes one persisted artifact on disk."""

    path: Path
    label: str
    captured_at: datetime
    size_bytes: int
    sha256: str


@dataclass(slots=True)
class ArtifactStore:
    """Owns canonical artifact path creation and byte persistence."""

    root: Path

    def __post_init__(self) -> None:
        """Ensures the root directory exists before use."""

        self.root.mkdir(parents=True, exist_ok=True)

    def persist_bytes(self, *, account_id: str, label: str, extension: str, payload: bytes) -> ArtifactRecord:
        """Writes one artifact to disk and returns its metadata."""

        captured_at = datetime.now(tz=UTC)
        account_directory = self.root / captured_at.strftime("%Y-%m-%d") / _sanitize_path_segment(account_id)
        account_directory.mkdir(parents=True, exist_ok=True)

        filename = f"{captured_at.strftime('%Y%m%dT%H%M%SZ')}_{_sanitize_path_segment(label)}.{extension.lstrip('.')}"
        path = account_directory / filename
        path.write_bytes(payload)

        return ArtifactRecord(
            path=path,
            label=label,
            captured_at=captured_at,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )


def _sanitize_path_segment(value: str) -> str:
    """Produces a stable filesystem-safe artifact path segment."""

    cleaned = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)
    return cleaned.strip("_") or "artifact"
