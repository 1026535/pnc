"""Inspector for historical ad-hoc v2 live evidence packages.

The live030 package predates typed results: its ``repr``-style timestamps,
free-form ``summary`` strings, and ``executed`` flags are descriptive only.
This module reports what a v2 file contains without converting any of it into
trusted typed receipts, frame refs, or case results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class V2Inspection:
    """A read-only structural report of one historical v2 document."""

    schema_version: int
    assignment_id: str | None
    candidate_sha: str | None
    case_count: int
    case_ids: tuple[str, ...]
    statuses: dict[str, int]
    physical_totals: dict[str, Any]
    dispatch_count: int
    dispatch_repr_fields: tuple[str, ...]
    warnings: tuple[str, ...]


def inspect_v2_evidence(path: Path) -> V2Inspection:
    """Describes one v2 file's structure; never trusts repr-converted values."""

    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("V2 evidence must be a JSON object.")
    warnings: list[str] = []

    cases = payload.get("cases") or payload.get("case_results") or []
    case_ids: list[str] = []
    statuses: dict[str, int] = {}
    if isinstance(cases, list):
        for entry in cases:
            if not isinstance(entry, dict):
                continue
            case_id = entry.get("case_id") or entry.get("id")
            if isinstance(case_id, str):
                case_ids.append(case_id)
            status = entry.get("status") or entry.get("result")
            if isinstance(status, str):
                statuses[status] = statuses.get(status, 0) + 1
    else:
        warnings.append("v2 'cases' is not a list; nothing structurally inspectable.")

    dispatches = payload.get("dispatches") or payload.get("input_events") or []
    dispatch_repr_fields: list[str] = []
    if isinstance(dispatches, list):
        for entry in dispatches:
            if isinstance(entry, dict):
                for key in entry:
                    if key not in dispatch_repr_fields:
                        dispatch_repr_fields.append(key)
        warnings.append(
            "dispatch rows carry ad-hoc/repr fields only; "
            "they are not trusted typed receipts."
        )

    physical = payload.get("totals") or payload.get("physical") or {}
    if isinstance(physical, dict) and physical:
        warnings.append("v2 totals are self-reported; they are not recomputed here.")

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return V2Inspection(
        schema_version=int(payload.get("schema_version", 2)),
        assignment_id=(
            payload.get("assignment_id")
            or metadata.get("assignment_id")
            if isinstance(payload.get("assignment_id") or metadata.get("assignment_id"), str)
            else None
        ),
        candidate_sha=(
            payload.get("candidate_sha")
            or metadata.get("candidate_sha")
            if isinstance(payload.get("candidate_sha") or metadata.get("candidate_sha"), str)
            else None
        ),
        case_count=len(case_ids),
        case_ids=tuple(case_ids),
        statuses=statuses,
        physical_totals=dict(physical) if isinstance(physical, dict) else {},
        dispatch_count=len(dispatches) if isinstance(dispatches, list) else 0,
        dispatch_repr_fields=tuple(dispatch_repr_fields),
        warnings=tuple(warnings),
    )


def inspect_report(inspection: V2Inspection) -> dict[str, object]:
    """Serializes the inspection to JSON primitives for the CLI."""

    return {
        "schema_version": inspection.schema_version,
        "assignment_id": inspection.assignment_id,
        "candidate_sha": inspection.candidate_sha,
        "case_count": inspection.case_count,
        "case_ids": list(inspection.case_ids),
        "statuses": dict(inspection.statuses),
        "physical_totals": dict(inspection.physical_totals),
        "dispatch_count": inspection.dispatch_count,
        "dispatch_repr_fields": list(inspection.dispatch_repr_fields),
        "warnings": list(inspection.warnings),
    }
