"""Realistic change matrix with explicit selection and fail-closed expectations."""

from dataclasses import dataclass, field
import unittest

from tools.test_selection.models import inventory
from tools.test_selection.ownership import OwnershipRules, ResourceRule
from tools.test_selection.planner import affected_plan


WORKER = "pnc_automation/app/automation/engine/worker.py"
MATCHER = "pnc_automation/core/vision/matcher.py"
GATEWAY = "tools/gateway.py"
BODY = "def run(value=1):\n    return value + 1\n"
PRIVATE_EDIT = "def run(value=1):\n    return value + 2\n"
TEST_PATHS = {
    "engine": "tests/unit/app/automation/engine/test_worker.py",
    "sibling": "tests/unit/app/automation/engine/test_cache.py",
    "runner": "tests/integration/entrypoints/test_runner.py",
    "api": "tests/contract/entrypoints/test_api.py",
    "architecture": "tests/architecture/test_boundaries.py",
    "vision": "tests/unit/core/vision/test_matcher.py",
    "workflow": "tests/integration/workflows/test_daily.py",
}
TESTS = inventory(list(TEST_PATHS.values()))
MODULES = {label: path.removesuffix(".py").replace("/", ".") for label, path in TEST_PATHS.items()}
MANDATORY = frozenset({"api", "architecture"})
ENGINE = MANDATORY | {"engine", "sibling", "runner"}
ALL = frozenset(TEST_PATHS)
RULES = OwnershipRules(
    ("pyproject.toml", "requirements*", "tests/support/*", "tests/selection_rules.yaml",
     "tests/__init__.py", "tools/test_selection/*", "pnc_automation/*/__init__.py",
     "pnc_automation/__init__.py", "pnc_automation/app/pnc/domain/*"),
    ("*.md", ".agents/*"),
    (ResourceRule("pnc_automation/templates/*", ("vision",)),
     ResourceRule("scripts/*.yaml", ("integration", "contract")),
     ResourceRule("config/*.json", ("vision", "integration"))),
)


def sources() -> dict[str, str]:
    result = {path: "# Synthetic tests are data, never imported.\n" for path in TEST_PATHS.values()}
    result.update({
        WORKER: BODY, MATCHER: BODY, GATEWAY: "from pnc_automation.app.automation.engine.worker import run\n",
        TEST_PATHS["engine"]: "from pnc_automation.app.automation.engine.worker import run\n",
        TEST_PATHS["runner"]: "import tools.gateway\n",
        TEST_PATHS["vision"]: "from pnc_automation.core.vision.matcher import run\n",
    })
    return result


@dataclass(frozen=True)
class ChangeCase:
    name: str
    changed: tuple[str, ...]
    expected: frozenset[str]
    fallback: str | None = None
    old_updates: dict[str, str] = field(default_factory=dict)
    new_updates: dict[str, str] = field(default_factory=dict)
    removed_old: tuple[str, ...] = ()
    removed_new: tuple[str, ...] = ()


