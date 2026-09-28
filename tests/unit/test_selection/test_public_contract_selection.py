"""Declaration changes retain scoped static consumers even without coverage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.test_selection.contexts import add_contexts, fingerprint
from tools.test_selection.models import COVERAGE_SELECTED_TIERS, POLICY_VERSION, inventory
from tools.test_selection.ownership import OwnershipRules, ResourceRule
from tools.test_selection.planner import affected_plan
from tools.test_selection.reporting import environment, write_json


MODEL = "pnc_automation/app/pnc/domain/record.py"
SERVICE = "pnc_automation/app/automation/engine/consumer.py"
HELPER = "tools/record_helper.py"


class PublicContractSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tests = inventory([
            "tests/unit/app/pnc/domain/test_record.py",
            "tests/unit/app/automation/engine/test_consumer.py",
            "tests/unit/app/automation/engine/test_sibling.py",
            "tests/unit/core/vision/test_other.py",
            "tests/contract/entrypoints/test_api.py",
            "tests/contract/other/test_unrelated.py",
            "tests/integration/workflows/test_consumer.py",
            "tests/architecture/test_layers.py",
        ])
        self.rules = OwnershipRules((), (), ())
        self.sources = {test.path: "pass\n" for test in self.tests}
        self.sources.update({
            MODEL: "class Record:\n    value: int = 1\n",
            SERVICE: "from pnc_automation.app.pnc.domain.record import Record\n",
            HELPER: "from pnc_automation.app.automation.engine.consumer import consume\n",
            "pnc_automation/core/vision/other.py": "pass\n",
            "tests/unit/app/pnc/domain/test_record.py": "from pnc_automation.app.pnc.domain.record import Record\n",
            "tests/unit/app/automation/engine/test_consumer.py": "import tools.record_helper\n",
            "tests/contract/entrypoints/test_api.py": "import tools.record_helper\n",
            "tests/integration/workflows/test_consumer.py": "import tools.record_helper\n",
            "tests/unit/core/vision/test_other.py": "import pnc_automation.core.vision.other\n",
            "tests/contract/other/test_unrelated.py": "import pnc_automation.core.vision.other\n",
        })
        self.expected = {
            test.module for test in self.tests
            if test.path not in {
                "tests/unit/core/vision/test_other.py",
                "tests/contract/other/test_unrelated.py",
            }
        }

    def test_declaration_forms_select_downstream_suites_without_unrelated_tests(self) -> None:
        declarations = (
            ("RecordLike = int\n", "RecordLike = str\n"),
            ("__all__ = ('Record',)\n", "__all__ = ('Record', 'Other')\n"),
            ("LEFT, RIGHT = 1, 2\n", "LEFT, RIGHT = 1, 3\n"),
            ("class Record:\n    value = 1\n", "class Record:\n    value = 2\n"),
            ("class Record(metaclass=A): pass\n", "class Record(metaclass=B): pass\n"),
            ("class Record[T]: pass\n", "class Record[T: int]: pass\n"),
            ("def run[T](value: T): pass\n", "def run[T: int](value: T): pass\n"),
            ("type Record[T] = list[T]\n", "type Record[T] = tuple[T, ...]\n"),
            ("from collections import Counter as Record\n", "from collections import deque as Record\n"),
            (
                "from dataclasses import dataclass, field\n@dataclass\nclass Record:\n    value: int = field(default=1)\n",
                "from dataclasses import dataclass, field\n@dataclass\nclass Record:\n    value: int = field(default=2)\n",
            ),
        )
        for before, after in declarations:
            with self.subTest(before=before):
                old = {**self.sources, MODEL: before}
                new = {**old, MODEL: after}
                for tiers in (frozenset(), COVERAGE_SELECTED_TIERS):
                    with self.subTest(coverage_tiers=tiers):
                        plan = affected_plan(
                            self.tests, self.rules, [MODEL], old, new, "base", "head",
                            coverage_selected_tiers=tiers,
                        )
                        self.assertFalse(plan.fallbacks)
                        self.assertEqual(set(plan.reasons), self.expected)

    def test_removed_intermediary_import_keeps_unchanged_consumers_and_their_suites(self) -> None:
        new = {**self.sources, MODEL: "class Record:\n    value: str = 'changed'\n", SERVICE: "pass\n"}
        plan = affected_plan(self.tests, self.rules, [MODEL, SERVICE], self.sources, new, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertEqual(set(plan.reasons), self.expected)

    def test_zero_observed_owners_cannot_remove_static_high_level_consumers(self) -> None:
        new = {**self.sources, MODEL: "class Record:\n    value: str = 'changed'\n"}
        with tempfile.TemporaryDirectory() as directory:
            seed_path = Path(directory) / "contexts.json"
            seed = {
                "version": POLICY_VERSION, "head": "base", "fingerprint": fingerprint(self.sources),
                "environment": environment(), "inventory": sorted(test.module for test in self.tests),
                "owners": {MODEL: []},
            }
            for observed in ([], ["tests.contract.other.test_unrelated"]):
                with self.subTest(observed=observed):
                    write_json(seed_path, {**seed, "owners": {MODEL: observed}})
                    plan = affected_plan(
                        self.tests, self.rules, [MODEL], self.sources, new, "base", "head",
                        coverage_selected_tiers=COVERAGE_SELECTED_TIERS,
                    )
                    add_contexts(plan, seed_path, self.sources, self.tests, tiers=COVERAGE_SELECTED_TIERS)
                    self.assertFalse(plan.fallbacks)
                    self.assertEqual(set(plan.reasons), self.expected | set(observed))

    def test_prior_policy_seed_still_requires_full_inventory(self) -> None:
        new = {**self.sources, MODEL: "class Record:\n    value: str = 'changed'\n"}
        with tempfile.TemporaryDirectory() as directory:
            seed_path = Path(directory) / "contexts.json"
            write_json(seed_path, {
                "version": POLICY_VERSION - 1, "head": "base", "fingerprint": fingerprint(self.sources),
                "environment": environment(), "inventory": sorted(test.module for test in self.tests),
                "owners": {},
            })
            plan = affected_plan(
                self.tests, self.rules, [MODEL], self.sources, new, "base", "head",
                coverage_selected_tiers=COVERAGE_SELECTED_TIERS,
            )
            add_contexts(plan, seed_path, self.sources, self.tests, tiers=COVERAGE_SELECTED_TIERS)
            self.assertTrue(plan.fallbacks)
            self.assertEqual(set(plan.reasons), {test.module for test in self.tests})

    def test_unmapped_contract_remains_a_guard_until_its_owner_is_established(self) -> None:
        unknown = "tests/contract/global/test_source_data.py"
        tests = inventory([test.path for test in self.tests] + [unknown])
        old = {**self.sources, unknown: "pass\n", MODEL: "def value(): return 1\n"}
        new = {**old, MODEL: "def value(): return 2\n"}
        for tiers in (frozenset(), COVERAGE_SELECTED_TIERS):
            with self.subTest(coverage_tiers=tiers):
                plan = affected_plan(
                    tests, self.rules, [MODEL], old, new, "base", "head",
                    coverage_selected_tiers=tiers,
                )
                self.assertFalse(plan.fallbacks)
                self.assertIn("tests.contract.global.test_source_data", plan.reasons)
                self.assertNotIn("tests.contract.other.test_unrelated", plan.reasons)

    def test_explicit_python_owner_scopes_a_nonimport_contract_check(self) -> None:
        scanner = "tests/contract/global/test_source_data.py"
        other = "pnc_automation/core/vision/other.py"
        tests = inventory([test.path for test in self.tests] + [scanner])
        old = {**self.sources, scanner: "pass\n"}
        rules = OwnershipRules((), (), (ResourceRule(other, ("contract.global",)),))
        new = {**old, MODEL: "class Record:\n    value: str = 'changed'\n"}
        plan = affected_plan(tests, rules, [MODEL], old, new, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertNotIn("tests.contract.global.test_source_data", plan.reasons)
        new = {**old, other: "def recognize(): return None\n"}
        plan = affected_plan(tests, rules, [other], old, new, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertIn("tests.contract.global.test_source_data", plan.reasons)
        self.assertNotIn("tests.contract.entrypoints.test_api", plan.reasons)
