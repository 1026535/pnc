"""Inventory and explainable-plan contracts using paths, never imported tests."""

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tools.test_selection.models import SelectionPlan, inventory, module_name


class InventoryTests(unittest.TestCase):
    def test_suite_discovery_never_imports_application_or_changes_environment(self) -> None:
        source = textwrap.dedent("""
            import importlib.abc
            import os
            import sys
            import tempfile
            import unittest

            class RejectApplicationImports(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == 'pnc_automation' or fullname.startswith('pnc_automation.'):
                        raise AssertionError('Offline discovery imported ' + fullname)

            sys.meta_path.insert(0, RejectApplicationImports())
            before_environment = dict(os.environ)
            temporary_directory = tempfile.TemporaryDirectory
            suite = unittest.defaultTestLoader.discover('tests/unit/test_selection')
            assert not unittest.defaultTestLoader.errors, unittest.defaultTestLoader.errors
            assert suite.countTestCases() >= 30
            assert dict(os.environ) == before_environment
            assert tempfile.TemporaryDirectory is temporary_directory
            assert not any(name == 'pnc_automation' or name.startswith('pnc_automation.')
                           for name in sys.modules)
        """)
        result = subprocess.run(
            [sys.executable, "-c", source],
            cwd=Path(__file__).resolve().parents[3],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_portable_tiers_and_nested_components(self) -> None:
        paths = [
            "tests/unit/core/vision/test_matcher.py",
            "tests/contract/entrypoints/test_api.py",
            "tests/integration/vision/test_ocr.py",
            "tests/architecture/test_boundaries.py",
        ]
        tests = inventory(paths)
        self.assertEqual([t.path for t in tests], sorted(paths))
        self.assertEqual(
            {(t.tier, t.component) for t in tests},
            {("unit", "core.vision"), ("contract", "entrypoints"),
             ("integration", "vision"), ("architecture", "")},
        )
        self.assertEqual(tests[-1].module, "tests.unit.core.vision.test_matcher")

    def test_live_support_data_legacy_and_non_tests_are_ineligible(self) -> None:
        paths = [
            "tests/live/test_account.py", "tests/support/test_fake.py",
            "tests/data/test_example.py", "tests/test_legacy.py",
            "tools/test_runner.py", "tests/unit/core/helper.py",
            "tests/unit/core/__init__.py", "tests/unit/core/test_image.png",
            "tests/unit/core/test_cached.pyc", "tests/units/test_typo.py",
        ]
        self.assertEqual(inventory(paths), ())

    def test_inventory_does_not_need_files_to_exist(self) -> None:
        self.assertEqual(
            inventory(["tests/unit/nonexistent/test_explodes_on_import.py"])[0].module,
            "tests.unit.nonexistent.test_explodes_on_import",
        )

    def test_sorting_is_independent_of_input_order(self) -> None:
        paths = ["tests/unit/z/test_z.py", "tests/unit/a/test_a.py"]
        self.assertEqual(inventory(paths), inventory(list(reversed(paths))))

    def test_empty_inventory(self) -> None:
        self.assertEqual(inventory([]), ())

    def test_tier_root_test_has_empty_component(self) -> None:
        self.assertEqual(inventory(["tests/architecture/test_rules.py"])[0].component, "")

    def test_module_names_treat_package_init_as_package(self) -> None:
        for path, expected in [
            ("pnc_automation/__init__.py", "pnc_automation"),
            ("pnc_automation/core/vision/__init__.py", "pnc_automation.core.vision"),
            ("pnc_automation/core/vision/image.py", "pnc_automation.core.vision.image"),
        ]:
            with self.subTest(path=path):
                self.assertEqual(module_name(path), expected)


class SelectionPlanTests(unittest.TestCase):
    def test_reasons_are_additive_deduplicated_and_sorted_in_document(self) -> None:
        plan = SelectionPlan("affected", "base-sha", "head-sha", ["b.py", "a.py"])
        plan.add("tests.unit.z.test_z", "z reason")
        plan.add("tests.unit.a.test_a", "first")
        plan.add("tests.unit.z.test_z", "a reason")
        plan.add("tests.unit.z.test_z", "z reason")
        document = plan.document()
        self.assertEqual(list(document["reasons"]), ["tests.unit.a.test_a", "tests.unit.z.test_z"])
        self.assertEqual(document["reasons"]["tests.unit.z.test_z"], ["a reason", "z reason"])
        self.assertEqual(document["base"], "base-sha")
        self.assertEqual(document["head"], "head-sha")
        self.assertEqual(document["changed_paths"], ["b.py", "a.py"])

    def test_full_keeps_existing_specific_reasons(self) -> None:
        tests = inventory(["tests/unit/a/test_a.py", "tests/unit/b/test_b.py"])
        plan = SelectionPlan("affected", "base", "head")
        plan.add(tests[0].module, "direct import")
        plan.full(tests, "unknown dependency")
        self.assertEqual(set(plan.reasons), {t.module for t in tests})
        self.assertEqual(plan.reasons[tests[0].module], ["direct import", "unknown dependency"])
        self.assertEqual(plan.fallbacks, ["unknown dependency"])

    def test_document_cannot_mutate_live_plan(self) -> None:
        plan = SelectionPlan("affected", "base", "head", ["a.py"])
        plan.add("test_a", "reason")
        document = plan.document()
        document["changed_paths"].append("other.py")
        document["reasons"]["test_a"].append("other reason")
        self.assertEqual(plan.changed_paths, ["a.py"])
        self.assertEqual(plan.reasons, {"test_a": ["reason"]})
