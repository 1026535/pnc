"""Offline validator binding a v3 result document to its released assignment.

The validator is fail-closed: every selected case must have exactly one
result, every identity field must match the binding, every artifact must hash,
every case-attributed dispatch must be a consistent typed receipt or failure,
and totals must recompute exactly from the recorded events. It never evaluates
``repr`` strings, infers acceptance, or upgrades a result's status.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from tools.live_validation.binding import AssignmentBinding, _HEX64
from tools.live_validation.cases import CaseSpec, require_case
from tools.live_validation.evidence import EVIDENCE_SCHEMA_VERSION, sha256_file


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """One concrete contract violation in a result document."""

    check: str
    detail: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The verdict plus every finding; empty findings means valid."""

    valid: bool
    findings: tuple[ValidationFinding, ...]


_FRAME_KEYS = (
    "session_id",
    "session_epoch",
    "capture_sequence",
    "input_sequence",
    "captured_at",
    "captured_monotonic",
)
_PRIMITIVE_FIELDS: Mapping[str, frozenset[str]] = {
    "tap": frozenset({"point", "input_sequence"}),
    "swipe": frozenset(
        {"start", "end", "duration_ms", "input_source", "gesture_primitive", "input_sequence"}
    ),
    "wheel": frozenset({"point", "frame_size", "vertical_detent", "transport", "input_sequence"}),
}
_STATUSES = frozenset({"passed", "failed", "blocked", "not_run"})
_ATTEMPT_STATUSES = frozenset(
    {"dispatched", "refused", "uncertain", "annotation_timeout", "unfinished"}
)
_ATTEMPT_INTENTS = frozenset({"body_entry", "control"})