CASES = (
    ChangeCase("private worker body", (WORKER,), ENGINE, new_updates={WORKER: PRIVATE_EDIT}),
    ChangeCase("private vision body", (MATCHER,), MANDATORY | {"vision"}, new_updates={MATCHER: PRIVATE_EDIT}),
    ChangeCase("tools facade body", (GATEWAY,), MANDATORY | {"runner"}, new_updates={GATEWAY: "from pnc_automation.app.automation.engine.worker import run\n# new comment\n"}),
    ChangeCase("changed test selects itself", (TEST_PATHS["engine"],), MANDATORY | {"engine"}),
    ChangeCase("new test selects itself", (TEST_PATHS["engine"],), MANDATORY | {"engine"}, removed_old=(TEST_PATHS["engine"],)),
    ChangeCase("removed consumer import still selected", (WORKER, TEST_PATHS["runner"]), ENGINE, new_updates={WORKER: PRIVATE_EDIT, TEST_PATHS["runner"]: "pass\n"}),
    ChangeCase("new consumer import selected", (WORKER, TEST_PATHS["workflow"]), ENGINE | {"workflow"}, new_updates={WORKER: PRIVATE_EDIT, TEST_PATHS["workflow"]: "import tools.gateway\n"}),
    ChangeCase("deleted production module", (WORKER,), ALL, "added/deleted production module", removed_new=(WORKER,)),
    ChangeCase("added production module", (WORKER,), ALL, "added/deleted production module", removed_old=(WORKER,)),
    ChangeCase("renamed production module", (WORKER, "pnc_automation/app/automation/engine/renamed.py"), ALL, "added/deleted production module", removed_new=(WORKER,), new_updates={"pnc_automation/app/automation/engine/renamed.py": BODY}),
    ChangeCase("public parameter rename", (WORKER,), ALL, "public declaration changed", new_updates={WORKER: "def run(other=1):\n    return other + 1\n"}),
    ChangeCase("public default change", (WORKER,), ALL, "public declaration changed", new_updates={WORKER: "def run(value=2):\n    return value + 1\n"}),
    ChangeCase("public return annotation", (WORKER,), ALL, "public declaration changed", new_updates={WORKER: "def run(value=1) -> int:\n    return value + 1\n"}),
    ChangeCase("public decorator", (WORKER,), ALL, "public declaration changed", new_updates={WORKER: "@cached\n" + BODY}),
    ChangeCase("serialized field change", (WORKER,), ALL, "public declaration changed", old_updates={WORKER: "class Record:\n    count: int = 1\n"}, new_updates={WORKER: "class Record:\n    count: str = '1'\n"}),
    ChangeCase("public constant change", (WORKER,), ALL, "public declaration changed", old_updates={WORKER: "MODE = 'safe'\n"}, new_updates={WORKER: "MODE = 'unsafe'\n"}),
    ChangeCase("syntax error in changed production", (WORKER,), ALL, "cannot parse changed source", new_updates={WORKER: "def run(:"}),
    ChangeCase("syntax error in changed test", (TEST_PATHS["engine"],), ALL, "unmodeled changed source", new_updates={TEST_PATHS["engine"]: "def test_bad(:"}),
    ChangeCase("unknown YAML resource", ("assets/new.yaml",), ALL, "unknown non-Python dependency"),
    ChangeCase("unknown JSON resource", ("assets/catalog.json",), ALL, "unknown non-Python dependency"),
    ChangeCase("unknown PNG resource", ("assets/anchor.png",), ALL, "unknown non-Python dependency"),
    ChangeCase("unknown SQL resource", ("schema/migration.sql",), ALL, "unknown non-Python dependency"),
    ChangeCase("unknown extensionless resource", ("runtime/CATALOG",), ALL, "unknown non-Python dependency"),
    ChangeCase("owned nested PNG resource", ("pnc_automation/templates/home/button.png",), MANDATORY | {"vision"}),
    ChangeCase("owned authored YAML", ("scripts/claim.yaml",), MANDATORY | {"runner", "workflow"}),
    ChangeCase("owned config JSON", ("config/anchors.json",), MANDATORY | {"vision", "runner", "workflow"}),
    ChangeCase("unknown Python root", ("plugins/new.py",), ALL, "unknown Python owner", new_updates={"plugins/new.py": "pass\n"}),
    ChangeCase("unmapped tool", ("tools/orphan.py",), ALL, "no test dependency established", old_updates={"tools/orphan.py": BODY}, new_updates={"tools/orphan.py": PRIVATE_EDIT}),
    ChangeCase("shared pyproject", ("pyproject.toml",), ALL, "shared contract/infrastructure"),
    ChangeCase("dependency lock change", ("requirements-dev.txt",), ALL, "shared contract/infrastructure"),
    ChangeCase("shared support helper", ("tests/support/core/fakes.py",), ALL, "shared contract/infrastructure", new_updates={"tests/support/core/fakes.py": "pass\n"}),
    ChangeCase("selection rules change", ("tests/selection_rules.yaml",), ALL, "shared contract/infrastructure"),
    ChangeCase("test bootstrap change", ("tests/__init__.py",), ALL, "shared contract/infrastructure"),
    ChangeCase("selector implementation change", ("tools/test_selection/planner.py",), ALL, "shared contract/infrastructure"),
    ChangeCase("package init change", ("pnc_automation/app/automation/__init__.py",), ALL, "shared contract/infrastructure"),
    ChangeCase("root package init change", ("pnc_automation/__init__.py",), ALL, "shared contract/infrastructure"),
    ChangeCase("shared domain model change", ("pnc_automation/app/pnc/domain/castles.py",), ALL, "shared contract/infrastructure"),
    ChangeCase("documentation only", ("README.md", "docs/design.md"), frozenset()),
    ChangeCase("skill documentation only", (".agents/skills/custom/SKILL.md",), frozenset()),
    ChangeCase("mixed docs and source", ("README.md", WORKER), ENGINE, new_updates={WORKER: PRIVATE_EDIT}),
    ChangeCase("no changes", (), frozenset()),
    ChangeCase("unrelated dynamic production loading", (WORKER,), ALL, "unmodeled application dynamic imports", new_updates={WORKER: PRIVATE_EDIT, "pnc_automation/plugins.py": "importlib.import_module(plugin_name)"}),
    ChangeCase("old dynamic production loading remains conservative", (WORKER,), ALL, "unmodeled application dynamic imports", old_updates={"pnc_automation/plugins.py": "__import__(plugin_name)"}, new_updates={WORKER: PRIVATE_EDIT}),
    ChangeCase("removed helper import remains reachable", ("tests/helpers.py",), MANDATORY | {"engine"}, old_updates={"tests/helpers.py": "pass\n", TEST_PATHS["engine"]: "import tests.helpers\n"}, new_updates={TEST_PATHS["engine"]: "pass\n"}),
    ChangeCase("renamed test retains surviving consumer", ("tests/old_test.py", TEST_PATHS["engine"]), MANDATORY | {"engine"}, old_updates={"tests/old_test.py": "pass\n", TEST_PATHS["engine"]: "import tests.old_test\n"}, new_updates={TEST_PATHS["engine"]: "pass\n"}),
)


