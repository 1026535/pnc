"""Per-test results and atomic, reproducible test evidence artifacts."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import os
import platform
import time
import unittest
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TypedDict
from uuid import uuid4


def write_json(path: Path, document: dict) -> None:
    """Replace a generated document atomically; concurrent runs use unique temp files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def environment() -> dict:
    """Record package versions, never environment variable contents or credentials."""
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": dict(sorted((d.metadata["Name"].lower(), d.version) for d in importlib.metadata.distributions() if d.metadata["Name"]))}


class TestIdentity(TypedDict):
    """Discovery identity independent of fixture or subtest display IDs."""

    test_id: str
    module: str
    class_id: str


class RecordOwner(TypedDict):
    """Canonical owner and tests accounted for by a unittest outcome."""

    module: str
    class_id: str
    scope: str
    phase: str
    covered_test_ids: list[str]


def describe_tests(cases: Iterable[unittest.TestCase]) -> list[TestIdentity]:
    """Capture discovery before unittest consumes its suite."""
    return [
        {"test_id": test.id(), "module": type(test).__module__,
         "class_id": f"{type(test).__module__}.{type(test).__qualname__}"}
        for test in cases
    ]


def summarize_module_timings(
    records: Iterable[dict],
    module_wall_seconds: Mapping[str, float] | None = None,
) -> list[dict]:
    """Aggregate test durations and terminal outcomes by owning module."""
    module_wall_seconds = module_wall_seconds or {}
    modules: dict[str, dict] = {}
    for record in records:
        module = record["module"]
        summary = modules.setdefault(module, {
            "module": module,
            "test_count": 0,
            "test_duration_seconds": 0.0,
            "wall_time_seconds": None,
            "slowest_test_seconds": 0.0,
            "test_status_counts": {},
            "recorded_fixture_count": 0,
        })
        if record["scope"] != "test":
            summary["recorded_fixture_count"] += 1
            continue
        duration = float(record.get("duration_seconds", 0.0))
        summary["test_count"] += 1
        summary["test_duration_seconds"] += duration
        summary["slowest_test_seconds"] = max(
            summary["slowest_test_seconds"], duration
        )
        status = record["status"]
        status_counts = summary["test_status_counts"]
        status_counts[status] = status_counts.get(status, 0) + 1

    for summary in modules.values():
        module = summary["module"]
        summary["test_duration_seconds"] = round(
            summary["test_duration_seconds"], 6
        )
        if module in module_wall_seconds:
            summary["wall_time_seconds"] = round(module_wall_seconds[module], 6)
        summary["slowest_test_seconds"] = round(
            summary["slowest_test_seconds"], 6
        )
        summary["test_status_counts"] = dict(
            sorted(summary["test_status_counts"].items())
        )
    return [modules[module] for module in sorted(modules)]


def summarize_run_timing(
    records: list[dict],
    *,
    phase_seconds: Mapping[str, float],
    total_run_seconds: float,
    module_wall_seconds: Mapping[str, float] | None = None,
) -> dict:
    """Return phase, test, module, and unaccounted wall-time summaries."""
    phases = {
        name: round(float(seconds), 6)
        for name, seconds in sorted(phase_seconds.items())
    }
    test_seconds = round(sum(
        float(record.get("duration_seconds", 0.0))
        for record in records
        if record.get("scope") == "test"
    ), 6)
    total = round(float(total_run_seconds), 6)
    phase_total = sum(phases.values())
    return {
        "phases": phases,
        "test_execution_seconds": test_seconds,
        "unattributed_seconds": round(max(0.0, total - phase_total), 6),
        "modules": summarize_module_timings(records, module_wall_seconds),
    }


def record_owners(inventory: list[TestIdentity]) -> dict[str, RecordOwner]:
    """Index ordinary and CPython class/module fixture IDs without guessing owners.

    Setup failure/skip accounts for the affected discovered tests. Teardown
    failures account for no missing execution. The audit uses this same contract.
    """
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("A nonempty discovered test inventory is required")
    owners: dict[str, RecordOwner] = {}
    classes: dict[str, tuple[str, list[str]]] = {}
    modules: dict[str, list[str]] = {}
    for identity in inventory:
        if (not isinstance(identity, dict)
                or set(identity) != {"test_id", "module", "class_id"}
                or any(not isinstance(value, str) or not value.strip()
                       for value in identity.values())):
            raise ValueError("Malformed discovered test identity")
        test_id, module, class_id = (
            identity["test_id"], identity["module"], identity["class_id"]
        )
        if (test_id in owners or not class_id.startswith(module + ".")
                or not test_id.startswith(class_id + ".")):
            raise ValueError("Duplicate or inconsistent discovered test identity")
        owners[test_id] = {
            "module": module, "class_id": class_id, "scope": "test",
            "phase": "test", "covered_test_ids": [test_id],
        }
        classes.setdefault(class_id, (module, []))[1].append(test_id)
        modules.setdefault(module, []).append(test_id)
    for scope, groups in (
        ("class", classes),
        ("module", {module: (module, ids) for module, ids in modules.items()}),
    ):
        for target, (module, ids) in groups.items():
            for prefix in ("setUp", "tearDown"):
                phase = prefix + scope.title()
                fixture_id = f"{phase} ({target})"
                if fixture_id in owners:
                    raise ValueError("Fixture identity collides with discovered test")
                owners[fixture_id] = {
                    "module": module,
                    "class_id": target if scope == "class" else "",
                    "scope": scope, "phase": phase,
                    "covered_test_ids": sorted(ids) if prefix == "setUp" else [],
                }
    return owners


