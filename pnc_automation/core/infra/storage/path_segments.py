"""Generic filesystem-safe path-segment helpers."""

from __future__ import annotations


def sanitize_artifact_segment(value: str) -> str:
    """Produces a stable filesystem-safe artifact path segment."""

    cleaned = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)
    return cleaned.strip("_") or "artifact"