class SelectionReviewRegressionTests(unittest.TestCase):
    """Regressions for uncertainty, executable documentation, and public contracts."""

    def test_uncertain_eligible_tests_are_selected_on_unrelated_python_change(self) -> None:
        for label in ("sibling", "workflow"):
            with self.subTest(tier=label):
                old = sources()
                old[TEST_PATHS[label]] = (
                    "from importlib import import_module\n"
                    "target = 'pnc_automation.core.vision.matcher'\n"
                    "matcher = import_module(target)\n"
                )
                new = {**old, MATCHER: PRIVATE_EDIT}
                plan = affected_plan(TESTS, RULES, [MATCHER], old, new, "base", "head")
                expected = MANDATORY | {"vision", label}
                self.assertEqual(set(plan.reasons), {MODULES[name] for name in expected})
                self.assertFalse(plan.fallbacks)

    def test_uncertain_support_and_tools_select_their_test_consumers(self) -> None:
        for helper in ("tests/support/dynamic_loader.py", "tools/dynamic_loader.py"):
            with self.subTest(helper=helper):
                old = sources()
                old[helper] = (
                    "from importlib import import_module\n"
                    "def load(target):\n    return import_module(target)\n"
                )
                module = helper.removesuffix(".py").replace("/", ".")
                old[TEST_PATHS["workflow"]] = f"from {module} import load\n"
                new = {**old, MATCHER: PRIVATE_EDIT}
                plan = affected_plan(TESTS, RULES, [MATCHER], old, new, "base", "head")
                expected = MANDATORY | {"vision", "workflow"}
                self.assertEqual(set(plan.reasons), {MODULES[name] for name in expected})
                self.assertFalse(plan.fallbacks)

    def test_python_under_agents_documentation_glob_requires_full_tests(self) -> None:
        for path in (".agents/check.py", ".agents/skills/example/scripts/check.py"):
            for added in (False, True):
                with self.subTest(path=path, added=added):
                    old = sources()
                    if not added:
                        old[path] = BODY
                    new = {**old, path: PRIVATE_EDIT}
                    plan = affected_plan(TESTS, RULES, [path], old, new, "base", "head")
                    self.assertEqual(set(plan.reasons), set(MODULES.values()))
                    self.assertTrue(plan.fallbacks)
                    self.assertNotIn("no_test_reason", plan.document())

    def test_constructor_signature_change_requires_full_tests(self) -> None:
        old = {**sources(), WORKER: "class Worker:\n    def __init__(self, value): pass\n"}
        new = {**old, WORKER: "class Worker:\n    def __init__(self, value, required): pass\n"}
        plan = affected_plan(TESTS, RULES, [WORKER], old, new, "base", "head")
        self.assertEqual(set(plan.reasons), set(MODULES.values()))
        self.assertIn(f"public declaration changed: {WORKER}", plan.fallbacks)

    def test_public_dunder_contract_changes_require_full_tests(self) -> None:
        declarations = (
            ("def __call__(self, value=1): pass", "def __call__(self, value=2): pass"),
            ("def __iter__(self): pass", "def __iter__(self) -> Iterator[int]: pass"),
            ("async def __aenter__(self): pass", "async def __aenter__(self) -> Worker: pass"),
        )
        for before, after in declarations:
            with self.subTest(declaration=before):
                old = {**sources(), WORKER: f"class Worker:\n    {before}\n"}
                new = {**old, WORKER: f"class Worker:\n    {after}\n"}
                plan = affected_plan(TESTS, RULES, [WORKER], old, new, "base", "head")
                self.assertEqual(set(plan.reasons), set(MODULES.values()))
                self.assertIn(f"public declaration changed: {WORKER}", plan.fallbacks)

    def test_public_type_alias_change_requires_full_tests(self) -> None:
        declarations = (
            ("type Value = int\n", "type Value = str\n"),
            ("type Values[T] = list[T]\n", "type Values[T] = tuple[T, ...]\n"),
        )
        for before, after in declarations:
            with self.subTest(declaration=before):
                old = {**sources(), WORKER: before}
                new = {**old, WORKER: after}
                plan = affected_plan(TESTS, RULES, [WORKER], old, new, "base", "head")
                self.assertEqual(set(plan.reasons), set(MODULES.values()))
                self.assertIn(f"public declaration changed: {WORKER}", plan.fallbacks)


