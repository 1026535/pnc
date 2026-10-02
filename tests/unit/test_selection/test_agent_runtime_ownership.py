"""Explicit owners route skill scripts to their portable tests, fail closed elsewhere."""

from pathlib import Path
import unittest

from tools.test_selection.models import inventory
from tools.test_selection.ownership import group_matches, load_rules
from tools.test_selection.planner import affected_plan
from tools.test_selection.sharding import shard_modules


ROOT = Path(__file__).resolve().parents[3]
GROUP = "unit.tools.agent_runtime"
AGENT_TEST_PATHS = (
    "tests/unit/tools/agent_runtime/test_consult_game_knowledge.py",
    "tests/unit/tools/agent_runtime/test_devin_acp.py",
    "tests/unit/tools/agent_runtime/test_devin_monitor.py",
    "tests/unit/tools/agent_runtime/test_devin_worker.py",
    "tests/unit/tools/agent_runtime/test_import_support.py",
)
SCRIPT_OWNERS = (
    ".agents/skills/devin-implement/scripts/devin_worker.py",
    ".agents/skills/devin-implement/scripts/devin_monitor.py",
    ".agents/skills/devin-implement/scripts/devin_acp.py",
    ".agents/skills/devin-implement/scripts/windows_job.py",
    ".agents/skills/devin-game-knowledge/scripts/consult_game_knowledge.py",
)
IMPORTS_HELPER = "tests/support/agent_runtime/imports.py"
UNRELATED_PRODUCTION = "pnc_automation/app/automation/engine/action_executor.py"
UNRELATED_TEST = "tests/unit/app/automation/engine/test_action_pacing.py"


class AgentRuntimeOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        paths = [
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "tests").rglob("test_*.py")
        ]
        cls.tests = inventory(paths)
        cls.rules = load_rules(ROOT / "tests/selection_rules.yaml", cls.tests)
        cls.modules = {test.module for test in cls.tests}
        cls.agent_modules = {
            test.module for test in cls.tests if group_matches(test, GROUP)
        }
        cls.mandatory = {
            test.module for test in cls.tests
            if test.tier in {"architecture", "contract"}
        }

    def sources(self) -> dict[str, str]:
        """Build a small graph with real test paths and explicit synthetic imports."""
        result = {test.path: "pass\n" for test in self.tests}
        actual_paths = (
            *AGENT_TEST_PATHS,
            *SCRIPT_OWNERS,
            "tests/__init__.py",
            "tests/support/__init__.py",
            "tests/support/agent_runtime/__init__.py",
            IMPORTS_HELPER,
            "tests/support/agent_runtime/worker_fixture.py",
            "tests/support/paths.py",
            UNRELATED_PRODUCTION,
            UNRELATED_TEST,
        )
        result.update({path: (ROOT / path).read_text(encoding="utf-8") for path in actual_paths})
        result.update({
            "pnc_automation/__init__.py": "",
            "pnc_automation/app/__init__.py": "",
            "pnc_automation/app/automation/__init__.py": "",
            "pnc_automation/app/automation/engine/__init__.py": "",
        })
        return result

    def expected_floor(self) -> set[str]:
        return self.agent_modules | self.mandatory

    def test_exact_skill_script_edits_select_the_agent_runtime_group(self) -> None:
        old = self.sources()
        for path in SCRIPT_OWNERS:
            with self.subTest(path=path):
                new = {**old, path: "def value():\n    return 2\n"}
                plan = affected_plan(
                    self.tests, self.rules, [path], old, new, "base", "head",
                )
                self.assertEqual(set(plan.reasons), self.expected_floor())
                self.assertFalse(plan.fallbacks)
                for module in self.agent_modules:
                    self.assertIn(f"explicit resource ownership: {path}", plan.reasons[module])

    def test_shared_import_helper_selects_its_real_agent_script_consumers(self) -> None:
        old = self.sources()
        new = {**old, IMPORTS_HELPER: "from contextlib import contextmanager\n# changed\n"}
        plan = affected_plan(
            self.tests, self.rules, [IMPORTS_HELPER], old, new, "base", "head",
        )
        self.assertEqual(set(plan.reasons), self.expected_floor())
        self.assertFalse(plan.fallbacks)
        self.assertTrue(self.agent_modules <= set(plan.reasons))

    def test_directly_changed_migrated_test_runs_itself(self) -> None:
        path = "tests/unit/tools/agent_runtime/test_devin_worker.py"
        old = self.sources()
        new = {**old, path: old[path] + "# changed\n"}
        plan = affected_plan(self.tests, self.rules, [path], old, new, "base", "head")
        self.assertEqual(set(plan.reasons), self.mandatory | {path[:-3].replace("/", ".")})
        self.assertFalse(plan.fallbacks)

    def test_unknown_and_mixed_skill_edits_keep_full_fallback(self) -> None:
        known = SCRIPT_OWNERS[0]
        unknown = ".agents/skills/example/scripts/new_worker.py"
        old = self.sources()
        old[unknown] = "def value():\n    return 1\n"
        changes = (
            ([unknown], {**old, unknown: "def value():\n    return 2\n"}),
            ([known, unknown], {
                **old, known: "def value():\n    return 2\n",
                unknown: "def value():\n    return 2\n",
            }),
        )
        for changed, new in changes:
            with self.subTest(changed=changed):
                plan = affected_plan(self.tests, self.rules, changed, old, new, "base", "head")
                self.assertEqual(set(plan.reasons), self.modules)
                self.assertTrue(any("unknown Python owner" in item for item in plan.fallbacks))

    def test_mapped_unmodeled_script_still_uses_late_fail_closed_fallback(self) -> None:
        path = SCRIPT_OWNERS[0]
        old = self.sources()
        new = {**old, path: "from importlib import import_module\nplugin = import_module(plugin_name)\n"}
        plan = affected_plan(self.tests, self.rules, [path], old, new, "base", "head")
        self.assertEqual(set(plan.reasons), self.modules)
        self.assertTrue(any(f"unmodeled changed source: {path}" in item for item in plan.fallbacks))

    def test_unrelated_owned_source_does_not_select_agent_group(self) -> None:
        old = self.sources()
        changed_body = old[UNRELATED_PRODUCTION].replace(
            "self.rng.uniform(*_HUMAN_DELAY_JITTER_RANGE)", "self.rng.uniform(1.0, 1.0)", 1,
        )
        self.assertNotEqual(changed_body, old[UNRELATED_PRODUCTION])
        new = {**old, UNRELATED_PRODUCTION: changed_body}
        plan = affected_plan(
            self.tests, self.rules, [UNRELATED_PRODUCTION], old, new, "base", "head",
        )
        component = "app.automation.engine"
        expected = self.mandatory | {
            test.module for test in self.tests
            if test.tier == "unit" and (
                test.component == component or test.component.startswith(component + ".")
            )
        }
        self.assertEqual(set(plan.reasons), expected)
        self.assertFalse(plan.fallbacks)
        self.assertTrue(self.agent_modules.isdisjoint(plan.reasons))

    def test_migrated_modules_are_in_inventory_and_ci_shard_union(self) -> None:
        portable = {test.path for test in self.tests}
        self.assertTrue(set(AGENT_TEST_PATHS) <= portable)
        self.assertNotIn("tests/native/tools/agent_runtime/test_visible_console.py", portable)

        names = [test.module for test in self.tests]
        shards = [shard_modules(names, index, 4) for index in range(4)]
        union = {module for shard in shards for module in shard}
        self.assertEqual(union, set(names))
        self.assertEqual(sum(len(shard) for shard in shards), len(union))
        self.assertTrue(self.agent_modules <= union)


if __name__ == "__main__":
    unittest.main()
