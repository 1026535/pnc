"""Generic naming helpers for stable persisted artifact paths."""

from __future__ import annotations

import re

from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


def format_account_artifact_directory(*, account_id: str) -> str:
    """Formats the per-account artifact directory from the canonical account id."""

    return to_snake_case_artifact_segment(account_id)


def to_snake_case_artifact_segment(value: str) -> str:
    """Converts a human-readable identifier into a lowercase snake_case artifact segment."""

    with_word_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    cleaned = sanitize_artifact_segment(with_word_boundaries)
    collapsed = re.sub(r"_+", "_", cleaned)
    return collapsed.lower()
