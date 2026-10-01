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
import subprocess
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
_ANNOTATION_DOCUMENT_KEYS = frozenset(
    {"schema_version", "run_id", "assignment_id", "evidence_sha256",
     "review_complete", "incident_annotations", "resource_actions"}
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


@dataclass(frozen=True, slots=True)
class TesterAnnotations:
    """A completed tester review bound to one sealed evidence document."""

    run_id: str
    assignment_id: str
    evidence_sha256: str
    incident_annotations: tuple[IncidentAnnotation, ...]
    resource_actions: tuple[ResourceAction, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalizationError(message)


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalizationError(f"{label} cannot be read: {error}") from error
    _require(isinstance(payload, dict), f"{label} must be a JSON object.")
    return payload


def _evidence_identity(evidence_path: Path) -> tuple[dict[str, Any], str, str, str]:
    from tools.live_validation.evidence import sha256_file

    evidence = _read_object(evidence_path, "live_evidence.json")
    run_id = evidence.get("run_id")
    assignment_id = evidence.get("assignment_id")
    _require(isinstance(run_id, str) and bool(run_id), "Evidence run_id is required.")
    _require(
        isinstance(assignment_id, str) and bool(assignment_id),
        "Evidence assignment_id is required.",
    )
    return evidence, run_id, assignment_id, sha256_file(evidence_path)


def _report_repository_root(source_root: Path) -> Path:
    """Finds the primary checkout whose ignored weekly collections are shared."""

    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise FinalizationError(
            f"Primary report repository cannot be resolved from {source_root}."
        ) from error
    common_dir = Path(result.stdout.strip()).resolve()
    _require(common_dir.name == ".git", "Primary report repository has no .git directory.")
    return common_dir.parent


def _verify_incidents(
    incidents: tuple[IncidentAnnotation, ...], *, evidence: dict[str, Any],
    run_id: str,
) -> None:
    if not incidents:
        return
    source_root = evidence.get("source_root")
    _require(
        isinstance(source_root, str) and Path(source_root).is_absolute(),
        "Evidence source_root must be absolute to verify published incidents.",
    )
    root = _report_repository_root(Path(source_root)) / ".local-data" / "reports"
    collections = (
        (root / "popup-audits", "records"),
        (root / "live-test-failures", "incidents"),
    )
    for index, annotation in enumerate(incidents):
        _require(
            annotation.incident_id not in (".", "..")
            and Path(annotation.incident_id).name == annotation.incident_id,
            f"incident_annotations[{index}] incident_id must be a folder name.",
        )
        path = Path(annotation.record_path).resolve()
        expected = [
            collection / folder / annotation.incident_id / "record.json"
            for collection, folder in collections
        ]
        _require(
            path in (candidate.resolve() for candidate in expected),
            f"incident_annotations[{index}] is outside the primary report collections.",
        )
        _require(path.is_file(), f"incident_annotations[{index}] record.json is not published.")
        readme = path.with_name("README.md")
        _require(readme.is_file(), f"incident_annotations[{index}] README.md is not published.")
        record = _read_object(path, f"incident_annotations[{index}] record.json")
        _require(
            record.get("id") == annotation.incident_id,
            f"incident_annotations[{index}] incident_id does not match record.json.",
        )
        _require(
            record.get("kind") == "incident" and record.get("run_id") == run_id,
            f"incident_annotations[{index}] record.json does not identify this run.",
        )
        folder = next(
            folder for collection, folder in collections
            if path == (collection / folder / annotation.incident_id / "record.json").resolve()
        )
        _require(
            record.get("record_path") == f"{folder}/{annotation.incident_id}/README.md",
            f"incident_annotations[{index}] record_path does not match published README.md.",
        )
        record_case_ids = record.get("case_ids")
        _require(
            isinstance(record_case_ids, list)
            and all(case_id in record_case_ids for case_id in annotation.case_ids),
            f"incident_annotations[{index}] case_ids do not match record.json.",
        )


def _verify_evidence_refs(
    annotations: TesterAnnotations, evidence: dict[str, Any]
) -> None:
    case_results = evidence.get("case_results")
    dispatches = evidence.get("attributed_dispatches")
    _require(isinstance(case_results, list), "Evidence case_results must be a list.")
    _require(isinstance(dispatches, list), "Evidence attributed_dispatches must be a list.")
    case_ids = {row.get("case_id") for row in case_results if isinstance(row, dict)}
    event_ids = {row.get("event_id") for row in dispatches if isinstance(row, dict)}
    for index, annotation in enumerate(annotations.incident_annotations):
        _require(
            set(annotation.case_ids) <= case_ids,
            f"incident_annotations[{index}] refers to an unknown case_id.",
        )
    for index, action in enumerate(annotations.resource_actions):
        _require(
            action.dispatch_event_id is None or action.dispatch_event_id in event_ids,
            f"resource_actions[{index}] refers to an unknown dispatch_event_id.",
        )


def write_run_finalization(
    path: Path,
    *,
    evidence_path: Path,
    run_id: str,
    assignment_id: str,
    now: datetime,
    incident_annotations: tuple[IncidentAnnotation, ...] = (),
    resource_actions: tuple[ResourceAction, ...] = (),
    review_complete: bool = False,
) -> RunFinalization:
    """Writes ``finalization.json`` beside the sealed evidence document."""

    _, evidence_run_id, evidence_assignment_id, evidence_sha256 = _evidence_identity(
        Path(evidence_path)
    )
    _require(run_id == evidence_run_id, "run_id does not match live_evidence.json.")
    _require(
        assignment_id == evidence_assignment_id,
        "assignment_id does not match live_evidence.json.",
    )
    _require(
        review_complete or not (incident_annotations or resource_actions),
        "Annotations require an explicit completed tester review.",
    )
    review_state = REVIEW_ANNOTATED if review_complete else REVIEW_PENDING
    finalization = RunFinalization(
        run_id=run_id,
        assignment_id=assignment_id,
        evidence_path=Path(evidence_path),
        evidence_sha256=evidence_sha256,
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


def parse_annotations(payload: Any) -> TesterAnnotations:
    """Strictly parses a tester-supplied annotation document."""

    _require(isinstance(payload, dict), "Annotations must be a JSON object.")
    unknown = set(payload) - _ANNOTATION_DOCUMENT_KEYS
    _require(not unknown, f"Annotations have unknown fields: {sorted(unknown)}.")
    _require(
        type(payload.get("schema_version")) is int
        and payload["schema_version"] == FINALIZATION_SCHEMA_VERSION,
        f"Annotations schema_version must be {FINALIZATION_SCHEMA_VERSION}.",
    )
    for field in ("run_id", "assignment_id", "evidence_sha256"):
        _require(
            isinstance(payload.get(field), str) and bool(payload[field]),
            f"Annotations {field} is required.",
        )
    _require(
        payload.get("review_complete") is True,
        "Annotations review_complete must be true.",
    )
    for field in ("incident_annotations", "resource_actions"):
        _require(
            isinstance(payload.get(field), list),
            f"Annotations {field} must be a list.",
        )

    incidents: list[IncidentAnnotation] = []
    for index, row in enumerate(payload["incident_annotations"]):
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
        case_ids = row.get("case_ids", [])
        _require(
            isinstance(case_ids, list)
            and all(isinstance(item, str) and item for item in case_ids),
            f"incident_annotations[{index}].case_ids must be a list of case ids.",
        )
        for field in ("boundary", "note"):
            _require(
                isinstance(row.get(field, ""), str),
                f"incident_annotations[{index}].{field} must be a string.",
            )
        incidents.append(
            IncidentAnnotation(
                incident_id=incident_id.strip(),
                record_path=record_path,
                case_ids=tuple(case_ids),
                boundary=row.get("boundary", ""),
                note=row.get("note", ""),
            )
        )

    actions: list[ResourceAction] = []
    for index, row in enumerate(payload["resource_actions"]):
        _require(isinstance(row, dict), f"resource_actions[{index}] must be an object.")
        extra = set(row) - _RESOURCE_ACTION_KEYS
        _require(not extra, f"resource_actions[{index}] unknown fields: {sorted(extra)}.")
        action_id = row.get("action_id")
        _require(
            isinstance(action_id, str) and action_id.strip(),
            f"resource_actions[{index}].action_id is required.",
        )
        for field in ("description", "resource_kind"):
            _require(
                isinstance(row.get(field, ""), str),
                f"resource_actions[{index}].{field} must be a string.",
            )
        quantity = row.get("quantity")
        _require(
            quantity is None or (isinstance(quantity, (int, float)) and not isinstance(quantity, bool)),
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
                description=row.get("description", ""),
                resource_kind=row.get("resource_kind", ""),
                quantity=quantity,
                dispatch_event_id=dispatch_event_id,
            )
        )
    return TesterAnnotations(
        run_id=payload["run_id"],
        assignment_id=payload["assignment_id"],
        evidence_sha256=payload["evidence_sha256"],
        incident_annotations=tuple(incidents),
        resource_actions=tuple(actions),
    )


def finalize_run(
    run_dir: Path,
    *,
    annotations_path: Path | None,
    now: datetime,
) -> RunFinalization:
    """Rewrites ``finalization.json`` with tester annotations, if supplied.

    The sealed ``live_evidence.json`` is never modified. A supplied document
    explicitly completes tester review, even when both annotation lists are empty.
    """

    run_dir = Path(run_dir)
    evidence_path = run_dir / "live_evidence.json"
    _require(evidence_path.exists(), f"live_evidence.json not found in {run_dir}.")
    evidence, run_id, assignment_id, evidence_sha256 = _evidence_identity(evidence_path)
    existing = run_dir / "finalization.json"
    if annotations_path is None and existing.exists():
        prior = _read_object(existing, "finalization.json")
        _require(
            prior.get("run_id") == run_id
            and prior.get("assignment_id") == assignment_id
            and prior.get("evidence_sha256") == evidence_sha256
            and prior.get("evidence_path") == str(evidence_path),
            "Existing finalization does not match live_evidence.json.",
        )
        state = prior.get("review_state")
        _require(state in (REVIEW_PENDING, REVIEW_ANNOTATED), "Invalid review_state.")
        parsed = parse_annotations({
            "schema_version": prior.get("schema_version"),
            "run_id": run_id,
            "assignment_id": assignment_id,
            "evidence_sha256": evidence_sha256,
            "review_complete": True,
            "incident_annotations": prior.get("incident_annotations"),
            "resource_actions": prior.get("resource_actions"),
        })
        _require(
            state == REVIEW_ANNOTATED
            or not (parsed.incident_annotations or parsed.resource_actions),
            "Pending finalization contains annotations.",
        )
        try:
            updated_at = datetime.fromisoformat(prior["updated_at"])
        except (KeyError, TypeError, ValueError) as error:
            raise FinalizationError("Existing finalization updated_at is invalid.") from error
        return RunFinalization(
            run_id, assignment_id, evidence_path, evidence_sha256, state,
            parsed.incident_annotations, parsed.resource_actions, updated_at,
        )
    incidents: tuple[IncidentAnnotation, ...] = ()
    actions: tuple[ResourceAction, ...] = ()
    review_complete = False
    if annotations_path is not None:
        parsed = parse_annotations(_read_object(Path(annotations_path), "annotations"))
        _require(parsed.run_id == run_id, "Annotations run_id does not match evidence.")
        _require(
            parsed.assignment_id == assignment_id,
            "Annotations assignment_id does not match evidence.",
        )
        _require(
            parsed.evidence_sha256 == evidence_sha256,
            "Annotations evidence_sha256 does not match evidence.",
        )
        _verify_evidence_refs(parsed, evidence)
        _verify_incidents(parsed.incident_annotations, evidence=evidence, run_id=run_id)
        incidents, actions = parsed.incident_annotations, parsed.resource_actions
        review_complete = True
    return write_run_finalization(
        existing,
        evidence_path=evidence_path,
        run_id=run_id,
        assignment_id=assignment_id,
        now=now,
        incident_annotations=incidents,
        resource_actions=actions,
        review_complete=review_complete,
    )
