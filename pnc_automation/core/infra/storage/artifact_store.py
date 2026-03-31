"""Persisted artifact storage for screenshots and diagnostics."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


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

    def persist_bytes(self, *, artifact_directory: str, label: str, extension: str, payload: bytes) -> ArtifactRecord:
        """Writes one artifact under the provided per-castle directory and returns its metadata."""

        captured_at = datetime.now(tz=UTC)
        artifact_directory_path = self.root / captured_at.strftime("%Y-%m-%d") / sanitize_artifact_segment(artifact_directory)
        artifact_directory_path.mkdir(parents=True, exist_ok=True)

        filename = f"{captured_at.strftime('%Y%m%dT%H%M%SZ')}_{sanitize_artifact_segment(label)}.{extension.lstrip('.')}"
        path = artifact_directory_path / filename
        path.write_bytes(payload)

        return ArtifactRecord(
            path=path,
            label=label,
            captured_at=captured_at,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
