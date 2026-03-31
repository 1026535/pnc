"""Canonical naming helpers for persisted automation artifacts."""

from __future__ import annotations

from pnc_automation.core.infra.storage.artifact_naming import to_snake_case_artifact_segment


def format_castle_artifact_directory(*, kingdom: str, castle_name: str) -> str:
    """Formats the per-castle artifact directory as `k###_castle_name`."""

    normalized_kingdom = to_snake_case_artifact_segment(kingdom)
    normalized_castle_name = to_snake_case_artifact_segment(castle_name)
    return f"{normalized_kingdom}_{normalized_castle_name}"
