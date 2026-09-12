"""Audit same-source completeness using actual unittest outcome records."""

from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.audit_test_selection import audit, main
from tools.test_selection.reporting import describe_tests, write_json
from tests.unit.test_harness.test_reporting import run_cases


def make_case(module: str, status: str = "passed") -> unittest.TestCase:
    """Build a real testcase with stable module/class identity."""
    def body(self) -> None:
        if status in {"failed", "expected_failure"}:
            self.fail("intentional failure")
        if status == "error":
            raise RuntimeError("intentional error")
        if status == "skipped":
            self.skipTest("intentional skip")

    if status in {"expected_failure", "unexpected_success"}:
        body = unittest.expectedFailure(body)
    case_type = type(
        "Case", (unittest.TestCase,),
        {"__module__": module, "test_result": body},
    )
    return case_type("test_result")


def evidence(*cases: unittest.TestCase) -> tuple[dict, dict]:
    """Run synthetic cases and retain the canonical discovery contract."""
    discovery = describe_tests(cases)
    modules = sorted({test["module"] for test in discovery})
    result = run_cases(*cases)
    shared = {
        "head": "candidate-sha", "base": "base-sha",
        "source_fingerprint": "a" * 64, "inventory_modules": modules,
    }
    plan = {
        **shared, "mode": "affected",
        "reasons": {modules[0]: ["static dependency"]},
    }
    results = {
        "metadata": {
            "commit_sha": "candidate-sha", "source_fingerprint": "a" * 64,
        },
        "selection": {
            **shared, "mode": "full",
            "reasons": {module: ["explicit full"] for module in modules},
        },
        "inventory_modules": modules,
        "discovered_tests": discovery,
        "discovered_test_ids": [test["test_id"] for test in discovery],
        "tests": list(result.records.values()),
        "succeeded": result.wasSuccessful(),
    }
    return plan, results


class SelectionAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan, self.results = evidence(
            make_case("tests.unit.core.test_worker"),
            make_case("tests.unit.core.test_worker_extra"),
        )

    def test_reports_unselected_failures_using_explicit_module_owners(self) -> None:
        cases = [
            make_case("tests.unit.core.test_worker", "failed"),
            make_case("tests.unit.core.test_worker_extra", "failed"),
            make_case("tests.contract.api.test_api", "error"),
            make_case("tests.integration.app.test_runner", "unexpected_success"),
            *[
                make_case(f"tests.unit.other.test_{status}", status)
                for status in ("passed", "skipped", "expected_failure")
            ],
        ]
        plan, results = evidence(*cases)
        plan["reasons"] = {"tests.unit.core.test_worker": ["static dependency"]}
        report = audit(plan, results)
        self.assertEqual(
            report["full_failures"], [case.id() for case in cases[:4]]
        )
        self.assertEqual(
            report["missed_failures"], [case.id() for case in cases[1:4]]
        )
        self.assertFalse(report["no_observed_misses"])
        self.assertEqual(report["selected_modules"], 1)
        self.assertEqual(report["covered_tests"], len(cases))

    def test_full_and_measure_accept_complete_passing_and_failing_runs(self) -> None:
        for mode in ("full", "measure"):
            for status in ("passed", "failed"):
                with self.subTest(mode=mode, status=status):
                    plan, results = evidence(
                        make_case("tests.unit.test_worker", status)
                    )
                    results["selection"]["mode"] = mode
                    report = audit(plan, results)
                    self.assertTrue(report["audit_valid"])
                    self.assertTrue(report["no_observed_misses"])
                    self.assertEqual(report["missed_failures"], [])

    def test_rejects_different_candidate_in_metadata_or_full_selection(self) -> None:
        for container, key in (
            ("metadata", "commit_sha"), ("selection", "head")
        ):
            with self.subTest(container=container):
                results = copy.deepcopy(self.results)
                results[container][key] = "other-candidate"
                with self.assertRaisesRegex(ValueError, "different candidates"):
                    audit(self.plan, results)

    def test_rejects_partial_run_evidence(self) -> None:
        for mode in ("affected", "group"):
            with self.subTest(mode=mode):
                self.results["selection"]["mode"] = mode
                with self.assertRaisesRegex(ValueError, "independent full run"):
                    audit(self.plan, self.results)

    def test_rejects_stale_missing_or_invalid_source_fingerprint(self) -> None:
        for location in ("plan", "metadata", "selection"):
            for fingerprint in ("b" * 64, "", None, "invalid"):
                with self.subTest(location=location, fingerprint=fingerprint):
                    plan, results = copy.deepcopy((self.plan, self.results))
                    target = plan if location == "plan" else results[location]
                    target["source_fingerprint"] = fingerprint
                    with self.assertRaisesRegex(ValueError, "[Ff]ingerprint"):
                        audit(plan, results)

    def test_rejects_empty_or_missing_inventory_and_records(self) -> None:
        for field in (
            "inventory_modules", "discovered_tests",
            "discovered_test_ids", "tests",
        ):
            for value in ([], None):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        audit(self.plan, {**self.results, field: value})

    def test_rejects_malformed_artifacts_and_duplicate_discovery(self) -> None:
        for value in (None, [], True, 7, "artifact"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    audit(value, self.results)
                with self.assertRaises(ValueError):
                    audit(self.plan, value)
        for field in ("discovered_tests", "discovered_test_ids"):
            with self.subTest(field=field):
                results = copy.deepcopy(self.results)
                results[field].append(results[field][0])
                with self.assertRaises(ValueError):
                    audit(self.plan, results)

    def test_rejects_missing_duplicate_and_unfinished_outcomes(self) -> None:
        for records in (
            self.results["tests"][:1],
            self.results["tests"] + [self.results["tests"][0]],
            [
                {**self.results["tests"][0], "status": "started"},
                self.results["tests"][1],
            ],
        ):
            with self.subTest(records=records):
                with self.assertRaises(ValueError):
                    audit(self.plan, {**self.results, "tests": records})

    def test_rejects_inventory_omissions_even_if_remaining_tests_passed(self) -> None:
        mutations = [
            lambda r: r["selection"]["reasons"].pop(
                "tests.unit.core.test_worker_extra"
            ),
            lambda r: r["inventory_modules"].pop(),
            lambda r: r["discovered_tests"].pop(),
            lambda r: r["discovered_test_ids"].pop(),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                results = copy.deepcopy(self.results)
                mutate(results)
                with self.assertRaises(ValueError):
                    audit(self.plan, results)

    def test_rejects_forged_owner_coverage_and_success_flag(self) -> None:
        for field, value in (
            ("module", "tests.unit.wrong"),
            ("covered_test_ids", self.results["discovered_test_ids"]),
            ("class_id", "wrong.Class"),
            ("scope", "module"),
        ):
            with self.subTest(field=field):
                results = copy.deepcopy(self.results)
                results["tests"][0][field] = value
                with self.assertRaisesRegex(ValueError, "ownership"):
                    audit(self.plan, results)
        with self.assertRaisesRegex(ValueError, "success flag"):
            audit(self.plan, {**self.results, "succeeded": False})

    def test_class_setup_error_and_skip_cover_exact_discovered_class(self) -> None:
        for exception in (RuntimeError, unittest.SkipTest):
            with self.subTest(exception=exception):
                class Case(unittest.TestCase):
                    @classmethod
                    def setUpClass(cls) -> None:
                        raise exception("class setup outcome")

                    def test_first(self) -> None:
                        self.fail("setup should prevent body")

                    def test_second(self) -> None:
                        self.fail("setup should prevent body")

                cases = [Case("test_first"), Case("test_second")]
                plan, results = evidence(*cases)
                record = results["tests"][0]
                self.assertEqual(record["module"], Case.__module__)
                self.assertEqual(
                    record["covered_test_ids"],
                    sorted(case.id() for case in cases),
                )
                report = audit(plan, results)
                self.assertEqual(report["covered_tests"], 2)
                self.assertTrue(report["no_observed_misses"])
                if exception is RuntimeError:
                    plan["reasons"] = {}
                    self.assertEqual(
                        audit(plan, results)["missed_failures"],
                        [record["test_id"]],
                    )

    def test_module_setup_error_and_skip_cover_only_that_module(self) -> None:
        module = types.ModuleType("tests.unit.test_fixture_module")
        for exception in (RuntimeError, unittest.SkipTest):
            with self.subTest(exception=exception):
                def setup() -> None:
                    raise exception("module setup outcome")

                module.setUpModule = setup
                with patch.dict(sys.modules, {module.__name__: module}):
                    plan, results = evidence(make_case(module.__name__))
                record = results["tests"][0]
                self.assertEqual(record["module"], module.__name__)
                self.assertEqual(record["scope"], "module")
                self.assertEqual(
                    record["test_id"], f"setUpModule ({module.__name__})"
                )
                self.assertEqual(audit(plan, results)["covered_tests"], 1)
                if exception is RuntimeError:
                    plan["reasons"] = {}
                    self.assertEqual(
                        audit(plan, results)["missed_failures"],
                        [record["test_id"]],
                    )

    def test_teardown_fixture_does_not_excuse_missing_execution(self) -> None:
        class Case(unittest.TestCase):
            @classmethod
            def tearDownClass(cls) -> None:
                raise RuntimeError("class teardown outcome")

            def runTest(self) -> None:
                pass

        plan, results = evidence(Case())
        fixture = next(
            row for row in results["tests"] if row["scope"] == "class"
        )
        self.assertEqual(fixture["covered_test_ids"], [])
        self.assertEqual(
            audit(plan, results)["full_failures"], [fixture["test_id"]]
        )
        results["tests"] = [fixture]
        with self.assertRaisesRegex(ValueError, "Incomplete full execution"):
            audit(plan, results)

    def test_fixture_error_cannot_hide_unexecuted_tests_in_another_class(self) -> None:
        class Failing(unittest.TestCase):
            @classmethod
            def setUpClass(cls) -> None:
                raise RuntimeError("class setup outcome")

            def runTest(self) -> None:
                pass

        plan, results = evidence(Failing(), make_case(Failing.__module__))
        results["tests"] = [
            row for row in results["tests"] if row["scope"] == "class"
        ]
        with self.assertRaisesRegex(ValueError, "Incomplete full execution"):
            audit(plan, results)

    def test_module_teardown_error_is_owned_but_cannot_cover_missing_body(self) -> None:
        module = types.ModuleType("tests.unit.test_teardown_module")

        def teardown() -> None:
            raise RuntimeError("module teardown outcome")

        module.tearDownModule = teardown
        with patch.dict(sys.modules, {module.__name__: module}):
            plan, results = evidence(make_case(module.__name__))
        fixture = next(row for row in results["tests"] if row["scope"] == "module")
        self.assertEqual(fixture["module"], module.__name__)
        self.assertEqual(fixture["covered_test_ids"], [])
        self.assertEqual(audit(plan, results)["full_failures"], [fixture["test_id"]])
        results["tests"] = [fixture]
        with self.assertRaisesRegex(ValueError, "Incomplete full execution"):
            audit(plan, results)

    def test_cli_replaces_prior_report_with_invalid_evidence_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            results_path = root / "results.json"
            output_path = root / "reports" / "audit.json"
            write_json(plan_path, self.plan)
            for status, expected_exit in (
                ("passed", 0), ("failed", 1), ("started", 2)
            ):
                with self.subTest(status=status):
                    results = copy.deepcopy(self.results)
                    results["tests"][1]["status"] = status
                    results["succeeded"] = status != "failed"
                    write_json(results_path, results)
                    arguments = [
                        "audit_test_selection.py",
                        str(plan_path), str(results_path),
                        "--output", str(output_path),
                    ]
                    with (
                        patch("sys.argv", arguments),
                        redirect_stdout(io.StringIO()),
                    ):
                        self.assertEqual(main(), expected_exit)
                    report = json.loads(
                        output_path.read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        report["audit_valid"], expected_exit != 2
                    )
                    if expected_exit == 2:
                        self.assertFalse(report["no_observed_misses"])
                        self.assertIn("Incomplete", report["error"])
                    else:
                        self.assertEqual(
                            report, audit(self.plan, results)
                        )
                    self.assertEqual(
                        list(output_path.parent.iterdir()), [output_path]
                    )
