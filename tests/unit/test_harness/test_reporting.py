"""Exercise result reporting through real unittest lifecycle callbacks."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.test_selection.reporting import (
    TimingResult, describe_tests, write_json, write_timings,
)


def run_cases(*cases: unittest.TestCase, coverage=None) -> TimingResult:
    """Run synthetic cases without exposing their intentional failures to discovery."""
    return unittest.TextTestRunner(
        stream=io.StringIO(),
        resultclass=lambda *args, **kwargs: TimingResult(
            *args, inventory=describe_tests(cases), coverage=coverage, **kwargs
        ),
    ).run(unittest.TestSuite(cases))


class TimingResultTests(unittest.TestCase):
    def test_failed_subtest_is_preserved_after_later_successful_subtest(self) -> None:
        class Case(unittest.TestCase):
            def runTest(self) -> None:
                for number in (1, 2):
                    with self.subTest(number=number):
                        self.assertEqual(number, 2)

        case = Case()
        result = run_cases(case)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(result.records[case.id()]["status"], "failed")
        self.assertEqual(set(result.records), {case.id()})
        self.assertEqual(result.started, {})
        self.assertEqual(result.records[case.id()]["module"], type(case).__module__)
        self.assertEqual(result.records[case.id()]["scope"], "test")
        self.assertEqual(result.records[case.id()]["covered_test_ids"], [case.id()])

    def test_skip_reports_reason_and_does_not_run_body(self) -> None:
        class Case(unittest.TestCase):
            @unittest.skip("portable fixture unavailable")
            def runTest(self) -> None:
                raise AssertionError("skipped body ran")

        case = Case()
        result = run_cases(case)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.skipped, [(case, "portable fixture unavailable")])
        self.assertEqual(result.records[case.id()]["status"], "skipped")
        self.assertEqual(
            result.records[case.id()]["skip_reason"], "portable fixture unavailable"
        )

    def test_subtest_skip_retains_parent_module_and_terminal_outcome(self) -> None:
        class Case(unittest.TestCase):
            def runTest(self) -> None:
                with self.subTest(part="optional"):
                    self.skipTest("optional subtest")

        case = Case()
        result = run_cases(case)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(set(result.records), {case.id()})
        self.assertEqual(result.records[case.id()]["module"], Case.__module__)
        self.assertEqual(result.records[case.id()]["status"], "skipped")
        self.assertEqual(result.records[case.id()]["covered_test_ids"], [case.id()])

    def test_subtest_error_is_preserved_after_later_skip(self) -> None:
        class Case(unittest.TestCase):
            def runTest(self) -> None:
                with self.subTest(part="broken"):
                    raise RuntimeError("subtest error")
                with self.subTest(part="optional"):
                    self.skipTest("optional subtest")

        case = Case()
        result = run_cases(case)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(set(result.records), {case.id()})
        self.assertEqual(result.records[case.id()]["status"], "error")

    def test_setup_error_has_record_and_retains_traceback(self) -> None:
        class Case(unittest.TestCase):
            def setUp(self) -> None:
                raise RuntimeError("setup exploded")

            def runTest(self) -> None:
                raise AssertionError("body ran after failed setup")

        case = Case()
        result = run_cases(case)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.records[case.id()]["status"], "error")
        self.assertEqual(result.errors[0][0], case)
        self.assertIn("RuntimeError: setup exploded", result.errors[0][1])
        self.assertEqual(result.started, {})

    def test_teardown_skip_does_not_hide_body_failure(self) -> None:
        class Case(unittest.TestCase):
            def runTest(self) -> None:
                self.fail("body failure must survive teardown")

            def tearDown(self) -> None:
                self.skipTest("cleanup fixture unavailable")

        case = Case()
        result = run_cases(case)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.records[case.id()]["status"], "failed")

    def test_cleanup_skip_does_not_hide_setup_error(self) -> None:
        class Case(unittest.TestCase):
            def setUp(self) -> None:
                self.addCleanup(self.skipTest, "cleanup fixture unavailable")
                raise RuntimeError("setup error must survive cleanup")

            def runTest(self) -> None:
                raise AssertionError("body ran after failed setup")

        case = Case()
        result = run_cases(case)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.records[case.id()]["status"], "error")

    def test_class_setup_error_is_reported_without_start_test(self) -> None:
        class Case(unittest.TestCase):
            @classmethod
            def setUpClass(cls) -> None:
                raise RuntimeError("class setup exploded")

            def runTest(self) -> None:
                raise AssertionError("body ran after failed class setup")

        case = Case()
        result = run_cases(case)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.testsRun, 0)
        self.assertEqual(len(result.records), 1)
        record = next(iter(result.records.values()))
        self.assertEqual(record["status"], "error")
        self.assertIn("setUpClass", record["test_id"])
        self.assertEqual(record["duration_seconds"], 0.0)
        self.assertEqual(record["module"], type(case).__module__)
        self.assertEqual(record["scope"], "class")
        self.assertEqual(record["phase"], "setUpClass")
        self.assertEqual(record["covered_test_ids"], [case.id()])

    def test_expected_failure_and_unexpected_success_remain_distinct(self) -> None:
        class Case(unittest.TestCase):
            @unittest.expectedFailure
            def test_expected(self) -> None:
                self.fail("known failure")

            @unittest.expectedFailure
            def test_unexpected(self) -> None:
                pass

        expected, unexpected = Case("test_expected"), Case("test_unexpected")
        result = run_cases(expected, unexpected)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.records[expected.id()]["status"], "expected_failure")
        self.assertEqual(
            result.records[unexpected.id()]["status"], "unexpected_success"
        )
        self.assertEqual(len(result.expectedFailures), 1)
        self.assertEqual(result.unexpectedSuccesses, [unexpected])

    def test_duration_includes_setup_teardown_and_cleanup(self) -> None:
        clock = [10.0]

        class Case(unittest.TestCase):
            def setUp(self) -> None:
                clock[0] += 2
                self.addCleanup(self.finish)

            def runTest(self) -> None:
                clock[0] += 3

            def tearDown(self) -> None:
                clock[0] += 5

            def finish(self) -> None:
                clock[0] += 7

        case = Case()
        with patch(
            "tools.test_selection.reporting.time.perf_counter",
            side_effect=lambda: clock[0],
        ):
            result = run_cases(case)
        self.assertEqual(result.records[case.id()]["duration_seconds"], 17.0)


class EvidenceWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_json_replacement_is_complete_and_in_same_directory(self) -> None:
        path = self.root / "nested" / "results.json"
        write_json(path, {"old": True})
        original_replace = os.replace
        replacements = []

        def inspect_replace(source: Path, target: Path) -> None:
            self.assertEqual(target, path)
            self.assertEqual(source.parent, path.parent)
            self.assertNotEqual(source, target)
            self.assertEqual(json.loads(target.read_text()), {"old": True})
            self.assertEqual(json.loads(source.read_text()), {"new": [1, 2]})
            replacements.append(source)
            original_replace(source, target)

        with patch("tools.test_selection.reporting.os.replace", side_effect=inspect_replace):
            write_json(path, {"new": [1, 2]})
        self.assertEqual(len(replacements), 1)
        self.assertEqual(json.loads(path.read_text()), {"new": [1, 2]})
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_json_failed_replace_preserves_old_document_and_cleans_temp(self) -> None:
        path = self.root / "results.json"
        write_json(path, {"old": True})
        with patch(
            "tools.test_selection.reporting.os.replace",
            side_effect=PermissionError("locked"),
        ):
            with self.assertRaisesRegex(PermissionError, "locked"):
                write_json(path, {"new": True})
        self.assertEqual(json.loads(path.read_text()), {"old": True})
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_json_serialization_failure_preserves_old_document(self) -> None:
        path = self.root / "results.json"
        write_json(path, {"old": True})
        with self.assertRaises(TypeError):
            write_json(path, {"invalid": object()})
        self.assertEqual(json.loads(path.read_text()), {"old": True})
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_csv_repeats_provenance_and_round_trips_skip_reason(self) -> None:
        path = self.root / "nested" / "timings.csv"
        metadata = {
            "schema_version": 1,
            "run_id": "run-unique",
            "commit_sha": "a" * 40,
            "source_fingerprint": "b" * 64,
            "utc_timestamp": "2026-09-12T05:00:00+00:00",
            "python": "3.13.7",
            "tool_versions": json.dumps({"coverage": "7.10.7"}),
            "fixture_profile": "portable",
            "total_run_seconds": 8.25,
        }
        records = [
            {
                "test_id": "tests.unit.core.vision.test_capture.Case.test_ok",
                "module": "tests.unit.core.vision.test_capture",
                "covered_test_ids": ["tests.unit.core.vision.test_capture.Case.test_ok"],
                "status": "passed", "skip_reason": "", "duration_seconds": 0.25,
            },
            {
                "test_id": "tests.integration.app.test_runner.Case.test_skip",
                "module": "tests.integration.app.test_runner",
                "covered_test_ids": ["tests.integration.app.test_runner.Case.test_skip"],
                "status": "skipped", "skip_reason": 'missing, "fixture"\nportable only',
                "duration_seconds": 0.0,
            },
        ]
        write_timings(path, records, metadata)
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)
        for row, record in zip(rows, records, strict=True):
            for key, value in metadata.items():
                self.assertEqual(row[key], str(value), key)
            for key, value in record.items():
                if key == "covered_test_ids":
                    self.assertEqual(json.loads(row[key]), value)
                else:
                    self.assertEqual(row[key], str(value), key)
        self.assertEqual(rows[0]["tier"], "unit")
        self.assertEqual(rows[0]["component"], "core.vision")
        self.assertEqual(rows[1]["tier"], "integration")
        self.assertEqual(rows[1]["component"], "app")
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_csv_failed_replace_preserves_previous_bytes(self) -> None:
        path = self.root / "timings.csv"
        write_timings(path, [], {})
        previous = path.read_bytes()
        with patch(
            "tools.test_selection.reporting.os.replace",
            side_effect=PermissionError("locked"),
        ):
            with self.assertRaisesRegex(PermissionError, "locked"):
                write_timings(path, [], {"run_id": "new"})
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_csv_fixture_uses_explicit_module_for_tier_and_component(self) -> None:
        class Case(unittest.TestCase):
            @classmethod
            def setUpClass(cls) -> None:
                raise RuntimeError("fixture error")

            def runTest(self) -> None:
                self.fail("fixture prevents body")

        case = Case()
        result = run_cases(case)
        path = self.root / "fixture.csv"
        write_timings(path, list(result.records.values()), {})
        with path.open(newline="", encoding="utf-8") as stream:
            row, = csv.DictReader(stream)
        self.assertEqual(row["module"], Case.__module__)
        self.assertEqual(row["scope"], "class")
        self.assertEqual(row["phase"], "setUpClass")
        self.assertEqual(row["tier"], "unit")
        self.assertEqual(row["component"], "test_harness")
        self.assertEqual(json.loads(row["covered_test_ids"]), [case.id()])
