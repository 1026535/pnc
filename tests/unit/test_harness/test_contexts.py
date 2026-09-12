"""Fail-closed context selection and unittest fixture attribution regressions."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.test_selection.contexts import add_contexts, fingerprint, seed_contexts
from tools.test_selection.models import POLICY_VERSION, SelectionPlan, inventory
from tools.test_selection.reporting import write_json
from tests.unit.test_harness.test_reporting import run_cases


class ContextLifecycleTests(unittest.TestCase):
    def test_context_covers_setup_body_teardown_cleanup_and_resets_for_class_fixtures(self) -> None:
        active = [""]
        events = []

        def switch(context: str) -> None:
            active[0] = context

        coverage = Mock()
        coverage.switch_context.side_effect = switch

        class Case(unittest.TestCase):
            @classmethod
            def setUpClass(cls) -> None:
                events.append(("class setup", active[0]))

            def setUp(self) -> None:
                events.append(("setup", active[0]))
                self.addCleanup(lambda: events.append(("cleanup", active[0])))

            def runTest(self) -> None:
                events.append(("body", active[0]))

            def tearDown(self) -> None:
                events.append(("teardown", active[0]))

            @classmethod
            def tearDownClass(cls) -> None:
                events.append(("class teardown", active[0]))

        class NextCase(Case):
            pass

        first, second = Case(), NextCase()
        result = run_cases(first, second, coverage=coverage)
        self.assertTrue(result.wasSuccessful())
        expected = []
        for case in (first, second):
            expected.extend([
                ("class setup", ""),
                *[(phase, case.id()) for phase in ("setup", "body", "teardown", "cleanup")],
                ("class teardown", ""),
            ])
        self.assertEqual(events, expected)
        self.assertEqual(active[0], "")
        self.assertEqual(
            [call.args[0] for call in coverage.switch_context.call_args_list],
            [first.id(), "", second.id(), ""],
        )

    def test_context_resets_after_setup_error_and_setup_skip(self) -> None:
        for error in (RuntimeError("broken setup"), unittest.SkipTest("missing fixture")):
            with self.subTest(error=type(error).__name__):
                active = [""]
                observed = []
                coverage = Mock()
                coverage.switch_context.side_effect = lambda context: active.__setitem__(0, context)

                class Case(unittest.TestCase):
                    def setUp(self) -> None:
                        observed.append(active[0])
                        raise error

                    def runTest(self) -> None:
                        raise AssertionError("body must not run")

                case = Case()
                result = run_cases(case, coverage=coverage)
                self.assertEqual(observed, [case.id()])
                self.assertEqual(active[0], "")
                self.assertEqual(result.started, {})
                expected = "skipped" if isinstance(error, unittest.SkipTest) else "error"
                self.assertEqual(result.records[case.id()]["status"], expected)


class ContextSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "contexts.json"
        self.tests = inventory([
            "tests/unit/alpha/test_alpha.py",
            "tests/unit/beta/test_beta.py",
            "tests/contract/api/test_api.py",
            "tests/architecture/test_layers.py",
        ])
        self.known = {test.module for test in self.tests}
        self.sources = {"pnc_automation/alpha.py": "value = 1\n"}
        self.env = {
            "python": "3.13.7", "platform": "Windows-test",
            "packages": {"coverage": "7.10.7"},
        }
        environment_patch = patch(
            "tools.test_selection.contexts.environment", return_value=self.env
        )
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        self.seed = {
            "version": POLICY_VERSION, "head": "base-sha",
            "fingerprint": fingerprint(self.sources), "environment": self.env,
            "inventory": sorted(self.known),
            "owners": {"pnc_automation/alpha.py": ["tests.unit.beta.test_beta"]},
        }

    def plan(self) -> SelectionPlan:
        plan = SelectionPlan(
            "affected", "base-sha", "candidate-sha", ["pnc_automation/alpha.py"]
        )
        plan.add("tests.unit.alpha.test_alpha", "static dependency")
        return plan

    def assert_full_fallback(self) -> None:
        plan = self.plan()
        add_contexts(plan, self.path, self.sources, self.tests)
        self.assertEqual(set(plan.reasons), self.known)
        self.assertTrue(plan.fallbacks)
        self.assertIn("static dependency", plan.reasons["tests.unit.alpha.test_alpha"])

    def test_missing_seed_runs_full(self) -> None:
        self.assert_full_fallback()
        self.assertFalse(self.path.exists())

    def test_corrupt_json_and_non_utf8_seed_run_full(self) -> None:
        for contents in (b'{"version":', b'\xff\xfe'):
            with self.subTest(contents=contents):
                self.path.write_bytes(contents)
                self.assert_full_fallback()

    def test_stale_base_fingerprint_policy_or_inventory_runs_full(self) -> None:
        for key, value in (
            ("head", "wrong-base"), ("fingerprint", "stale-source"),
            ("version", POLICY_VERSION + 1), ("inventory", []),
        ):
            with self.subTest(key=key):
                seed = {**self.seed, key: value}
                write_json(self.path, seed)
                self.assert_full_fallback()

    def test_environment_python_platform_or_dependency_mismatch_runs_full(self) -> None:
        for key, value in (
            ("python", "3.14.0"), ("platform", "Linux-test"),
            ("packages", {"coverage": "7.10.8"}),
        ):
            with self.subTest(key=key):
                seed = copy.deepcopy(self.seed)
                seed["environment"][key] = value
                write_json(self.path, seed)
                self.assert_full_fallback()

    def test_malformed_structure_or_unknown_owner_runs_full(self) -> None:
        for owners in (
            [], {"source.py": "not a list"},
            {"source.py": ["tests.unknown"]}, {"source.py": [[]]},
        ):
            with self.subTest(owners=owners):
                write_json(self.path, {**self.seed, "owners": owners})
                self.assert_full_fallback()
        for seed in ({}, {**self.seed, "unexpected": True}):
            with self.subTest(keys=tuple(seed)):
                write_json(self.path, seed)
                self.assert_full_fallback()

    def test_non_object_json_roots_run_full(self) -> None:
        for root in (None, True, 1, "seed", [], [{"version": 1}]):
            with self.subTest(root=root):
                self.path.write_text(json.dumps(root), encoding="utf-8")
                self.assert_full_fallback()

    def test_observed_owners_are_additive_to_static_and_mandatory_guards(self) -> None:
        write_json(self.path, self.seed)
        plan = self.plan()
        for test in self.tests:
            if test.tier in {"contract", "architecture"}:
                plan.add(test.module, "mandatory guard")
        previous = copy.deepcopy(plan.reasons)
        add_contexts(plan, self.path, self.sources, self.tests)
        self.assertEqual(set(plan.reasons), self.known)
        self.assertEqual(plan.fallbacks, [])
        for module, reasons in previous.items():
            self.assertEqual(plan.reasons[module], reasons)
        self.assertEqual(plan.reasons["tests.unit.beta.test_beta"], [
            "observed execution dependency: pnc_automation/alpha.py"
        ])
        add_contexts(plan, self.path, self.sources, self.tests)
        self.assertEqual(len(plan.reasons["tests.unit.beta.test_beta"]), 1)

    def test_unobserved_change_does_not_remove_static_selection(self) -> None:
        write_json(self.path, self.seed)
        plan = self.plan()
        plan.changed_paths = ["pnc_automation/unobserved.py"]
        previous = copy.deepcopy(plan.reasons)
        add_contexts(plan, self.path, self.sources, self.tests)
        self.assertEqual(plan.reasons, previous)
        self.assertEqual(plan.fallbacks, [])

    def test_seed_round_trip_attributes_shared_fixtures_to_all_modules(self) -> None:
        shared = str(self.root / "pnc_automation" / "shared.py")
        specific = str(self.root / "pnc_automation" / "alpha.py")
        outside = str(self.root.parent / "external_dependency.py")
        data = Mock()
        data.measured_files.return_value = [shared, specific, outside]
        data.contexts_by_lineno.side_effect = lambda filename: {
            shared: {1: [""], 2: ["tests.unit.alpha.test_alpha.Case.test_ok"]},
            specific: {3: ["tests.unit.beta.test_beta.Case.test_ok"]},
        }[filename]
        coverage = Mock()
        coverage.get_data.return_value = data
        seed_contexts(self.path, coverage, self.root, self.sources, self.tests, "base-sha")
        plan = self.plan()
        add_contexts(plan, self.path, self.sources, self.tests)
        self.assertEqual(set(plan.reasons), {
            "tests.unit.alpha.test_alpha", "tests.unit.beta.test_beta"
        })
        self.assertEqual(plan.fallbacks, [])
        plan.changed_paths = ["pnc_automation/shared.py"]
        add_contexts(plan, self.path, self.sources, self.tests)
        self.assertEqual(set(plan.reasons), self.known)
        self.assertEqual(plan.fallbacks, [])
        self.assertEqual(data.contexts_by_lineno.call_count, 2)

    def test_fingerprint_is_order_independent_and_changes_with_content(self) -> None:
        self.assertEqual(fingerprint({"a": "1", "b": "2"}), fingerprint({"b": "2", "a": "1"}))
        self.assertNotEqual(fingerprint({"a": "1"}), fingerprint({"a": "2"}))
