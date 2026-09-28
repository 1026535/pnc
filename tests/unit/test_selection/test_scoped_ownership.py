"""Configured rules retain contract safety and narrow feature helpers."""

from pathlib import Path
import unittest

from tools.test_selection.models import inventory
from tools.test_selection.ownership import load_rules
from tools.test_selection.planner import affected_plan

ROOT = Path(__file__).resolve().parents[3]


class ScopedOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tests = inventory([
            "tests/unit/app/pnc/domain/test_sample.py",
            "tests/unit/app/pnc/vision/test_sample.py",
            "tests/integration/sample/test_capture.py",
            "tests/contract/sample/test_api.py",
            "tests/architecture/test_imports.py",
        ])
        self.rules = load_rules(ROOT / "tests/selection_rules.yaml", self.tests)
        self.sources = {test.path: "pass\n" for test in self.tests}
        self.helper = "tests/support/pnc/capture_vision/feature.py"
        self.domain = "pnc_automation/app/pnc/domain/sample.py"
        self.sources.update({
            self.helper: "def make_frame():\n    return 1\n",
            self.domain: "def value():\n    return 1\n",
            "tests/unit/app/pnc/vision/test_sample.py": "from tests.support.pnc.capture_vision.feature import make_frame\n",
            "tests/unit/app/pnc/domain/test_sample.py": "from pnc_automation.app.pnc.domain.sample import value\n",
        })

    def test_scoped_helper_selects_consumers_and_mandatory_contracts(self) -> None:
        plan = affected_plan(self.tests, self.rules, [self.helper], self.sources, self.sources, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertEqual(set(plan.reasons), {
            "tests.unit.app.pnc.vision.test_sample",
            "tests.contract.sample.test_api", "tests.architecture.test_imports",
        })

    def test_domain_body_edit_does_not_select_unrelated_vision(self) -> None:
        updated = {**self.sources, self.domain: "def value():\n    return 2\n"}
        plan = affected_plan(self.tests, self.rules, [self.domain], self.sources, updated, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertNotIn("tests.unit.app.pnc.vision.test_sample", plan.reasons)
        self.assertIn("tests.unit.app.pnc.domain.test_sample", plan.reasons)

    def test_public_domain_signature_change_still_requires_full_inventory(self) -> None:
        updated = {**self.sources, self.domain: "def value(arg):\n    return arg\n"}
        plan = affected_plan(self.tests, self.rules, [self.domain], self.sources, updated, "base", "head")
        self.assertTrue(plan.fallbacks)
        self.assertEqual(len(plan.reasons), len(self.tests))
