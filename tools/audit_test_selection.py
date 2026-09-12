"""Compare an affected plan with independent full-run failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__ in {None, ""}:
    from _script_bootstrap import ensure_repo_root_on_path
    ensure_repo_root_on_path()

from tools.test_selection.reporting import record_owners, write_json


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _strings(value: object, label: str, *, allow_empty: bool = False) -> set[str]:
    if (not isinstance(value, list) or (not value and not allow_empty)
            or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(value) != len(set(value))):
        raise ValueError(f"{label} must contain unique nonempty strings")
    return set(value)


def _selected(plan: dict, label: str) -> set[str]:
    reasons = _object(plan.get("reasons"), f"{label} reasons")
    for module, values in reasons.items():
        _text(module, f"{label} module")
        _strings(values, f"{label} selection reasons")
    return set(reasons)


def audit(plan: dict, results: dict) -> dict:
    """Validate complete same-source execution before comparing observed failures."""
    plan = _object(plan, "Affected plan")
    results = _object(results, "Full results")
    metadata = _object(results.get("metadata"), "Result metadata")
    full = _object(results.get("selection"), "Full selection")
    head = _text(plan.get("head"), "Candidate SHA")
    base = _text(plan.get("base"), "Base SHA")
    if head != metadata.get("commit_sha") or head != full.get("head"):
        raise ValueError("Selection and full results refer to different candidates")
    if plan.get("mode") != "affected":
        raise ValueError("An affected selection plan is required")
    if full.get("mode") not in ("full", "measure"):
        raise ValueError("An independent full run is required for selection audit")
    fingerprint = _text(plan.get("source_fingerprint"), "Source fingerprint")
    if (len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint)
            or fingerprint != metadata.get("source_fingerprint")
            or fingerprint != full.get("source_fingerprint")):
        raise ValueError("Selection and full results require the same source fingerprint")
    modules = _strings(plan.get("inventory_modules"), "Affected inventory")
    if (modules != _strings(full.get("inventory_modules"), "Full selection inventory")
            or modules != _strings(results.get("inventory_modules"), "Result inventory")
            or modules != _selected(full, "Full")):
        raise ValueError("Full execution must select the complete portable inventory")
    selected = _selected(plan, "Affected")
    if not selected <= modules:
        raise ValueError("Affected selection includes unknown modules")

    discovered = results.get("discovered_tests")
    owners = record_owners(discovered)
    ids = _strings(results.get("discovered_test_ids"), "Discovered test IDs")
    if (ids != {test["test_id"] for test in discovered}
            or modules != {test["module"] for test in discovered}):
        raise ValueError("Discovered tests do not cover the complete portable inventory")
    records = results.get("tests")
    if not isinstance(records, list) or not records:
        raise ValueError("Full results must contain completed outcome records")
    terminal = {"passed", "skipped", "expected_failure", "unexpected_success", "failed", "error"}
    failure_statuses = {"failed", "error", "unexpected_success"}
    seen: set[str] = set()
    covered: set[str] = set()
    failures: list[str] = []
    missed: list[str] = []
    for value in records:
        record = _object(value, "Outcome record")
        test_id = _text(record.get("test_id"), "Outcome test ID")
        status = _text(record.get("status"), "Outcome status")
        if test_id in seen or test_id not in owners:
            raise ValueError("Duplicate or undiscovered outcome record")
        seen.add(test_id)
        owner = owners[test_id]
        if any(record.get(key) != expected for key, expected in owner.items()):
            raise ValueError(f"Outcome ownership disagrees with discovery: {test_id}")
        if status not in terminal:
            raise ValueError(f"Incomplete or unknown outcome status: {status}")
        if owner["scope"] != "test" and status not in {"error", "skipped"}:
            raise ValueError("Class/module fixture outcomes must be errors or skips")
        covered.update(owner["covered_test_ids"])
        if status in failure_statuses:
            failures.append(test_id)
            if record["module"] not in selected:
                missed.append(test_id)
    if covered != ids:
        raise ValueError("Incomplete full execution: some discovered tests have no outcome")
    if type(results.get("succeeded")) is not bool or results["succeeded"] != (not failures):
        raise ValueError("Full success flag disagrees with recorded failures")
    return {"head": head, "base": base, "source_fingerprint": fingerprint,
            "audit_valid": True, "covered_tests": len(covered),
            "selected_modules": len(selected), "full_failures": failures,
            "missed_failures": missed, "no_observed_misses": not missed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".test-impact/audit-result.json"))
    args = parser.parse_args()
    try:
        report = audit(
            json.loads(args.plan.read_text(encoding="utf-8")),
            json.loads(args.results.read_text(encoding="utf-8")),
        )
    except (ValueError, OSError) as error:
        # Replace any prior success report so stale output cannot authorize an audit.
        report = {"audit_valid": False, "no_observed_misses": False, "error": str(error)}
        write_json(args.output, report)
        print(json.dumps(report, indent=2))
        return 2
    write_json(args.output, report)
    print(json.dumps(report, indent=2))
    return 1 if report["missed_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