class TimedTestSuite(unittest.TestSuite):
    """Measure the wall time of one module suite, including shared fixtures."""

    def __init__(self, module: str, tests=()):
        super().__init__(tests)
        self.module = module

    def run(self, result, debug=False):
        started = time.perf_counter()
        try:
            return super().run(result, debug)
        finally:
            record_timing = getattr(result, "record_module_timing", None)
            if record_timing is not None:
                record_timing(self.module, time.perf_counter() - started)


class TimingResult(unittest.TextTestResult):
    """Record skips, failures, subtest failures, and per-test setup/cleanup duration."""

    def __init__(
        self,
        *args,
        inventory: list[TestIdentity],
        coverage=None,
        switch_contexts: bool = True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.coverage = coverage
        self.switch_contexts = coverage is not None and switch_contexts
        self.owners = record_owners(inventory)
        self.records: dict[str, dict] = {}
        self.started: dict[str, float] = {}
        self.module_wall_seconds: dict[str, float] = {}

    def record_module_timing(self, module: str, duration: float) -> None:
        """Record module wall time, including class/module fixture lifecycle."""
        self.module_wall_seconds[module] = round(
            self.module_wall_seconds.get(module, 0.0) + duration, 6
        )

    def startTest(self, test):
        self.started[test.id()] = time.perf_counter()
        self.records[test.id()] = self._record(test)
        if self.switch_contexts:
            self.coverage.switch_context(test.id())
        super().startTest(test)

    def stopTest(self, test):
        self.records[test.id()]["duration_seconds"] = round(time.perf_counter() - self.started.pop(test.id()), 6)
        if self.switch_contexts:
            # Imports and class/module fixtures must not inherit the previous test.
            self.coverage.switch_context("")
        super().stopTest(test)

    def _record(self, test) -> dict:
        test_id = test.id()
        if test_id not in self.owners:
            raise ValueError(f"Outcome has no discovered owner: {test_id}")
        return {"test_id": test_id, **self.owners[test_id], "status": "started",
                "skip_reason": "", "duration_seconds": 0.0}

    def outcome(self, test, status: str, reason: str = "") -> None:
        self.records.setdefault(test.id(), self._record(test))
        priority = {"started": 0, "passed": 1, "skipped": 2, "expected_failure": 3,
                    "unexpected_success": 4, "failed": 5, "error": 6}
        previous = self.records[test.id()].get("status", "started")
        # Cleanup/teardown can report a skip after an earlier failure or error.
        if priority[status] >= priority[previous]:
            self.records[test.id()].update(status=status, skip_reason=reason)

    def addSuccess(self, test):
        self.outcome(test, "passed")
        super().addSuccess(test)

    def addFailure(self, test, err):
        self.outcome(test, "failed")
        super().addFailure(test, err)

    def addError(self, test, err):
        self.outcome(test, "error")
        super().addError(test, err)

    def addSkip(self, test, reason):
        # unittest reports a subtest skip separately but does not start that ID.
        owner = test.test_case if isinstance(test, unittest.case._SubTest) else test
        self.outcome(owner, "skipped", reason)
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self.outcome(test, "expected_failure")
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self.outcome(test, "unexpected_success")
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            status = "failed" if issubclass(err[0], test.failureException) else "error"
            self.outcome(test, status)
        super().addSubTest(test, subtest, err)


def write_timings(path: Path, records: list[dict], metadata: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "schema_version", "run_id", "commit_sha", "source_fingerprint",
        "utc_timestamp", "python", "tool_versions", "fixture_profile",
        "total_run_seconds", "selection_seconds", "collection_seconds",
        "execution_seconds", "reporting_seconds", "test_execution_seconds",
        "unattributed_seconds", "test_id", "module", "class_id", "scope",
        "phase", "covered_test_ids", "tier", "component", "status",
        "skip_reason", "duration_seconds",
    ]
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for record in records:
                parts = record["module"].split(".")
                row = {key: metadata.get(key, "") for key in fields}
                row.update(record)
                row["tier"] = parts[1] if len(parts) > 1 else "setup"
                row["component"] = ".".join(parts[2:-1])
                row["covered_test_ids"] = json.dumps(record["covered_test_ids"])
                writer.writerow(row)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