def _is_iso(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _frame_findings(frame: object, where: str) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if not isinstance(frame, dict):
        return [ValidationFinding("frame", f"{where} frame is not an object.")]
    for key in _FRAME_KEYS:
        if key not in frame:
            findings.append(ValidationFinding("frame", f"{where} frame missing '{key}'."))
    if "session_id" in frame and not isinstance(frame["session_id"], str):
        findings.append(ValidationFinding("frame", f"{where} frame session_id must be a string."))
    for key in ("session_epoch", "capture_sequence", "input_sequence"):
        if key in frame and not isinstance(frame[key], int):
            findings.append(ValidationFinding("frame", f"{where} frame {key} must be an int."))
    if "captured_at" in frame and not _is_iso(frame["captured_at"]):
        findings.append(ValidationFinding("frame", f"{where} frame captured_at must be ISO-8601."))
    if "captured_monotonic" in frame and not isinstance(
        frame["captured_monotonic"], (int, float)
    ):
        findings.append(
            ValidationFinding("frame", f"{where} frame captured_monotonic must be numeric.")
        )
    return findings


def validate_live_evidence(
    binding: AssignmentBinding,
    result_path: Path,
    *,
    verify_files: bool = True,
) -> ValidationReport:
    """Validates one saved result document against its released assignment."""

    findings: list[ValidationFinding] = []

    def fail(check: str, detail: str) -> None:
        findings.append(ValidationFinding(check, detail))

    try:
        doc = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return ValidationReport(
            valid=False,
            findings=(ValidationFinding("parse", f"result cannot be read: {error}"),),
        )
    if not isinstance(doc, dict):
        return ValidationReport(
            valid=False, findings=(ValidationFinding("parse", "result is not a JSON object."),)
        )

    # --- Envelope identity --------------------------------------------------
    if doc.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        fail("schema_version", f"expected {EVIDENCE_SCHEMA_VERSION}, got {doc.get('schema_version')!r}.")
    for key, expected in (
        ("assignment_id", binding.assignment_id),
        ("run_id", binding.run_id),
        ("candidate_sha", binding.candidate_sha),
        ("source_root", str(binding.source_root)),
        ("import_root", str(binding.import_root)),
        ("report_root", str(binding.report_root)),
        ("entry_point", str(binding.entry_point)),
        ("entry_sha256", binding.entry_sha256),
    ):
        if doc.get(key) != expected:
            fail("envelope", f"{key} mismatch: expected {expected!r}, got {doc.get(key)!r}.")
    if not _is_iso(doc.get("started_at")) or not _is_iso(doc.get("finished_at")):
        fail("envelope", "started_at/finished_at must be ISO-8601 timestamps.")

    target = doc.get("actual_target")
    if not isinstance(target, dict):
        fail("target", "actual_target must be an object.")
    else:
        if target.get("account_id") != binding.target_account_id:
            fail("target", "actual account_id does not match the binding.")
        if target.get("instance_id") != binding.target_instance_id:
            fail("target", "actual instance_id does not match the binding.")
        if target.get("live_role") != binding.target_role:
            fail("target", "actual live_role does not match the binding.")
        if target.get("castle") != binding.target_castle_ref:
            fail("target", "actual castle does not match the binding.")

    # --- Case results -------------------------------------------------------
    results = doc.get("case_results")
    if not isinstance(results, list):
        fail("case_results", "case_results must be a list.")
        results = []
    expected_ids = [selection.case_id for selection in binding.selected_cases]
    actual_ids = [row.get("case_id") for row in results if isinstance(row, dict)]
    if actual_ids != expected_ids:
        fail(
            "case_results",
            f"case_result order/ids {actual_ids!r} != selected {expected_ids!r}; "
            "every selected case needs exactly one result.",
        )
    specs: dict[str, CaseSpec] = {}
    for case_id in expected_ids:
        try:
            specs[case_id] = require_case(case_id)
        except KeyError as error:
            fail("case_results", str(error))
    result_by_id: dict[str, dict[str, Any]] = {}
    for row in results:
        if not isinstance(row, dict):
            fail("case_results", "case_result rows must be objects.")
            continue
        case_id = row.get("case_id")
        if isinstance(case_id, str):
            result_by_id[case_id] = row
        spec = specs.get(case_id if isinstance(case_id, str) else "")
        if spec is not None and row.get("purpose") != spec.purpose.value:
            fail("case_results", f"{case_id}: purpose {row.get('purpose')!r} != spec '{spec.purpose.value}'.")
        if row.get("status") not in _STATUSES:
            fail("case_results", f"{case_id}: status must be one of {sorted(_STATUSES)}.")
        if spec is not None and row.get("body_case_id") != spec.body_case_id:
            fail(
                "case_results",
                f"{case_id}: body_case_id {row.get('body_case_id')!r} != "
                f"spec '{spec.body_case_id}'.",
            )

    # --- Artifact index -----------------------------------------------------
    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, list):
        fail("artifacts", "artifacts must be a list.")
        artifacts = []
    artifact_paths: set[str] = set()
    for index, entry in enumerate(artifacts):
        if not isinstance(entry, dict):
            fail("artifacts", f"artifacts[{index}] must be an object.")
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not Path(path).is_absolute():
            fail("artifacts", f"artifacts[{index}].path must be absolute.")
        elif verify_files:
            file_path = Path(path)
            if not file_path.exists():
                fail("artifacts", f"artifact missing on disk: {path}")
            else:
                digest = sha256_file(file_path)
                if digest != entry.get("sha256"):
                    fail("artifacts", f"artifact sha256 mismatch: {path}")
        if not isinstance(entry.get("sha256"), str) or _HEX64.fullmatch(str(entry.get("sha256"))) is None:
            fail("artifacts", f"artifacts[{index}].sha256 must be lowercase SHA-256 hex.")
        if not entry.get("kind") or not entry.get("purpose"):
            fail("artifacts", f"artifacts[{index}] requires nonempty kind and purpose.")
        if isinstance(path, str):
            artifact_paths.add(path)

    for row in result_by_id.values():
        case_id = row.get("case_id")
        for key in ("source_artifact", "follow_up_artifact"):
            value = row.get(key)
            if value is not None and value not in artifact_paths:
                fail("artifacts", f"{case_id}.{key} is not in the artifact index.")
        for ref in row.get("artifacts") or []:
            if isinstance(ref, dict) and isinstance(ref.get("path"), str):
                if ref["path"] not in artifact_paths:
                    fail("artifacts", f"{case_id} artifact {ref['path']} is not in the index.")

    # --- Attributed dispatches ----------------------------------------------
    events = doc.get("attributed_dispatches")
    if not isinstance(events, list):
        fail("events", "attributed_dispatches must be a list.")
        events = []
    event_by_id: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for index, entry in enumerate(events):
        where = f"attributed_dispatches[{index}]"
        if not isinstance(entry, dict):
            fail("events", f"{where} must be an object.")
            continue
        event_id = entry.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            fail("events", f"{where} requires an event_id.")
            continue
        if event_id in seen_ids:
            fail("events", f"duplicate event_id '{event_id}'.")
        seen_ids.add(event_id)
        event_by_id[event_id] = entry
        phase = entry.get("phase")
        case_id = entry.get("case_id")
        if phase == "case":
            if not isinstance(case_id, str) or case_id not in specs:
                fail("events", f"{event_id}: case phase requires a selected case_id.")
        elif phase in ("setup", "cleanup"):
            if case_id is not None:
                fail("events", f"{event_id}: {phase} events must not carry a case_id.")
        else:
            fail("events", f"{event_id}: phase must be setup/case/cleanup.")
        kind = entry.get("kind")
        if kind == "receipt":
            primitive = entry.get("primitive")
            if primitive not in _PRIMITIVE_FIELDS:
                fail("events", f"{event_id}: receipt primitive must be tap/swipe/wheel.")
            else:
                params = entry.get("dispatch")
                if not isinstance(params, dict):
                    fail("events", f"{event_id}: receipt dispatch must be an object.")
                else:
                    missing = _PRIMITIVE_FIELDS[primitive] - set(params)
                    if missing:
                        fail("events", f"{event_id}: {primitive} dispatch missing {sorted(missing)}.")
                    if not isinstance(params.get("input_sequence"), int):
                        fail("events", f"{event_id}: input_sequence must be an int.")
            findings.extend(_frame_findings(entry.get("source_frame"), event_id))
        elif kind == "failure":
            for key in ("input_kind", "failure_phase", "exception_type"):
                if not isinstance(entry.get(key), str) or not entry[key]:
                    fail("events", f"{event_id}: failure requires nonempty '{key}'.")
            if entry.get("source_frame") is not None:
                findings.extend(_frame_findings(entry.get("source_frame"), event_id))
        else:
            fail("events", f"{event_id}: kind must be receipt/failure.")

    # --- Physical input identity and continuity -----------------------------
    seen_physical: dict[tuple[str, int, int], str] = {}
    last_sequence_by_session: dict[tuple[str, int], int] = {}
    for entry in event_by_id.values():
        if entry.get("kind") != "receipt":
            continue
        source_frame = entry.get("source_frame")
        dispatch = entry.get("dispatch")
        if not isinstance(source_frame, dict) or not isinstance(dispatch, dict):
            continue
        session_key = (
            source_frame.get("session_id"),
            source_frame.get("session_epoch"),
        )
        input_sequence = dispatch.get("input_sequence")
        if not (
            isinstance(session_key[0], str)
            and isinstance(session_key[1], int)
            and isinstance(input_sequence, int)
        ):
            continue
        physical = (session_key[0], session_key[1], input_sequence)
        if input_sequence != source_frame.get("input_sequence", -2) + 1:
            fail("events", f"'{entry.get('event_id')}' dispatch must advance its source by one input.")
        prior = seen_physical.get(physical)
        if prior is not None:
            fail(
                "events",
                f"receipts '{prior}' and '{entry.get('event_id')}' share the same "
                "physical identity (session, epoch, input_sequence).",
            )
        else:
            seen_physical[physical] = entry.get("event_id")
        previous = last_sequence_by_session.get(session_key)
        if previous is not None and input_sequence != previous + 1:
            fail(
                "events",
                f"'{entry.get('event_id')}' input_sequence {input_sequence} does not "
                f"continue session {session_key[0]}/{session_key[1]} after {previous}; coverage gap.",
            )
        last_sequence_by_session[session_key] = input_sequence

    # --- Case/event binding --------------------------------------------------
    for row in result_by_id.values():
        case_id = str(row.get("case_id"))
        spec = specs.get(case_id)
        for key in ("receipt_event_ids", "dispatch_event_ids"):
            values = row.get(key)
            if not isinstance(values, list):
                fail("binding", f"{case_id}.{key} must be a list.")
                continue
            for event_id in values:
                event = event_by_id.get(event_id)
                if event is None:
                    fail("binding", f"{case_id}.{key} references unknown event '{event_id}'.")
                elif event.get("case_id") != case_id or event.get("phase") != "case":
                    fail("binding", f"{case_id}.{key} event '{event_id}' is not attributed to this case.")
            expected = [eid for eid, event in event_by_id.items()
                        if event.get("phase") == "case" and event.get("case_id") == case_id
                        and (key == "dispatch_event_ids" or event.get("kind") == "receipt")]
            if values != expected:
                fail("binding", f"{case_id}.{key} must include all case events exactly once in order.")
        receipt_ids = row.get("receipt_event_ids") or []
        for event_id in receipt_ids:
            event = event_by_id.get(event_id)
            if event is not None and event.get("kind") != "receipt":
                fail("binding", f"{case_id}: receipt_event_ids must name receipt events only.")
        body_id = row.get("body_entry_event_id")
        body_owner = spec.body_case_id if spec is not None else case_id
        if body_id is not None:
            event = event_by_id.get(body_id)
            if event is None:
                fail("binding", f"{case_id}: body_entry_event_id references unknown event.")
            elif (
                event.get("kind") != "receipt"
                or event.get("primitive") != "tap"
                or event.get("case_id") != body_owner
            ):
                fail(
                    "binding",
                    f"{case_id}: body entry must be a tap receipt attributed to "
                    f"its owner case '{body_owner}'.",
                )
        if spec is not None and row.get("status") == "passed":
            if body_id is None:
                fail(
                    "binding",
                    f"{case_id}: a passed case requires a body-entry receipt "
                    f"owned by '{body_owner}'.",
                )
            if row.get("source_artifact") is None:
                fail("binding", f"{case_id}: a passed case requires a source_artifact.")
            if row.get("follow_up_artifact") is None:
                fail("binding", f"{case_id}: a passed case requires a follow_up_artifact.")
            postcondition = row.get("postcondition")
            if not isinstance(postcondition, dict):
                fail("binding", f"{case_id}: a passed case requires a postcondition record.")
            elif "screen_type" not in postcondition:
                fail("binding", f"{case_id}: postcondition requires a screen_type.")
            elif postcondition.get("artifact_path") != row.get("follow_up_artifact"):
                fail("binding", f"{case_id}: postcondition must bind the persisted follow-up artifact.")
            if isinstance(postcondition, dict):
                findings.extend(_frame_findings(postcondition.get("frame"), f"{case_id} postcondition"))
            if spec.purpose.value == "development_validation":
                if (not isinstance(postcondition, dict)
                        or postcondition.get("screen_type") != "pnc_home_city"
                        or postcondition.get("guard") != "clear"
                        or postcondition.get("blocking_popup") is not False):
                    fail("binding", f"{case_id}: passed return requires guarded Home proof.")
                kinds = {
                    ref.get("kind")
                    for ref in row.get("artifacts") or []
                    if isinstance(ref, dict)
                }
                for required_kind in ("annotation_request", "annotation_response"):
                    if required_kind not in kinds:
                        fail(
                            "binding",
                            f"{case_id}: a passed validation case requires a "
                            f"'{required_kind}' artifact.",
                        )

    # --- Logical attempts ----------------------------------------------------
    attempts = doc.get("logical_attempts")
    if not isinstance(attempts, list):
        fail("attempts", "logical_attempts must be a list.")
        attempts = []
    seen_attempts: set[str] = set()
    per_case_numbers: dict[str, list[int]] = {}
    for index, entry in enumerate(attempts):
        where = f"logical_attempts[{index}]"
        if not isinstance(entry, dict):
            fail("attempts", f"{where} must be an object.")
            continue
        attempt_id = entry.get("attempt_id")
        case_id = entry.get("case_id")
        if not isinstance(attempt_id, str) or attempt_id in seen_attempts:
            fail("attempts", f"{where} requires a unique attempt_id.")
        if isinstance(attempt_id, str):
            seen_attempts.add(attempt_id)
        spec = specs.get(case_id if isinstance(case_id, str) else "")
        if spec is None:
            fail("attempts", f"{where} case_id must be a selected case.")
            continue
        if entry.get("control_name") != (spec.control_name or spec.operation_id):
            fail(
                "attempts",
                f"{attempt_id}: control_name must be the spec control "
                f"'{spec.control_name}' or operation '{spec.operation_id}'.",
            )
        number, limit = entry.get("number"), entry.get("limit")
        if not isinstance(number, int) or not isinstance(limit, int) or number < 1 or limit < 1 or number > limit:
            fail("attempts", f"{attempt_id}: requires 1 <= number <= limit.")
        if entry.get("status") not in _ATTEMPT_STATUSES:
            fail("attempts", f"{attempt_id}: invalid status {entry.get('status')!r}.")
        intent = entry.get("intent")
        if intent not in _ATTEMPT_INTENTS:
            fail(
                "attempts",
                f"{attempt_id}: intent must be one of {sorted(_ATTEMPT_INTENTS)}.",
            )
        elif intent == "body_entry":
            if spec.purpose.value != "discovery":
                fail(
                    "attempts",
                    f"{attempt_id}: body_entry intent is only valid on a discovery case.",
                )
            elif number != 1 or limit != 1:
                fail(
                    "attempts",
                    f"{attempt_id}: a body-entry intent is exactly 1 of 1.",
                )
        elif isinstance(limit, int) and limit > spec.max_control_attempts:
            fail("attempts", f"{attempt_id}: limit exceeds the released bound {spec.max_control_attempts}.")
        if not isinstance(entry.get("journal_ref"), str) or not entry.get("journal_ref"):
            fail("attempts", f"{attempt_id}: requires a nonempty journal_ref.")
        dispatch_event_id = entry.get("dispatch_event_id")
        if entry.get("status") == "dispatched" and dispatch_event_id is None:
            fail("attempts", f"{attempt_id}: a dispatched attempt requires a dispatch_event_id.")
        if entry.get("status") in {"refused", "annotation_timeout", "unfinished"} and (
            dispatch_event_id is not None
        ):
            fail(
                "attempts",
                f"{attempt_id}: a {entry.get('status')} attempt must not carry a dispatch_event_id.",
            )
        if dispatch_event_id is not None:
            event = event_by_id.get(dispatch_event_id)
            if (event is None or event.get("case_id") != case_id
                    or event.get("kind") != "receipt"):
                fail("attempts", f"{attempt_id}: dispatch_event_id must be a case event of this case.")
        if isinstance(number, int):
            per_case_numbers.setdefault(str(case_id), []).append(number)
    for case_id, numbers in per_case_numbers.items():
        if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
            fail("attempts", f"{case_id}: attempt numbers must be strictly increasing.")
    for case_id, row in result_by_id.items():
        if row.get("status") != "passed":
            continue
        spec = specs[case_id]
        sent = [a for a in attempts if isinstance(a, dict) and a.get("case_id") == case_id
                and a.get("status") == "dispatched"]
        if len(sent) != 1:
            fail("attempts", f"{case_id}: passed case requires one journaled confirmed dispatch.")
        elif spec.purpose.value == "discovery":
            if sent[0].get("dispatch_event_id") != row.get("body_entry_event_id"):
                fail("attempts", f"{case_id}: body intent must bind the body receipt.")
        else:
            if sent[0].get("intent") != "control":
                fail("attempts", f"{case_id}: passed return lacks its control intent.")
            owner = result_by_id.get(spec.body_case_id, {})
            if owner.get("body_entry_event_id") != row.get("body_entry_event_id"):
                fail("binding", f"{case_id}: return must retain its declared discovery receipt.")
        if len(sent) == 1:
            event = event_by_id.get(sent[0].get("dispatch_event_id"), {})
            frame = (row.get("postcondition") or {}).get("frame")
            source = event.get("source_frame", {})
            if isinstance(frame, dict) and source:
                if (frame.get("session_id") != source.get("session_id")
                        or frame.get("session_epoch") != source.get("session_epoch")
                        or frame.get("input_sequence") != event.get("dispatch", {}).get("input_sequence")
                        or frame.get("capture_sequence", -1) <= source.get("capture_sequence", -1)):
                    fail("binding", f"{case_id}: postcondition frame does not follow its recorded input.")

    # --- Totals ---------------------------------------------------------------
    totals = doc.get("totals")
    if not isinstance(totals, dict):
        fail("totals", "totals must be an object.")
    else:
        counts = {"tap": 0, "swipe": 0, "wheel": 0, "dispatch_records": 0, "dispatch_failures": 0}
        for entry in event_by_id.values():
            if entry.get("kind") == "receipt":
                counts["dispatch_records"] += 1
                primitive = entry.get("primitive")
                if primitive in counts:
                    counts[primitive] += 1
            elif entry.get("kind") == "failure":
                counts["dispatch_failures"] += 1
        counts["logical_attempts"] = len(attempts)
        for key, expected in counts.items():
            if totals.get(key) != expected:
                fail("totals", f"totals.{key} expected {expected}, got {totals.get(key)!r}.")

    # --- Coverage / cleanup / terminal check ----------------------------------
    coverage = doc.get("coverage")
    if not isinstance(coverage, dict):
        fail("coverage", "coverage must be an object.")
    else:
        if not _is_iso(coverage.get("start")) or not _is_iso(coverage.get("end")):
            fail("coverage", "coverage start/end must be ISO-8601 timestamps.")
        primitives = coverage.get("unsupported_input_primitives")
        if not isinstance(primitives, list) or not all(isinstance(p, str) for p in primitives):
            fail("coverage", "coverage.unsupported_input_primitives must be a list of strings.")
    cleanup = doc.get("cleanup")
    if not isinstance(cleanup, dict):
        fail("cleanup", "cleanup must be an object.")
    else:
        for key, expected in binding.expected_cleanup.items():
            if expected and cleanup.get(key) is not True:
                fail("cleanup", f"cleanup.{key} must be true.")
        if cleanup.get("reservation_disposition") != binding.reservation_disposition:
            fail("cleanup", "cleanup.reservation_disposition must match the binding.")
    terminal = doc.get("terminal_binding_check")
    if not isinstance(terminal, dict):
        fail("terminal", "terminal_binding_check must be an object.")
    else:
        for key in ("head_matches", "tree_clean", "entry_sha256_matches", "execution_identity_matches"):
            if terminal.get(key) is not True:
                fail("terminal", f"terminal_binding_check.{key} must be true.")
        if not _is_iso(terminal.get("checked_at")):
            fail("terminal", "terminal_binding_check.checked_at must be ISO-8601.")
        if terminal.get("head_matches") is False or terminal.get("tree_clean") is False:
            fail("terminal", "the final source check did not reproduce the bound candidate.")
    final_state = doc.get("observed_final_state")
    if not isinstance(final_state, dict):
        fail("final_state", "observed_final_state must be an object.")
    else:
        for key in ("screen_type", "blocking_popup", "artifact_path", "frame_fingerprint"):
            if key not in final_state:
                fail("final_state", f"observed_final_state missing '{key}'.")

    return ValidationReport(valid=not findings, findings=tuple(findings))