class AffectedPlanMatrixTests(unittest.TestCase):
    def test_realistic_and_adversarial_change_matrix(self) -> None:
        self.assertGreaterEqual(len(CASES), 30)
        self.assertEqual(len({case.name for case in CASES}), len(CASES))
        for case in CASES:
            with self.subTest(change=case.name):
                old, new = sources(), sources()
                old.update(case.old_updates)
                new.update(case.new_updates)
                for path in case.removed_old:
                    old.pop(path, None)
                for path in case.removed_new:
                    new.pop(path, None)
                plan = affected_plan(TESTS, RULES, list(case.changed), old, new, "base-sha", "head-sha")
                self.assertEqual(set(plan.reasons), {MODULES[label] for label in case.expected})
                self.assertTrue(all(reasons for reasons in plan.reasons.values()))
                self.assertEqual(plan.changed_paths, list(case.changed))
                self.assertEqual((plan.base, plan.head), ("base-sha", "head-sha"))
                if case.fallback is None:
                    self.assertEqual(plan.fallbacks, [])
                else:
                    self.assertTrue(any(case.fallback in reason for reason in plan.fallbacks), plan.fallbacks)

    def test_no_inventory_is_error_even_for_docs(self) -> None:
        with self.assertRaisesRegex(ValueError, "No portable test modules"):
            affected_plan((), RULES, ["README.md"], {}, {}, "base", "head")

    def test_owner_and_reverse_dependency_reasons_are_both_retained(self) -> None:
        old, new = sources(), sources()
        new[WORKER] = PRIVATE_EDIT
        plan = affected_plan(TESTS, RULES, [WORKER], old, new, "base", "head")
        reasons = plan.reasons[MODULES["engine"]]
        self.assertIn(f"component owner: {WORKER}", reasons)
        self.assertIn(f"reverse import dependency: {WORKER}", reasons)
        self.assertNotIn(MODULES["vision"], plan.reasons)

    def test_missing_graph_cannot_authorize_partial_test_run(self) -> None:
        for old, new in (({}, {}), ({}, sources()), (sources(), {})):
            with self.subTest(old_available=bool(old), new_available=bool(new)):
                plan = affected_plan(TESTS, RULES, [TEST_PATHS["engine"]], old, new, "base", "head")
                self.assertEqual(set(plan.reasons), set(MODULES.values()))
                self.assertTrue(plan.fallbacks)

    def test_docs_only_plan_has_machine_readable_no_test_explanation(self) -> None:
        plan = affected_plan(TESTS, RULES, ["README.md"], sources(), sources(), "base", "head")
        self.assertEqual(plan.reasons, {})
        self.assertEqual(plan.fallbacks, [])
        self.assertTrue(plan.document().get("no_test_reason"), "Documentation-only zero-test plans must explain why execution is unnecessary")

    def test_unknown_test_helper_cannot_silently_run_only_mandatory_checks(self) -> None:
        old, new = sources(), sources()
        old["tests/new_support.py"] = BODY
        new["tests/new_support.py"] = PRIVATE_EDIT
        plan = affected_plan(TESTS, RULES, ["tests/new_support.py"], old, new, "base", "head")
        self.assertEqual(set(plan.reasons), set(MODULES.values()))
        self.assertTrue(plan.fallbacks)

    def test_changed_path_missing_from_nonempty_snapshots_falls_back(self) -> None:
        old, new = sources(), sources()
        old.pop(TEST_PATHS["engine"])
        new.pop(TEST_PATHS["engine"])
        plan = affected_plan(TESTS, RULES, [TEST_PATHS["engine"]], old, new, "base", "head")
        self.assertEqual(set(plan.reasons), set(MODULES.values()))
        self.assertTrue(plan.fallbacks)

    def test_explicit_resource_owner_is_not_hidden_by_markdown_docs_rule(self) -> None:
        rules = OwnershipRules(
            (), ("*.md",), (ResourceRule("assets/*", ("vision",)),)
        )
        plan = affected_plan(
            TESTS, rules, ["assets/catalog.md"], sources(), sources(), "base", "head"
        )
        self.assertIn(MODULES["vision"], plan.reasons)
        self.assertFalse(plan.document().get("no_test_reason"))
