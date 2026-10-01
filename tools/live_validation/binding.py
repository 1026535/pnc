"""Released-assignment binding for tracked live validation runs.

The binding is the released authority for one run: it names the exact clean
Git candidate, source/import/report roots, tracked entry point, configured
target, selected frozen cases, and terminal cleanup disposition. It contains
no credentials and no local account-config contents. Nothing in a produced
result may grant authority this document did not release.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")

_EXPECTED_CLEANUP_KEYS = frozenset({
    "session_closed",
    "lease_released",
    "observer_restored",
    "instance_preserved",
})


class AssignmentBindingError(ValueError):
    """The released assignment document is malformed or inconsistent."""


@dataclass(frozen=True, slots=True)
class OfflineEvidenceRef:
    """One required offline evidence file the assignment depends on."""

    path: Path
    sha256: str
    description: str


@dataclass(frozen=True, slots=True)
class CaseSelection:
    """One selected frozen case and its exact released parameters."""

    case_id: str
    params: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AssignmentBinding:
    """Exact released authority a tracked runner must satisfy before connecting."""

    assignment_id: str
    run_id: str
    candidate_sha: str
    source_root: Path
    import_root: Path
    report_root: Path
    entry_point: Path
    entry_sha256: str
    target_account_id: str
    target_castle_ref: str
    target_instance_id: str
    target_role: str
    selected_cases: tuple[CaseSelection, ...]
    resource_allowance_ref: str | None
    reservation_disposition: str
    expected_cleanup: dict[str, bool]
    offline_evidence: tuple[OfflineEvidenceRef, ...]
    config_path: Path | None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssignmentBindingError(message)


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AssignmentBindingError(f"Assignment field '{key}' requires a nonempty string.")
    return value


def _require_path(payload: dict[str, Any], key: str) -> Path:
    return Path(_require_str(payload, key))


def load_assignment_binding(path: Path) -> AssignmentBinding:
    """Parses one released assignment document with strict field validation."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssignmentBindingError(f"Assignment cannot be read as JSON: {error}") from error
    _require(isinstance(payload, dict), "Assignment document must be a JSON object.")
    _require(
        payload.get("schema_version") == SCHEMA_VERSION,
        f"Assignment schema_version must be {SCHEMA_VERSION}.",
    )

    selected_raw = payload.get("selected_cases")
    _require(isinstance(selected_raw, list) and selected_raw, "Assignment requires a nonempty selected_cases list.")
    selected: list[CaseSelection] = []
    for index, entry in enumerate(selected_raw):
        _require(isinstance(entry, dict), f"selected_cases[{index}] must be an object.")
        case_id = entry.get("case_id")
        params = entry.get("params", {})
        _require(isinstance(case_id, str) and case_id.strip(), f"selected_cases[{index}].case_id is required.")
        _require(isinstance(params, dict), f"selected_cases[{index}].params must be an object.")
        selected.append(CaseSelection(case_id=case_id, params=dict(params)))
    ids = [selection.case_id for selection in selected]
    _require(len(ids) == len(set(ids)), "Assignment selected_cases must not repeat a case id.")

    evidence_raw = payload.get("offline_evidence", [])
    _require(isinstance(evidence_raw, list), "Assignment offline_evidence must be a list.")
    offline_evidence: list[OfflineEvidenceRef] = []
    for index, entry in enumerate(evidence_raw):
        _require(isinstance(entry, dict), f"offline_evidence[{index}] must be an object.")
        ref_path = entry.get("path")
        ref_sha = entry.get("sha256")
        description = entry.get("description", "")
        _require(isinstance(ref_path, str) and ref_path.strip(), f"offline_evidence[{index}].path is required.")
        _require(
            isinstance(ref_sha, str) and _HEX64.fullmatch(ref_sha) is not None,
            f"offline_evidence[{index}].sha256 must be a lowercase SHA-256 hex string.",
        )
        _require(isinstance(description, str), f"offline_evidence[{index}].description must be a string.")
        offline_evidence.append(
            OfflineEvidenceRef(path=Path(ref_path), sha256=ref_sha, description=description)
        )

    cleanup_raw = payload.get("expected_cleanup")
    _require(isinstance(cleanup_raw, dict) and cleanup_raw, "Assignment expected_cleanup must be a nonempty object.")
    expected_cleanup: dict[str, bool] = {}
    for key, value in cleanup_raw.items():
        _require(key in _EXPECTED_CLEANUP_KEYS, f"Assignment expected_cleanup has unknown key '{key}'.")
        _require(isinstance(value, bool), f"Assignment expected_cleanup['{key}'] must be a boolean.")
        expected_cleanup[key] = value

    candidate_sha = _require_str(payload, "candidate_sha")
    _require(
        _HEX40.fullmatch(candidate_sha) is not None,
        "Assignment candidate_sha must be a lowercase 40-hex Git SHA.",
    )
    entry_sha256 = _require_str(payload, "entry_sha256")
    _require(
        _HEX64.fullmatch(entry_sha256) is not None,
        "Assignment entry_sha256 must be a lowercase SHA-256 hex string.",
    )
    config_path_raw = payload.get("config_path")
    _require(
        config_path_raw is None or (isinstance(config_path_raw, str) and config_path_raw.strip()),
        "Assignment config_path must be a nonempty string when present.",
    )

    return AssignmentBinding(
        assignment_id=_require_str(payload, "assignment_id"),
        run_id=_require_str(payload, "run_id"),
        candidate_sha=candidate_sha,
        source_root=_require_path(payload, "source_root"),
        import_root=_require_path(payload, "import_root"),
        report_root=_require_path(payload, "report_root"),
        entry_point=_require_path(payload, "entry_point"),
        entry_sha256=entry_sha256,
        target_account_id=_require_str(payload, "target_account_id"),
        target_castle_ref=_require_str(payload, "target_castle_ref"),
        target_instance_id=_require_str(payload, "target_instance_id"),
        target_role=_require_str(payload, "target_role"),
        selected_cases=tuple(selected),
        resource_allowance_ref=(
            payload.get("resource_allowance_ref")
            if isinstance(payload.get("resource_allowance_ref"), str)
            else None
        ),
        reservation_disposition=_require_str(payload, "reservation_disposition"),
        expected_cleanup=expected_cleanup,
        offline_evidence=tuple(offline_evidence),
        config_path=None if config_path_raw is None else Path(config_path_raw),
    )


def binding_static_findings(binding: AssignmentBinding, *, case_ids: frozenset[str]) -> list[str]:
    """Returns the static findings that must all be absent before connecting.

    The supplied ``case_ids`` are the frozen registry's known case ids; this
    function does not import the registry so binding stays dependency-free.
    """

    findings: list[str] = []
    if not binding.entry_point.is_absolute():
        findings.append("entry_point must be absolute.")
    if not binding.source_root.is_absolute():
        findings.append("source_root must be absolute.")
    if not binding.report_root.is_absolute():
        findings.append("report_root must be absolute.")
    for selection in binding.selected_cases:
        if selection.case_id not in case_ids:
            findings.append(f"selected case '{selection.case_id}' is not in the frozen registry.")
    if binding.target_role != "live_testing":
        findings.append("target_role must be 'live_testing'.")
    return findings
