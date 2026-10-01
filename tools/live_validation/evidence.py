"""Typed v3 live evidence document, serialization, and totals.

Every selected case has exactly one ``CaseResult``; unselected or historical
cases are never inserted as fresh proof. All values serialize to JSON
primitives with ISO timestamps and ``str()`` paths — the validator treats the
file as untrusted data and verifies every identity back to the released
binding.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchEvent,
    InputDispatchFailure,
    InputDispatchRecord,
    SwipeDispatch,
    TapDispatch,
    WheelDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef

from tools.live_validation.events import AttributedDispatch


EVIDENCE_SCHEMA_VERSION = 3


class CaseStatus(StrEnum):
    """One observed case outcome; the run never infers acceptance from it."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """One curated evidence artifact: canonical path, kind, hash, purpose."""

    path: Path
    kind: str
    sha256: str
    purpose: str


@dataclass(frozen=True, slots=True)
class CaseResult:
    """The single recorded outcome for one selected case."""

    case_id: str
    purpose: str
    status: CaseStatus
    artifacts: tuple[ArtifactRef, ...]
    receipt_event_ids: tuple[str, ...]
    dispatch_event_ids: tuple[str, ...]
    body_entry_event_id: str | None
    source_artifact: Path | None
    follow_up_artifact: Path | None
    unresolved_boundary: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class LogicalAttemptRecord:
    """One journal-visible logical attempt in serialized form."""

    attempt_id: str
    case_id: str
    control_name: str
    number: int
    limit: int
    status: str
    journal_ref: str
    dispatch_event_id: str | None


@dataclass(frozen=True, slots=True)
class LiveEvidence:
    """The complete v3 evidence document for one bounded run."""

    assignment_id: str
    run_id: str
    candidate_sha: str
    source_root: Path
    import_root: Path
    report_root: Path
    entry_point: Path
    entry_sha256: str
    started_at: datetime
    finished_at: datetime
    actual_target: dict[str, str | None]
    case_results: tuple[CaseResult, ...]
    artifacts: tuple[ArtifactRef, ...]
    attributed_dispatches: tuple[AttributedDispatch, ...]
    logical_attempts: tuple[LogicalAttemptRecord, ...]
    incident_refs: tuple[str, ...]
    resource_actions: tuple[dict[str, Any], ...]
    coverage: dict[str, Any]
    observed_final_state: dict[str, Any]
    totals: dict[str, int]
    cleanup: dict[str, Any]
    terminal_binding_check: dict[str, Any]


def sha256_file(path: Path) -> str:
    """Hashes one file's bytes for identity binding."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frame_ref_dict(frame: FrameRef) -> dict[str, object]:
    """Serializes one authorizing frame identity exactly."""

    return {
        "session_id": frame.session_id,
        "session_epoch": frame.session_epoch,
        "capture_sequence": frame.capture_sequence,
        "input_sequence": frame.input_sequence,
        "captured_at": frame.captured_at.isoformat(),
    }


def _dispatch_dict(event: InputDispatchEvent) -> dict[str, object]:
    if isinstance(event, InputDispatchRecord):
        dispatch = event.dispatch
        if isinstance(dispatch, TapDispatch):
            primitive = "tap"
            params: dict[str, object] = {
                "point": list(dispatch.point),
                "input_sequence": dispatch.input_sequence,
            }
        elif isinstance(dispatch, SwipeDispatch):
            primitive = "swipe"
            params = {
                "start": list(dispatch.start),
                "end": list(dispatch.end),
                "duration_ms": dispatch.duration_ms,
                "input_source": dispatch.input_source,
                "gesture_primitive": dispatch.gesture_primitive,
                "input_sequence": dispatch.input_sequence,
            }
        elif isinstance(dispatch, WheelDispatch):
            primitive = "wheel"
            params = {
                "point": list(dispatch.point),
                "frame_size": list(dispatch.frame_size),
                "vertical_detent": dispatch.vertical_detent,
                "transport": dispatch.transport,
                "input_sequence": dispatch.input_sequence,
            }
        else:
            raise TypeError(f"Unsupported dispatch type: {type(dispatch).__name__}.")
        return {
            "kind": "receipt",
            "primitive": primitive,
            "dispatch": params,
            "source_frame": frame_ref_dict(event.source_frame),
            "artifact_path": None if event.artifact_path is None else str(event.artifact_path),
            "home_city": event.home_city,
        }
    if isinstance(event, InputDispatchFailure):
        return {
            "kind": "failure",
            "input_kind": event.input_kind,
            "failure_phase": event.failure_phase,
            "exception_type": event.exception_type,
            "operation_id": event.operation_id,
            "source_frame": (
                None if event.source_frame is None else frame_ref_dict(event.source_frame)
            ),
            "artifact_path": None if event.artifact_path is None else str(event.artifact_path),
            "home_city": event.home_city,
        }
    raise TypeError(f"Unsupported dispatch event type: {type(event).__name__}.")


