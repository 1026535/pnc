"""Seeded faults prove why source scanners and resources need non-import owners."""

import ast
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

from tools.test_selection.models import inventory, module_name
from tools.test_selection.ownership import OwnershipRules, ResourceRule
from tools.test_selection.planner import affected_plan
from tools.test_selection.python_graph import build_graph


class FaultRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="selection-fault-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def execute(self, checks: dict[str, Callable[[], None]], selected: set[str]) -> unittest.TestResult:
        suite = unittest.TestSuite(unittest.FunctionTestCase(checks[name]) for name in sorted(selected))
        result = unittest.TestResult()
        suite.run(result)
        return result

    def test_source_scanning_fault_missed_by_imports_is_caught_by_mandatory_architecture(self) -> None:
        path = "pnc_automation/core/engine.py"
        source_file = self.root / "engine.py"
        test_path = "tests/unit/core/test_engine.py"
        scanner_path = "tests/architecture/test_source_boundary.py"
        tests = inventory([test_path, scanner_path])
        old = {path: "def run():\n    return 1\n", test_path: "import pnc_automation.core.engine\n",
               scanner_path: "import ast\nfrom pathlib import Path\n"}
        new = {**old, path: "from pnc_automation.app import runtime\n" + old[path]}

        def source_boundary() -> None:
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            forbidden = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                         and node.module and node.module.startswith("pnc_automation.app")]
            self.assertEqual(forbidden, [], "core cannot consume app runtime")

        checks = {module_name(test_path): lambda: None, module_name(scanner_path): source_boundary}
        source_file.write_text(old[path], encoding="utf-8")
        self.assertTrue(self.execute(checks, set(checks)).wasSuccessful())
        source_file.write_text(new[path], encoding="utf-8")
        import_only = build_graph(old, new).consumers({module_name(path)}) & set(checks)
        self.assertNotIn(module_name(scanner_path), import_only)
        self.assertTrue(self.execute(checks, import_only).wasSuccessful(), "Import-only baseline must demonstrate the false green")
        full = self.execute(checks, set(checks))
        self.assertEqual(len(full.failures), 1)
        plan = affected_plan(tests, OwnershipRules((), (), ()), [path], old, new, "base", "head")
        selected = self.execute(checks, set(plan.reasons))
        self.assertEqual(len(selected.failures), 1)
        self.assertFalse(selected.errors)
        self.assertFalse(plan.fallbacks, "Mandatory source checks should suffice for this private implementation edit")

    def test_static_resource_fault_missed_by_imports_is_caught_by_explicit_owner(self) -> None:
        path = "assets/anchors/catalog.json"
        resource = self.root / "catalog.json"
        vision_path = "tests/unit/core/vision/test_catalog.py"
        unrelated_path = "tests/unit/engine/test_worker.py"
        tests = inventory([vision_path, unrelated_path])
        snapshot = {vision_path: "from pathlib import Path\n", unrelated_path: "pass\n"}

        def catalog_contract() -> None:
            self.assertEqual(resource.read_text(encoding="utf-8"), '{"home": [12, 34]}')

        checks = {module_name(vision_path): catalog_contract, module_name(unrelated_path): lambda: None}
        resource.write_text('{"home": [12, 34]}', encoding="utf-8")
        self.assertTrue(self.execute(checks, set(checks)).wasSuccessful())
        resource.write_text('{"home": null}', encoding="utf-8")
        import_only = build_graph(snapshot).consumers({path}) & set(checks)
        self.assertEqual(import_only, set())
        self.assertTrue(self.execute(checks, import_only).wasSuccessful())
        self.assertEqual(len(self.execute(checks, set(checks)).failures), 1)
        rules = OwnershipRules((), (), (ResourceRule("assets/anchors/*.json", ("vision",)),))
        plan = affected_plan(tests, rules, [path], snapshot, snapshot, "base", "head")
        self.assertEqual(set(plan.reasons), {module_name(vision_path)})
        self.assertEqual(len(self.execute(checks, set(plan.reasons)).failures), 1)
        self.assertFalse(plan.fallbacks)

    def test_unknown_static_resource_falls_back_and_catches_seeded_failure(self) -> None:
        path = "new-assets/button.png"
        resource = self.root / "button.png"
        vision_path = "tests/unit/core/vision/test_button.py"
        tests = inventory([vision_path, "tests/unit/engine/test_worker.py"])
        snapshot = {test.path: "pass\n" for test in tests}
        resource.write_bytes(b"corrupt image")

        def image_contract() -> None:
            self.assertTrue(resource.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

        checks = {test.module: image_contract if test.path == vision_path else lambda: None for test in tests}
        plan = affected_plan(tests, OwnershipRules((), (), ()), [path], snapshot, snapshot, "base", "head")
        self.assertEqual(set(plan.reasons), set(checks))
        self.assertTrue(plan.fallbacks)
        self.assertEqual(len(self.execute(checks, set(plan.reasons)).failures), 1)
