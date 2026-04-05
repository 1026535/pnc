"""Runtime debug persistence for checkpointed world-map survey snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


@dataclass(frozen=True, slots=True)
class StoredWorldMapSurveyDebugDump:
    """Describes one persisted world-map survey debug dump."""

    path: Path
    document: dict[str, object]


@dataclass(slots=True)
class WorldMapSurveyDebugStore:
    """Owns the runtime artifact layout for checkpointed world-map survey-state debug dumps."""

    root: Path

    def __post_init__(self) -> None:
        """Ensures the runtime artifact root exists before use."""

        self.root.mkdir(parents=True, exist_ok=True)

    def persist(self, document: dict[str, object]) -> StoredWorldMapSurveyDebugDump:
        """Writes one already-exported world-map survey snapshot document under the runtime artifact tree."""

        checkpoint = _require_mapping(document.get("checkpoint"), field_name="checkpoint")
        artifact_directory = _require_non_empty_string(
            checkpoint.get("artifact_directory"),
            field_name="checkpoint.artifact_directory",
        )
        label = _require_non_empty_string(
            checkpoint.get("label"),
            field_name="checkpoint.label",
        )
        captured_at = datetime.fromisoformat(
            _require_non_empty_string(
                checkpoint.get("captured_at"),
                field_name="checkpoint.captured_at",
            )
        )
        directory = (
            self.root
            / captured_at.astimezone(UTC).strftime("%Y-%m-%d")
            / sanitize_artifact_segment(artifact_directory)
            / "world_map_surveys"
        )
        directory.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{captured_at.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}_{sanitize_artifact_segment(label)}.json"
        )
        path = directory / filename
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )
        return StoredWorldMapSurveyDebugDump(path=path, document=document)


def _require_mapping(value: object, *, field_name: str) -> dict[str, Any]:
    """Returns one required mapping field or fails fast when the snapshot is malformed."""

    if isinstance(value, dict):
        return value
    raise ValueError(f"World-map survey debug dump field '{field_name}' must be a mapping.")


def _require_non_empty_string(value: object, *, field_name: str) -> str:
    """Returns one required non-empty string field or fails fast when the snapshot is malformed."""

    if isinstance(value, str) and value.strip() != "":
        return value
    raise ValueError(f"World-map survey debug dump field '{field_name}' must be a non-empty string.")

