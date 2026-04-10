"""Runtime artifact persistence for world-map movement calibration reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


@dataclass(frozen=True, slots=True)
class StoredWorldMapMovementCalibrationReport:
    """Describes one persisted world-map movement calibration report."""

    path: Path
    document: dict[str, object]


@dataclass(slots=True)
class WorldMapMovementCalibrationStore:
    """Owns the runtime artifact layout for persisted world-map movement calibration reports."""

    root: Path

    def __post_init__(self) -> None:
        """Ensures the runtime artifact root exists before use."""

        self.root.mkdir(parents=True, exist_ok=True)

    def persist(
        self,
        *,
        artifact_directory: str,
        label: str,
        captured_at: datetime,
        document: dict[str, object],
    ) -> StoredWorldMapMovementCalibrationReport:
        """Writes one JSON-ready calibration report under the runtime artifact tree."""

        directory = (
            self.root
            / captured_at.astimezone(UTC).strftime("%Y-%m-%d")
            / sanitize_artifact_segment(artifact_directory)
            / "world_map_movement_calibration"
        )
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{captured_at.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}_{sanitize_artifact_segment(label)}.json"
        path = directory / filename
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )
        return StoredWorldMapMovementCalibrationReport(path=path, document=document)
