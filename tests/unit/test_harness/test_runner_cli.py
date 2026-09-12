"""Runner CLI regressions using a temporary candidate and mocked Git/discovery."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from tools import run_tests


class RunnerCliTests(unittest.TestCase):
    """Exercise real selection, reporting, and synthetic unittest execution."""

    def setUp(self) -> None:
        previous_cwd = Path.cwd()
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.addCleanup(os.chdir, previous_cwd)
        self.enterContext(patch.dict(os.environ))
        self.enterContext(patch.object(run_tests, "ROOT", self.root))
        self.sources = {
            "tests/unit/sample/test_available.py": "raise AssertionError('must not import candidate tests')\n",
            "pnc_automation/sample.py": "VALUE = 1\n",
        }
        self.files = {
            **self.sources,
            "README.md": "Candidate documentation\n",
            "assets/anchor.png": "first resource contents",
            "tests/selection_rules.yaml": (
                "version: 1\nfull: []\ndocumentation: ['*.md']\nresources: []\n"
            ),
        }
        for relative, contents in self.files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        self.enterContext(patch.object(run_tests, "resolve", return_value="a" * 40))
        self.enterContext(patch.object(run_tests, "working_paths", return_value=list(self.files)))
        self.enterContext(patch.object(run_tests, "python_snapshot", return_value=self.sources))
        self.base = self.enterContext(patch.object(run_tests, "base_revision", return_value="b" * 40))
        self.enterContext(patch.object(run_tests, "changed_paths", return_value=["README.md"]))
        self.enterContext(patch.object(
            run_tests, "environment", return_value={"python": "offline", "packages": {}}
        ))
        self.executed: list[str] = []
        self.flag_snapshots: list[tuple[list[str], str | None]] = []
        self.loader_factory = self.enterContext(patch.object(run_tests.unittest, "TestLoader"))
        self.loader = self.loader_factory.return_value
        self.loader.loadTestsFromName.side_effect = self.available_suite
        self.output = io.StringIO()
        self.errors = io.StringIO()

    def available_suite(self, module: str) -> unittest.TestSuite:
        """Provide a real case with the selected module identity, without imports."""
        executed = self.executed
        flag_snapshots = self.flag_snapshots

        def test_available(case: unittest.TestCase) -> None:
            executed.append(module)
            flag_snapshots.append((
                sorted(key for key in os.environ if key.startswith("PNC_RUN_LIVE")),
                os.environ.get("PNC_TEST_FIXTURE_PROFILE"),
            ))

        case_type = type("AvailableCase", (unittest.TestCase,), {
            "__module__": module, "test_available": test_available,
        })
        return unittest.TestSuite([case_type("test_available")])

    def invoke(self, *arguments: str) -> int:
        with redirect_stdout(self.output), redirect_stderr(self.errors):
            return run_tests.main(list(arguments))

    def document(self, filename: str) -> dict:
        return json.loads((self.root / ".test-impact" / filename).read_text(encoding="utf-8"))

    def assert_available_suite_ran(self) -> dict:
        module = "tests.unit.sample.test_available"
        test_id = module + ".AvailableCase.test_available"
        self.loader.loadTestsFromName.assert_called_once_with(module)
        self.assertEqual(self.executed, [module])
        report = self.document("results.json")
        self.assertTrue(report["succeeded"])
        self.assertEqual(report["inventory_modules"], [module])
        self.assertEqual(report["discovered_test_ids"], [test_id])
        self.assertEqual(report["discovered_tests"], [{
            "test_id": test_id, "module": module, "class_id": module + ".AvailableCase",
        }])
        self.assertEqual(report["tests"][0]["status"], "passed")
        return report

    def test_invalid_group_returns_two_without_loading_tests(self) -> None:
        self.assertEqual(self.invoke("group", "invalidgroup2"), 2)
        self.assertIn("Unknown or empty group: invalidgroup2", self.errors.getvalue())
        self.loader_factory.assert_not_called()
        self.assertEqual(self.executed, [])

    def test_documentation_dry_run_never_loads_or_executes_tests(self) -> None:
        self.assertEqual(self.invoke("affected", "--base", "base", "--dry-run"), 0)
        self.loader_factory.assert_not_called()
        self.assertEqual(self.executed, [])
        plan = self.document("selection.json")
        self.assertEqual(plan["reasons"], {})
        self.assertEqual(plan["fallbacks"], [])
        self.assertEqual(plan["changed_paths"], ["README.md"])
        self.assertFalse((self.root / ".test-impact/results.json").exists())

    def test_missing_base_falls_back_and_executes_available_suite(self) -> None:
        self.base.side_effect = ValueError("missing requested base")
        self.assertEqual(self.invoke("affected", "--base", "missingbase"), 0)
        report = self.assert_available_suite_ran()
        self.assertIn("missing requested base", report["selection"]["fallbacks"][0])

    def test_malformed_yaml_falls_back_and_executes_available_suite(self) -> None:
        (self.root / "tests/selection_rules.yaml").write_text("full: [unterminated", encoding="utf-8")
        self.assertEqual(self.invoke("affected", "--base", "base"), 0)
        report = self.assert_available_suite_ran()
        self.assertIn("selection analysis unavailable", report["selection"]["fallbacks"][0])

    def test_inherited_live_flags_are_neutralized_before_execution(self) -> None:
        os.environ.update({
            "PNC_RUN_LIVE_SMOKE": "1", "PNC_RUN_LIVE_CHAT_SMOKE": "1",
            "PNC_RUN_LIVE_FUTURE_FLAG": "1", "PNC_TEST_FIXTURE_PROFILE": "local",
        })
        self.assertEqual(self.invoke("full"), 0)
        self.assert_available_suite_ran()
        self.assertEqual(self.flag_snapshots, [([], "portable")])

    def test_candidate_fingerprint_changes_for_non_python_resource_edit(self) -> None:
        self.assertEqual(self.invoke("full", "--dry-run"), 0)
        before = self.document("selection.json")
        (self.root / "assets/anchor.png").write_bytes(b"changed resource contents")
        self.assertEqual(self.invoke("full", "--dry-run"), 0)
        after = self.document("selection.json")
        self.assertNotEqual(before["source_fingerprint"], after["source_fingerprint"])
        self.assertEqual(before["head"], after["head"])
        self.assertEqual(before["inventory_modules"], after["inventory_modules"])
        self.loader_factory.assert_not_called()

    def test_interrupted_measure_removes_previous_context_seed(self) -> None:
        seed = self.root / ".test-impact/contexts.json"
        seed.parent.mkdir()
        seed.write_text('{"previous": "seed"}', encoding="utf-8")
        coverage_module = ModuleType("coverage")
        coverage_factory = Mock()
        coverage_module.Coverage = coverage_factory
        self.loader.loadTestsFromName.side_effect = KeyboardInterrupt
        with (
            patch.dict(sys.modules, {"coverage": coverage_module}),
            patch.object(run_tests, "seed_contexts") as publish_seed,
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.invoke("measure")
        coverage_factory.return_value.start.assert_called_once_with()
        self.assertFalse(seed.exists())
        publish_seed.assert_not_called()
        self.assertEqual(self.executed, [])


if __name__ == "__main__":
    unittest.main()
