"""Canonical naming helpers for persisted automation artifacts."""

from __future__ import annotations

import re

from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


def format_account_artifact_directory(*, account_id: str) -> str:
    """Formats the per-account artifact directory from the canonical account id."""

    return _to_snake_case_segment(account_id)


def format_castle_artifact_directory(*, kingdom: str, castle_name: str) -> str:
    """Formats the per-castle artifact directory as `k###_castle_name`."""

    normalized_kingdom = _to_snake_case_segment(kingdom)
    normalized_castle_name = _to_snake_case_segment(castle_name)
    return f"{normalized_kingdom}_{normalized_castle_name}"


def _to_snake_case_segment(value: str) -> str:
    """Converts a human-readable identifier into a lowercase snake_case segment."""

    with_word_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    cleaned = sanitize_artifact_segment(with_word_boundaries)
    collapsed = re.sub(r"_+", "_", cleaned)
    return collapsed.lower()