def attributed_dispatch_dict(attributed: AttributedDispatch) -> dict[str, object]:
    """Serializes one attributed dispatch event."""

    row = {
        "event_id": attributed.event_id,
        "phase": attributed.phase.value,
        "case_id": attributed.case_id,
    }
    row.update(_dispatch_dict(attributed.event))
    return row


def artifact_ref_dict(ref: ArtifactRef) -> dict[str, object]:
    """Serializes one curated artifact reference."""

    return {
        "path": str(ref.path),
        "kind": ref.kind,
        "sha256": ref.sha256,
        "purpose": ref.purpose,
    }


def case_result_dict(result: CaseResult) -> dict[str, object]:
    """Serializes one case result row."""

    return {
        "case_id": result.case_id,
        "purpose": result.purpose,
        "status": result.status.value,
        "artifacts": [artifact_ref_dict(ref) for ref in result.artifacts],
        "receipt_event_ids": list(result.receipt_event_ids),
        "dispatch_event_ids": list(result.dispatch_event_ids),
        "body_entry_event_id": result.body_entry_event_id,
        "source_artifact": (
            None if result.source_artifact is None else str(result.source_artifact)
        ),
        "follow_up_artifact": (
            None if result.follow_up_artifact is None else str(result.follow_up_artifact)
        ),
        "unresolved_boundary": result.unresolved_boundary,
        "detail": result.detail,
    }


def compute_totals(
    events: tuple[AttributedDispatch, ...],
    attempts: tuple[LogicalAttemptRecord, ...],
) -> dict[str, int]:
    """Derives physical totals only from actual dispatch receipts."""

    totals = {"tap": 0, "swipe": 0, "wheel": 0, "dispatch_records": 0, "dispatch_failures": 0}
    for attributed in events:
        event = attributed.event
        if isinstance(event, InputDispatchRecord):
            totals["dispatch_records"] += 1
            if isinstance(event.dispatch, TapDispatch):
                totals["tap"] += 1
            elif isinstance(event.dispatch, SwipeDispatch):
                totals["swipe"] += 1
            elif isinstance(event.dispatch, WheelDispatch):
                totals["wheel"] += 1
        elif isinstance(event, InputDispatchFailure):
            totals["dispatch_failures"] += 1
    totals["logical_attempts"] = len(attempts)
    return totals


def serialize_live_evidence(evidence: LiveEvidence) -> dict[str, object]:
    """Converts the whole evidence document to JSON primitives."""

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "assignment_id": evidence.assignment_id,
        "run_id": evidence.run_id,
        "candidate_sha": evidence.candidate_sha,
        "source_root": str(evidence.source_root),
        "import_root": str(evidence.import_root),
        "report_root": str(evidence.report_root),
        "entry_point": str(evidence.entry_point),
        "entry_sha256": evidence.entry_sha256,
        "started_at": evidence.started_at.isoformat(),
        "finished_at": evidence.finished_at.isoformat(),
        "actual_target": dict(evidence.actual_target),
        "case_results": [case_result_dict(result) for result in evidence.case_results],
        "artifacts": [artifact_ref_dict(ref) for ref in evidence.artifacts],
        "attributed_dispatches": [
            attributed_dispatch_dict(attributed)
            for attributed in evidence.attributed_dispatches
        ],
        "logical_attempts": [
            {
                "attempt_id": record.attempt_id,
                "case_id": record.case_id,
                "control_name": record.control_name,
                "number": record.number,
                "limit": record.limit,
                "status": record.status,
                "journal_ref": record.journal_ref,
                "dispatch_event_id": record.dispatch_event_id,
            }
            for record in evidence.logical_attempts
        ],
        "incident_refs": list(evidence.incident_refs),
        "resource_actions": [dict(row) for row in evidence.resource_actions],
        "coverage": dict(evidence.coverage),
        "observed_final_state": dict(evidence.observed_final_state),
        "totals": dict(evidence.totals),
        "cleanup": dict(evidence.cleanup),
        "terminal_binding_check": dict(evidence.terminal_binding_check),
    }


def write_live_evidence(evidence: LiveEvidence, path: Path) -> Path:
    """Persists one evidence document atomically (fsync, then os.replace)."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_live_evidence(evidence)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


def collect_artifact(path: Path, *, kind: str, purpose: str) -> ArtifactRef:
    """Hashes one existing artifact into a curated reference."""

    path = Path(path)
    return ArtifactRef(path=path, kind=kind, sha256=sha256_file(path), purpose=purpose)


def now_utc() -> datetime:
    """The runner's default wall clock."""

    return datetime.now(tz=UTC)
