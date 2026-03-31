"""Shared direct-input helpers for building-upgrade priority sources."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pnc_automation.pnc.building_catalog import default_building_upgrade_priority


def resolve_building_priority_names(
    *,
    priority: Sequence[str] | None,
    priority_file: str | Path | None,
) -> list[str] | None:
    """Returns one explicit building-priority list from direct values or a newline-delimited file."""

    if priority is not None and priority_file is not None:
        raise ValueError("Building priority input accepts either direct priority values or one priority_file, not both.")
    if priority is not None:
        return list(priority)
    if priority_file is None:
        return None
    path = Path(priority_file)
    entries = _parse_building_priority_file(path)
    if not entries:
        raise ValueError(f"Building priority file '{path}' did not contain any building ids.")
    return entries


def resolve_building_priority_values(
    *,
    priority: Sequence[str] | None,
    priority_file: str | Path | None,
    default_priority: Sequence[str] | None = None,
) -> list[str]:
    """Returns the canonical ordered building-priority list, including defaults when no input was provided."""

    resolved_priority = resolve_building_priority_names(
        priority=_normalize_priority_sequence(priority, field_name="priority"),
        priority_file=_normalize_priority_file(priority_file),
    )
    if resolved_priority is not None:
        return resolved_priority
    fallback_priority = default_building_priority_names() if default_priority is None else default_priority
    normalized_default_priority = _normalize_priority_sequence(fallback_priority, field_name="default_priority")
    if normalized_default_priority is None:
        raise ValueError("Building priority resolution requires at least one default priority value.")
    return normalized_default_priority


def _parse_building_priority_file(path: Path) -> list[str]:
    """Parses one UTF-8 text file into the ordered building ids it declares."""

    entries: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line == "":
            continue
        for segment in line.split(","):
            entry = segment.strip()
            if entry != "":
                entries.append(entry)
    return entries


def default_building_priority_names() -> list[str]:
    """Returns the canonical default ordered building priorities as raw string ids."""

    return [home_city_object_id.value for home_city_object_id in default_building_upgrade_priority()]


def _normalize_priority_sequence(priority: Sequence[str] | None, *, field_name: str) -> list[str] | None:
    """Returns one validated priority list while rejecting ambiguous string or mixed-type inputs."""

    if priority is None:
        return None
    if isinstance(priority, str):
        raise TypeError(f"Expected '{field_name}' to be a sequence of strings, not one string.")
    entries: list[str] = []
    for item in priority:
        if not isinstance(item, str):
            raise TypeError(f"Expected '{field_name}' entries to be strings.")
        entries.append(item)
    return entries


def _normalize_priority_file(priority_file: str | Path | None) -> str | Path | None:
    """Returns one validated priority-file value or fails fast for unsupported types."""

    if priority_file is None or isinstance(priority_file, str | Path):
        return priority_file
    raise TypeError("Expected 'priority_file' to be a string or Path.")
