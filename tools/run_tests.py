"""Run and explain portable unittest groups, affected tests, and measurements."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml

if __package__ in {None, ""}:
    from _script_bootstrap import ensure_repo_root_on_path
    ensure_repo_root_on_path()

from tools.test_selection.contexts import add_contexts, fingerprint, seed_contexts
from tools.test_selection.git_changes import base_revision, changed_paths, python_snapshot, resolve, working_paths
from tools.test_selection.models import SelectionPlan, inventory
from tools.test_selection.ownership import group_matches, load_rules
from tools.test_selection.planner import affected_plan
from tools.test_selection.reporting import TimingResult, describe_tests, environment, write_json, write_timings

ROOT = Path(__file__).resolve().parents[1]


def local_report_root() -> Path:
    """Returns the generated report root for the current repository root."""

    return ROOT / ".local-data" / "reports"


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def main(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("full", "group", "affected", "measure"))
    parser.add_argument("group", nargs="?")
    parser.add_argument("--base", help="Git revision to compare with candidate (default: merge base with upstream)")
    parser.add_argument("--dry-run", action="store_true", help="Print selection without importing tests")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--json", type=Path, default=ROOT / ".test-impact/selection.json")
    parser.add_argument(
        "--csv",
        type=Path,
        help="Per-test timing output (measure defaults to .local-data/reports/test_timings.csv)",
    )
    parser.add_argument("--results", type=Path, default=ROOT / ".test-impact/results.json")
    parser.add_argument("--contexts", action="store_true", help="Use optional additive coverage seed; invalid seed runs full")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    # Portable runs have no authority to activate opt-in runtime tests.
    for key in tuple(os.environ):
        if key.startswith("PNC_RUN_LIVE"):
            os.environ.pop(key)
    os.environ["PNC_TEST_FIXTURE_PROFILE"] = "portable"
    os.chdir(ROOT)
    try:
        head = resolve(ROOT, "HEAD")
        paths = working_paths(ROOT)
        tests = inventory(paths)
        if not tests:
            raise ValueError("No portable tests found under unit/contract/integration/architecture")
        new = python_snapshot(ROOT, None)
        # Bind audit evidence to resources and configuration as well as Python.
        candidate_fingerprint = fingerprint({
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths
        })
        if args.mode == "affected":
            try:
                base = base_revision(ROOT, args.base)
                changed = changed_paths(ROOT, base)
                old = python_snapshot(ROOT, base)
                rules = load_rules(ROOT / "tests/selection_rules.yaml", tests)
                plan = affected_plan(tests, rules, changed, old, new, base, head)
                if args.contexts:
                    add_contexts(plan, ROOT / ".test-impact/contexts.json", old, tests)
            except (ValueError, OSError, UnicodeError, yaml.YAMLError) as error:
                plan = SelectionPlan("affected", args.base or "unresolved", head)
                plan.full(tests, f"selection analysis unavailable: {error}")
        else:
            plan = SelectionPlan(args.mode, head, head)
            for test in tests:
                if args.mode != "group" or (args.group and group_matches(test, args.group)):
                    plan.add(test.module, f"explicit {args.mode} {args.group or ''}".strip())
            if not plan.reasons:
                raise ValueError(f"Unknown or empty group: {args.group}")
        plan.source_fingerprint = candidate_fingerprint
        plan.inventory_modules = sorted(test.module for test in tests)
        write_json(args.json, plan.document())
        print(f"{args.mode}: {len(plan.reasons)}/{len(tests)} portable modules; {len(plan.fallbacks)} full-suite reasons", flush=True)
        if args.explain or args.dry_run:
            print(json.dumps(plan.document(), indent=2))
        if args.dry_run:
            return 0
        if not plan.reasons:
            print("No test execution required: unchanged or explicitly documentation-only changes.")
            write_json(args.results, {"head": head, "tests": [], "succeeded": True, "no_tests_reason": "unchanged or documentation-only", "selection": plan.document()})
            return 0
        coverage = None
        if args.mode == "measure":
            from coverage import Coverage
            # An interrupted measurement must not leave an apparently valid seed.
            (ROOT / ".test-impact/contexts.json").unlink(missing_ok=True)
            coverage = Coverage(branch=True, source=["pnc_automation"], config_file=False,
                                data_file=str(ROOT / ".test-impact" / f"coverage-{uuid4().hex}"))
            coverage.start()
        loader = unittest.TestLoader()
        selected = unittest.TestSuite(loader.loadTestsFromName(name) for name in sorted(plan.reasons))
        discovered = describe_tests(flatten(selected))
        ids = [test["test_id"] for test in discovered]
        if len(ids) != len(set(ids)) or not ids:
            raise ValueError("Selected inventory contains duplicate tests or is unexpectedly empty")
        runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1,
            resultclass=lambda *a, **kw: TimingResult(*a, coverage=coverage, inventory=discovered, **kw))
        result = runner.run(selected)
        if coverage:
            coverage.stop()
            coverage.save()
            coverage.json_report(outfile=str(ROOT / ".test-impact/coverage.json"))
            coverage.report(skip_empty=True)
            if result.wasSuccessful() and len(plan.reasons) == len(tests):
                seed_contexts(ROOT / ".test-impact/contexts.json", coverage, ROOT, new, tests, head)
            else:
                (ROOT / ".test-impact/contexts.json").unlink(missing_ok=True)
        elapsed = round(time.perf_counter() - started, 6)
        env = environment()
        metadata = {"schema_version": 1, "run_id": uuid4().hex, "commit_sha": head,
                    "source_fingerprint": candidate_fingerprint, "utc_timestamp": datetime.now(timezone.utc).isoformat(),
                    "python": env["python"], "fixture_profile": "portable",
                    "tool_versions": json.dumps({k: v for k, v in env["packages"].items() if k in {"coverage", "pytest", "pytest-testmon"}}, sort_keys=True),
                    "total_run_seconds": elapsed}
        records = sorted(result.records.values(), key=lambda row: row["test_id"])
        write_json(args.results, {"metadata": metadata, "environment": env, "selection": plan.document(),
                   "discovered_test_ids": ids, "discovered_tests": discovered,
                   "inventory_modules": plan.inventory_modules,
                   "tests": records, "succeeded": result.wasSuccessful()})
        csv_path = args.csv or (local_report_root() / "test_timings.csv" if args.mode == "measure" else None)
        if csv_path:
            write_timings(csv_path, records, metadata)
        print(f"Total including selection/collection/reporting: {elapsed:.3f}s", flush=True)
        return 0 if result.wasSuccessful() else 1
    except (ValueError, OSError, ImportError) as error:
        print(f"Offline test runner failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
