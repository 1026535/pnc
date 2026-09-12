"""Per-test results and atomic, reproducible test evidence artifacts."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import os
import platform
import time
import unittest
from collections.abc import Iterable
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
    fields = ["schema_version", "run_id", "commit_sha", "source_fingerprint", "utc_timestamp", "python", "tool_versions", "fixture_profile", "total_run_seconds", "test_id", "module", "class_id", "scope", "phase", "covered_test_ids", "tier", "component", "status", "skip_reason", "duration_seconds"]
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
