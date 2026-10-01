"""Typed post-run finalization overlay for tester annotations.

The runner writes one immutable ``live_evidence.json`` per run and never
rewrites it. Tester review metadata — links to incident records published
under the shared weekly collections, and observed in-run resource actions —
lives in a sibling ``finalization.json``. The file is seeded automatically
with ``review_state: "pending_tester_review"`` and stays pending until a
tester writes annotations through ``finalize_run``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

FINALIZATION_SCHEMA_VERSION = 1
REVIEW_PENDING = "pending_tester_review"
REVIEW_ANNOTATED = "annotated"

_ANNOTATION_KEYS = frozenset(
    {"incident_id", "record_path", "case_ids", "boundary", "note"}
)
_RESOURCE_ACTION_KEYS = frozenset(
    {"action_id", "description", "resource_kind", "quantity", "dispatch_event_id"}
)


class FinalizationError(ValueError):
    """The finalization document or annotation payload is malformed."""


@dataclass(frozen=True, slots=True)
class IncidentAnnotation:
    """Links one published incident record to this run.

    ``incident_id`` is the stable ``INC-...`` identifier and ``record_path``
    the incident's ``record.json`` under an existing shared collection
    (``live-test-failures/incidents`` or ``popup-audits/records``). The runner
    never creates or indexes incident records; it only links ones the tester
    already published.
    """

    incident_id: str
    record_path: str
    case_ids: tuple[str, ...]
    boundary: str
    note: str


@dataclass(frozen=True, slots=True)
class ResourceAction:
    """One observed in-run resource action the tester attributes post-hoc."""

    action_id: str
    description: str
    resource_kind: str
    quantity: int | float | None
    dispatch_event_id: str | None


@dataclass(frozen=True, slots=True)
class RunFinalization:
    """The typed overlay pairing tester annotations with immutable evidence."""

    run_id: str
    assignment_id: str
    evidence_path: Path
    evidence_sha256: str
    review_state: str
    incident_annotations: tuple[IncidentAnnotation, ...]
    resource_actions: tuple[ResourceAction, ...]
    updated_at: datetime


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalizationError(message)


def write_run_finalization(
    path: Path,
    *,
    evidence_path: Path,
    run_id: str,
    assignment_id: str,
    now: datetime,
    incident_annotations: tuple[IncidentAnnotation, ...] = (),
    resource_actions: tuple[ResourceAction, ...] = (),
) -> RunFinalization:
    """Writes ``finalization.json`` beside the sealed evidence document."""

    from tools.live_validation.evidence import sha256_file

    review_state = (
        REVIEW_ANNOTATED if incident_annotations or resource_actions else REVIEW_PENDING
    )
    finalization = RunFinalization(
        run_id=run_id,
        assignment_id=assignment_id,
        evidence_path=Path(evidence_path),
        evidence_sha256=sha256_file(Path(evidence_path)),
        review_state=review_state,
        incident_annotations=incident_annotations,
        resource_actions=resource_actions,
        updated_at=now,
    )
    payload = {
        "schema_version": FINALIZATION_SCHEMA_VERSION,
        "run_id": finalization.run_id,
        "assignment_id": finalization.assignment_id,
        "evidence_path": str(finalization.evidence_path),
        "evidence_sha256": finalization.evidence_sha256,
        "review_state": finalization.review_state,
        "incident_annotations": [
            {
                "incident_id": row.incident_id,
                "record_path": row.record_path,
                "case_ids": list(row.case_ids),
                "boundary": row.boundary,
                "note": row.note,
            }
            for row in finalization.incident_annotations
        ],
        "resource_actions": [
            {
                "action_id": row.action_id,
                "description": row.description,
                "resource_kind": row.resource_kind,
                "quantity": row.quantity,
                "dispatch_event_id": row.dispatch_event_id,
            }
            for row in finalization.resource_actions
        ],
        "updated_at": finalization.updated_at.isoformat(),
    }
    Path(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return finalization


def parse_annotations(payload: Any) -> tuple[
    tuple[IncidentAnnotation, ...], tuple[ResourceAction, ...]
]:
    """Strictly parses a tester-supplied annotation document."""

    _require(isinstance(payload, dict), "Annotations must be a JSON object.")
    unknown = set(payload) - {"schema_version", "incident_annotations", "resource_actions"}
    _require(not unknown, f"Annotations have unknown fields: {sorted(unknown)}.")
    _require(
        payload.get("schema_version") == FINALIZATION_SCHEMA_VERSION,
        f"Annotations schema_version must be {FINALIZATION_SCHEMA_VERSION}.",
    )

    incidents: list[IncidentAnnotation] = []
    for index, row in enumerate(payload.get("incident_annotations") or []):
        _require(isinstance(row, dict), f"incident_annotations[{index}] must be an object.")
        extra = set(row) - _ANNOTATION_KEYS
        _require(not extra, f"incident_annotations[{index}] unknown fields: {sorted(extra)}.")
        incident_id = row.get("incident_id")
        record_path = row.get("record_path")
        _require(
            isinstance(incident_id, str) and incident_id.strip(),
            f"incident_annotations[{index}].incident_id is required.",
        )
        _require(
            isinstance(record_path, str) and Path(record_path).is_absolute(),
            f"incident_annotations[{index}].record_path must be absolute.",
        )
        case_ids = row.get("case_ids") or []
        _require(
            isinstance(case_ids, list)
            and all(isinstance(item, str) and item for item in case_ids),
            f"incident_annotations[{index}].case_ids must be a list of case ids.",
        )
        incidents.append(
            IncidentAnnotation(
                incident_id=incident_id.strip(),
                record_path=record_path,
                case_ids=tuple(case_ids),
                boundary=str(row.get("boundary") or ""),
                note=str(row.get("note") or ""),
            )
        )

    actions: list[ResourceAction] = []
    for index, row in enumerate(payload.get("resource_actions") or []):
        _require(isinstance(row, dict), f"resource_actions[{index}] must be an object.")
        extra = set(row) - _RESOURCE_ACTION_KEYS
        _require(not extra, f"resource_actions[{index}] unknown fields: {sorted(extra)}.")
        action_id = row.get("action_id")
        _require(
            isinstance(action_id, str) and action_id.strip(),
            f"resource_actions[{index}].action_id is required.",
        )
        quantity = row.get("quantity")
        _require(
            quantity is None or isinstance(quantity, (int, float)),
            f"resource_actions[{index}].quantity must be numeric or null.",
        )
        dispatch_event_id = row.get("dispatch_event_id")
        _require(
            dispatch_event_id is None or isinstance(dispatch_event_id, str),
            f"resource_actions[{index}].dispatch_event_id must be a string or null.",
        )
        actions.append(
            ResourceAction(
                action_id=action_id.strip(),
                description=str(row.get("description") or ""),
                resource_kind=str(row.get("resource_kind") or ""),
                quantity=quantity,
                dispatch_event_id=dispatch_event_id,
            )
        )
    return tuple(incidents), tuple(actions)


def finalize_run(
    run_dir: Path,
    *,
    annotations_path: Path | None,
    now: datetime,
) -> RunFinalization:
    """Rewrites ``finalization.json`` with tester annotations, if supplied.

    The sealed ``live_evidence.json`` is never modified; annotations land in
    the sibling overlay and flip ``review_state`` once any are present.
    """

    run_dir = Path(run_dir)
    evidence_path = run_dir / "live_evidence.json"
    _require(evidence_path.exists(), f"live_evidence.json not found in {run_dir}.")
    incidents: tuple[IncidentAnnotation, ...] = ()
    actions: tuple[ResourceAction, ...] = ()
    if annotations_path is not None:
        try:
            payload = json.loads(Path(annotations_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FinalizationError(f"annotations cannot be read: {error}") from error
        incidents, actions = parse_annotations(payload)
    existing = run_dir / "finalization.json"
    run_id = run_dir.name
    assignment_id = ""
    if existing.exists():
        prior = json.loads(existing.read_text(encoding="utf-8"))
        run_id = str(prior.get("run_id") or run_dir.name)
        assignment_id = str(prior.get("assignment_id") or "")
    return write_run_finalization(
        existing,
        evidence_path=evidence_path,
        run_id=run_id,
        assignment_id=assignment_id,
        now=now,
        incident_annotations=incidents,
        resource_actions=actions,
    )
