"""Run an isolated synthetic unittest/native-selector/pytest-testmon fault audit.

This is an opt-in local experiment, never a normal test or a PNC runtime entrypoint.
Every case has its own unchanged baseline and freshly seeded testmon database.
Generated fixtures and subprocess output remain under .test-impact.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import textwrap
import time
from uuid import uuid4
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.test_selection.models import inventory
from tools.test_selection.ownership import OwnershipRules, ResourceRule
from tools.test_selection.planner import affected_plan


NATIVE_SOURCE_HASHES = {
    name: hashlib.sha256((REPO_ROOT / "tools" / "test_selection" / name).read_bytes()).hexdigest()
    for name in ("models.py", "ownership.py", "planner.py", "python_graph.py")
}
CORE = "pnc_automation/demo/core.py"
BEHAVIOR_PATH = "tests/unit/demo/test_behaviors.py"
BEHAVIOR = "tests.unit.demo.test_behaviors.BehaviorTests."
API = "tests.integration.entrypoints.test_api.ApiTests.test_total"
CONTRACT = "tests.contract.test_public.PublicTests.test_signature"
RESOURCE = "tests.unit.vision.test_resources.ResourceTests."
SCANNER = "tests.architecture.test_source.SourceTests."
EXPECTED_VERSIONS = {"pytest": "9.0.2", "coverage": "7.10.7", "pytest-testmon": "2.2.0"}
RULES = OwnershipRules(
    ("pyproject.toml", "tests/support/*", "tests/__init__.py", "pnc_automation/*/__init__.py",
     "pnc_automation/__init__.py"),
    ("*.md",),
    (ResourceRule("assets/*", ("vision",)),),
)

NETWORK_GUARD = """
import sys
def reject_network(event, arguments):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind'}:
        raise RuntimeError('Network access forbidden in synthetic experiment: ' + event)
sys.addaudithook(reject_network)
"""

UNIT_DRIVER = NETWORK_GUARD + """
import json
from pathlib import Path
import unittest
class Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.executed = []
    def startTest(self, test):
        self.executed.append(test.id())
        super().startTest(test)
loader = unittest.TestLoader()
suite = (loader.loadTestsFromNames(sys.argv[2:]) if len(sys.argv) > 2
         else loader.discover('tests', top_level_dir='.'))
result = Result()
suite.run(result)
document = {'executed': sorted(result.executed),
            'failures': sorted(test.id() for test, _ in result.failures),
            'errors': sorted(test.id() for test, _ in result.errors),
            'details': {test.id(): detail for test, detail in result.failures + result.errors},
            'skipped': sorted(test.id() for test, _ in result.skipped),
            'loader_errors': loader.errors}
Path(sys.argv[1]).write_text(json.dumps(document, indent=2), encoding='utf-8')
sys.exit(0 if result.wasSuccessful() and not loader.errors else 1)
"""

PYTEST_DRIVER = NETWORK_GUARD + """
import pytest
sys.exit(pytest.main(sys.argv[1:]))
"""


@dataclass(frozen=True)
class Mutation:
    name: str
    category: str
    expected: tuple[str, ...]
    updates: dict[str, str] = field(default_factory=dict)
    deletes: tuple[str, ...] = ()
    cache: str | None = None
    guard: str | None = None


def source(value: str) -> str:
    return textwrap.dedent(value).lstrip("\n")


def baseline_files() -> dict[str, str]:
    """Return the complete authored synthetic fixture, including its test oracles."""
    files = {
        "pytest.ini": "[pytest]\ntestpaths = tests\naddopts =\n",
        "pnc_automation/__init__.py": "MODE = 'safe'\n",
        "pnc_automation/demo/__init__.py": source("""
            from importlib import import_module
            _LAZY_EXPORTS = {'Thing': ('pnc_automation.demo.lazy_impl', 'Thing')}
            def __getattr__(name):
                module, symbol = _LAZY_EXPORTS[name]
                return getattr(import_module(module), symbol)
        """),
        CORE: "def calculate(value=3):\n    return value * 2\n",
        "pnc_automation/demo/api.py": "from .core import calculate\ndef total(value=4):\n    return calculate(value)\n",
        "pnc_automation/demo/lazy_impl.py": "class Thing:\n    def value(self):\n        return 5\n",
        "pnc_automation/demo/alternate.py": "class Thing:\n    def value(self):\n        return 99\ndef calculate(value=3):\n    return 99\n",
        "pnc_automation/demo/values.py": "RATE = 3\n",
        "pnc_automation/demo/relative.py": "from .values import RATE\ndef amount():\n    return RATE * 2\n",
        "pnc_automation/demo/records.py": "from dataclasses import dataclass\n@dataclass\nclass Record:\n    count: int = 3\n    def next(self):\n        return self.count + 1\n",
        "pnc_automation/demo/decorated.py": source("""
            def twice(function):
                def wrapped():
                    return function() * 2
                return wrapped
            @twice
            def value():
                return 3
        """),
        "pnc_automation/demo/module_setup.py": "def token():\n    return 'module-safe'\n",
        "pnc_automation/demo/class_setup.py": "def token():\n    return 'class-safe'\n",
        "pnc_automation/demo/plugin.py": "def value():\n    return 7\n",
        "pnc_automation/demo/loading.py": source("""
            from importlib import import_module
            def literal():
                return import_module('pnc_automation.demo.plugin').value()
            def dynamic():
                name = 'pnc_automation.demo.plugin'
                return import_module(name).value()
        """),
        "pnc_automation/demo/errors.py": "def reject():\n    raise ValueError('bad input')\n",
        "pnc_automation/demo/async_service.py": "async def answer():\n    return 42\n",
        "pnc_automation/demo/source_contract.py": "# Read as data, never imported.\ndef required():\n    return 1\n",
        "tests/support/expected.py": "EXPECTED = 6\n",
        "assets/catalog.json": '{"home": [12, 34]}',
        "assets/workflow.yaml": "task: observe\n",
        "assets/button.png": "PNG-fixture-signature",
        "assets/captured.txt": "HOME READY",
        "assets/schema.sql": "CREATE TABLE events(id INTEGER);",
        "assets/catalog.md": "Runtime catalog: HOME",
        "vendor/weights.bin": "weights-v1",
        BEHAVIOR_PATH: source("""
            import unittest

            def setUpModule():
                global module_value
                from pnc_automation.demo.module_setup import token
                module_value = token()

            class BehaviorTests(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    from pnc_automation.demo.class_setup import token
                    cls.class_value = token()

                def test_default(self):
                    from pnc_automation.demo.core import calculate
                    self.assertEqual(calculate(), 6)

                def test_explicit(self):
                    from pnc_automation.demo.core import calculate
                    self.assertEqual(calculate(3), 6)

                def test_keyword(self):
                    from pnc_automation.demo.core import calculate
                    self.assertEqual(calculate(value=3), 6)

                def test_lazy(self):
                    from pnc_automation.demo import Thing
                    self.assertEqual(Thing().value(), 5)

                def test_relative(self):
                    from pnc_automation.demo.relative import amount
                    self.assertEqual(amount(), 6)

                def test_record_field(self):
                    from pnc_automation.demo.records import Record
                    self.assertEqual(Record().count, 3)

                def test_record_method(self):
                    from pnc_automation.demo.records import Record
                    self.assertEqual(Record().next(), 4)

                def test_decorated(self):
                    from pnc_automation.demo.decorated import value
                    self.assertEqual(value(), 6)

                def test_module_setup(self):
                    self.assertEqual(module_value, 'module-safe')

                def test_class_setup(self):
                    self.assertEqual(self.class_value, 'class-safe')

                def test_helper(self):
                    from tests.support.expected import EXPECTED
                    self.assertEqual(EXPECTED, 6)

                def test_package_init(self):
                    from pnc_automation import MODE
                    self.assertEqual(MODE, 'safe')

                def test_dynamic(self):
                    from pnc_automation.demo.loading import dynamic
                    self.assertEqual(dynamic(), 7)

                def test_literal_dynamic(self):
                    from pnc_automation.demo.loading import literal
                    self.assertEqual(literal(), 7)

                def test_error_contract(self):
                    from pnc_automation.demo.errors import reject
                    with self.assertRaisesRegex(ValueError, 'bad input'):
                        reject()

                def test_async(self):
                    from pnc_automation.demo.async_service import answer
                    coroutine = answer()
                    try:
                        with self.assertRaises(StopIteration) as result:
                            coroutine.send(None)
                        self.assertEqual(result.exception.value, 42)
                    finally:
                        coroutine.close()
        """),
        "tests/integration/entrypoints/test_api.py": source("""
            import unittest
            class ApiTests(unittest.TestCase):
                def test_total(self):
                    from pnc_automation.demo.api import total
                    self.assertEqual(total(), 8)
        """),
        "tests/contract/test_public.py": source("""
            import inspect
            import unittest
            class PublicTests(unittest.TestCase):
                def test_signature(self):
                    from pnc_automation.demo.core import calculate
                    self.assertEqual(list(inspect.signature(calculate).parameters), ['value'])
        """),
        "tests/architecture/test_source.py": source("""
            import ast
            from pathlib import Path
            import unittest
            class SourceTests(unittest.TestCase):
                def test_forbidden_import(self):
                    tree = ast.parse(Path('pnc_automation/demo/source_contract.py').read_text())
                    imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                               for alias in node.names]
                    self.assertNotIn('forbidden_layer', imports)
                def test_required_symbol(self):
                    tree = ast.parse(Path('pnc_automation/demo/source_contract.py').read_text())
                    names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
                    self.assertIn('required', names)
        """),
        "tests/unit/vision/test_resources.py": source("""
            import json
            from pathlib import Path
            import unittest
            class ResourceTests(unittest.TestCase):
                def test_json(self):
                    self.assertEqual(json.loads(Path('assets/catalog.json').read_text()), {'home': [12, 34]})
                def test_yaml(self):
                    self.assertEqual(Path('assets/workflow.yaml').read_text(), 'task: observe\\n')
                def test_png(self):
                    self.assertEqual(Path('assets/button.png').read_bytes(), b'PNG-fixture-signature')
                def test_text(self):
                    self.assertEqual(Path('assets/captured.txt').read_text(), 'HOME READY')
                def test_sql(self):
                    self.assertEqual(Path('assets/schema.sql').read_text(), 'CREATE TABLE events(id INTEGER);')
                def test_markdown(self):
                    self.assertEqual(Path('assets/catalog.md').read_text(), 'Runtime catalog: HOME')
                def test_binary(self):
                    self.assertEqual(Path('vendor/weights.bin').read_bytes(), b'weights-v1')
        """),
    }
    for path in tuple(files):
        if path.startswith("tests/") and path.endswith(".py"):
            for parent in Path(path).parents:
                if parent.as_posix() != ".":
                    files.setdefault((parent / "__init__.py").as_posix(), "")
    return files


def mutations(files: dict[str, str]) -> tuple[Mutation, ...]:
    """Thirty-four independent faults, each with an exact full-suite oracle."""
    def edit(name: str, path: str, before: str, after: str, expected: tuple[str, ...],
             category: str = "python", guard: str | None = None) -> Mutation:
        if before not in files[path]:
            raise ValueError(f"Mutation {name} has no matching baseline fragment")
        return Mutation(name, category, expected, {path: files[path].replace(before, after)}, guard=guard)

    core_failures = tuple(BEHAVIOR + name for name in ("test_default", "test_explicit", "test_keyword")) + (API,)
    cases = [
        edit("private-body", CORE, "value * 2", "value * 2 + 1", core_failures),
        edit("public-default", CORE, "value=3", "value=4", (BEHAVIOR + "test_default",)),
        edit("public-signature", CORE, "value", "amount", (BEHAVIOR + "test_keyword", CONTRACT)),
        edit("api-body", "pnc_automation/demo/api.py", "calculate(value)", "calculate(value + 1)", (API,)),
        edit("api-default", "pnc_automation/demo/api.py", "value=4", "value=5", (API,)),
        edit("lazy-implementation", "pnc_automation/demo/lazy_impl.py", "return 5", "return 6", (BEHAVIOR + "test_lazy",)),
        edit("lazy-export-remap", "pnc_automation/demo/__init__.py", ".lazy_impl", ".alternate", (BEHAVIOR + "test_lazy",)),
        edit("relative-from-symbol", "pnc_automation/demo/values.py", "RATE = 3", "RATE = 4", (BEHAVIOR + "test_relative",)),
        edit("dataclass-field", "pnc_automation/demo/records.py", "count: int = 3", "count: int = 5", (BEHAVIOR + "test_record_field", BEHAVIOR + "test_record_method")),
        edit("class-method", "pnc_automation/demo/records.py", "self.count + 1", "self.count + 2", (BEHAVIOR + "test_record_method",)),
        edit("decorator-body", "pnc_automation/demo/decorated.py", "function() * 2", "function() * 3", (BEHAVIOR + "test_decorated",)),
        edit("module-setup", "pnc_automation/demo/module_setup.py", "module-safe", "module-broken", (BEHAVIOR + "test_module_setup",)),
        edit("class-setup", "pnc_automation/demo/class_setup.py", "class-safe", "class-broken", (BEHAVIOR + "test_class_setup",)),
        edit("shared-helper", "tests/support/expected.py", "EXPECTED = 6", "EXPECTED = 7", (BEHAVIOR + "test_helper",)),
        edit("test-assertion", BEHAVIOR_PATH, "self.assertEqual(calculate(3), 6)", "self.assertEqual(calculate(3), 7)", (BEHAVIOR + "test_explicit",)),
        Mutation("new-failing-test", "inventory", ("tests.unit.demo.test_new.NewTests.test_new",), {
            "tests/unit/demo/test_new.py": "import unittest\nclass NewTests(unittest.TestCase):\n    def test_new(self):\n        self.assertEqual(1, 2)\n"}),
        Mutation("production-rename", "rename", core_failures, {
            "pnc_automation/demo/renamed.py": files[CORE].replace("value * 2", "value * 2 + 1"),
            BEHAVIOR_PATH: files[BEHAVIOR_PATH].replace("demo.core", "demo.renamed"),
            "pnc_automation/demo/api.py": files["pnc_automation/demo/api.py"].replace(".core", ".renamed"),
            "tests/contract/test_public.py": files["tests/contract/test_public.py"].replace("demo.core", "demo.renamed"),
        }, (CORE,)),
        Mutation("production-delete", "delete", (BEHAVIOR + "test_lazy",), deletes=("pnc_automation/demo/lazy_impl.py",)),
        edit("removed-import-edge", "pnc_automation/demo/api.py", "from .core", "from .alternate", (API,)),
        edit("package-initialization", "pnc_automation/__init__.py", "safe", "broken", (BEHAVIOR + "test_package_init",)),
        edit("dynamic-plugin", "pnc_automation/demo/plugin.py", "return 7", "return 8", (BEHAVIOR + "test_dynamic", BEHAVIOR + "test_literal_dynamic")),
        edit("exception-contract", "pnc_automation/demo/errors.py", "ValueError", "RuntimeError", (BEHAVIOR + "test_error_contract",)),
        edit("async-body", "pnc_automation/demo/async_service.py", "return 42", "return 43", (BEHAVIOR + "test_async",)),
        edit("source-scanned-import", "pnc_automation/demo/source_contract.py", "# Read as data, never imported.", "import forbidden_layer", (SCANNER + "test_forbidden_import",), "source-as-data", "mandatory architecture source scanning"),
        edit("source-scanned-symbol", "pnc_automation/demo/source_contract.py", "def required", "def removed", (SCANNER + "test_required_symbol",), "source-as-data", "mandatory architecture source scanning"),
    ]
    for name, path, replacement, test in (
        ("static-json", "assets/catalog.json", '{"home": null}', "test_json"),
        ("static-yaml", "assets/workflow.yaml", "task: spend\n", "test_yaml"),
        ("static-png", "assets/button.png", "corrupt image", "test_png"),
        ("static-text", "assets/captured.txt", "NO HOME", "test_text"),
        ("static-sql", "assets/schema.sql", "DROP TABLE events;", "test_sql"),
        ("static-markdown", "assets/catalog.md", "Runtime catalog: BROKEN", "test_markdown"),
        ("unknown-binary", "vendor/weights.bin", "corrupt weights", "test_binary"),
    ):
        cases.append(Mutation(name, "static-resource", (RESOURCE + test,), {path: replacement},
                              guard="explicit resource owners or unknown-resource full fallback"))
    for cache in ("missing", "corrupt"):
        cases.append(Mutation(f"cache-{cache}", "cache", core_failures,
                              {CORE: files[CORE].replace("value * 2", "value * 2 + 1")}, cache=cache,
                              guard="full run on missing/corrupt selection state"))
    if len(cases) < 30 or len({case.name for case in cases}) != len(cases):
        raise ValueError("Experiment requires at least 30 unique cases")
    return tuple(cases)


def write_fixture(root: Path, files: dict[str, str]) -> None:
    """Write generated fixture files only below the supplied experiment root."""
    for relative, content in files.items():
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError(f"Fixture path escapes root: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


def child_environment(root: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "COVERAGE_PROCESS_START",
                "TESTMON_DATAFILE", "TMNET_API_KEY", "TMNET_URL"):
        environment.pop(key, None)
    environment.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1",
                        "TESTMON_DATAFILE": str(root / ".testmondata")})
    return environment


def command(root: Path, arguments: list[str], log: Path) -> dict:
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-B", *arguments], cwd=root, env=child_environment(root),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        check=False,
    )
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    return {"returncode": result.returncode, "seconds": time.perf_counter() - started,
            "log": str(log), "arguments": [arguments[0], "<embedded driver>", *arguments[2:]]}


def run_unittest(root: Path, output: Path, modules: list[str] | None = None) -> dict:
    if modules == []:
        return {"returncode": 0, "seconds": 0.0, "executed": [], "failures": [], "errors": [],
                "skipped": [], "loader_errors": [], "not_run": "native plan selected no modules"}
    result = command(root, ["-c", UNIT_DRIVER, str(output), *(modules or [])], output.with_suffix(".log"))
    if not output.exists():
        raise RuntimeError(f"Unittest did not produce a report: {result}")
    return {**result, **json.loads(output.read_text(encoding="utf-8"))}


def run_testmon(root: Path, output: Path, seed: bool = False) -> dict:
    arguments = ["-c", PYTEST_DRIVER, "-p", "testmon.pytest_testmon", "--testmon",
                 "-c", str(root / "pytest.ini"), "--rootdir", str(root), "--confcutdir", str(root),
                 "--junitxml", str(output), "--tb=short", "-q"]
    if seed:
        arguments.append("--testmon-noselect")
    result = command(root, arguments, output.with_suffix(".log"))
    document = {"executed": [], "failures": [], "errors": [], "skipped": []}
    if output.exists():
        for test in ET.parse(output).iter("testcase"):
            name = test.attrib.get("classname", "") + "." + test.attrib["name"]
            if test.find("skipped") is not None:
                document["skipped"].append(name)
                continue
            document["executed"].append(name)
            if test.find("failure") is not None:
                document["failures"].append(name)
            if test.find("error") is not None:
                document["errors"].append(name)
    return {**result, **{key: sorted(value) for key, value in document.items()}}


def failing_ids(result: dict) -> set[str]:
    return set(result["failures"]) | set(result["errors"])


def digest(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def execute_case(index: int, mutation: Mutation, files: dict[str, str], run_root: Path) -> dict:
    case_root = run_root / f"{index:02d}-{mutation.name}"
    root = case_root / "repo"
    root.mkdir(parents=True)
    write_fixture(root, files)
    baseline = run_unittest(root, case_root / "baseline-unittest.json")
    seed = run_testmon(root, case_root / "seed.xml", seed=True)
    if baseline["returncode"] or seed["returncode"] or set(baseline["executed"]) != set(seed["executed"]):
        raise RuntimeError(f"Baseline parity failed in {case_root}; inspect baseline and seed logs")
    cache_path = root / ".testmondata"
    if not cache_path.is_file():
        raise RuntimeError(f"Seed did not create a testmon database in {root}")
    seeded_cache_digest = hashlib.sha256(cache_path.read_bytes()).hexdigest()
    candidate = {**files, **mutation.updates}
    for relative in mutation.deletes:
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()) or relative not in files:
            raise ValueError(f"Unsafe generated-fixture deletion: {relative}")
        target.unlink()
        del candidate[relative]
    write_fixture(root, mutation.updates)
    for relative in mutation.updates:
        # Avoid timestamp-resolution ambiguities after an immediately preceding seed.
        os.utime(root / relative, (time.time() + 2, time.time() + 2))
    if mutation.cache == "missing":
        cache_path.unlink()
    elif mutation.cache == "corrupt":
        cache_path.write_bytes(b"intentionally corrupt synthetic testmon database")
    changed = sorted(set(mutation.updates) | set(mutation.deletes))
    old_sources = {path: text for path, text in files.items() if path.endswith(".py")}
    new_sources = {path: text for path, text in candidate.items() if path.endswith(".py")}
    plan_started = time.perf_counter()
    plan = affected_plan(inventory(list(candidate)), RULES, changed, old_sources, new_sources,
                         "synthetic-baseline-" + digest(files), "synthetic-candidate-" + digest(candidate))
    planning_seconds = time.perf_counter() - plan_started
    full = run_unittest(root, case_root / "full-unittest.json")
    expected = set(mutation.expected)
    if failing_ids(full) != expected or full["returncode"] != 1:
        raise RuntimeError(f"Fault oracle mismatch in {case_root}: expected {sorted(expected)}, got {sorted(failing_ids(full))}")
    if mutation.cache is None and hashlib.sha256(cache_path.read_bytes()).hexdigest() != seeded_cache_digest:
        raise RuntimeError("Independent unittest unexpectedly changed the seeded testmon database")
    raw = run_testmon(root, case_root / "affected.xml")
    native = run_unittest(root, case_root / "native-unittest.json", sorted(plan.reasons))
    native["planning_seconds"] = planning_seconds
    native["plan"] = plan.document()
    native["source_hashes"] = NATIVE_SOURCE_HASHES
    # Execute a guard bypassing testmon filtering; never let testmon deselect mandatory tests.
    guard_modules = sorted({"tests.architecture.test_source", "tests.contract.test_public"} |
                           ({"tests.unit.vision.test_resources"} if mutation.category == "static-resource" else set()))
    guard = run_unittest(root, case_root / "guard-unittest.json", guard_modules)
    missed_raw = sorted(expected - failing_ids(raw))
    missed_native = sorted(expected - failing_ids(native))
    guarded_misses = sorted(expected - (failing_ids(raw) | failing_ids(guard)))
    record = {
        "index": index, "mutation": asdict(mutation), "changed": changed,
        "fixture_root": str(root), "baseline_source_sha256": digest(files),
        "seed_cache_sha256": seeded_cache_digest, "baseline": baseline, "seed": seed,
        "full_unittest": full, "raw_testmon": raw, "native_selector": native,
        "mandatory_guard": guard, "raw_missed_failure_ids": missed_raw,
        "native_missed_failure_ids": missed_native, "guarded_missed_failure_ids": guarded_misses,
        "raw_tool_error": raw["returncode"] not in (0, 1, 5),
        "raw_false_green": bool(missed_raw) and raw["returncode"] == 0,
        "raw_zero_test_exit": raw["returncode"] == 5,
    }
    (case_root / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def refresh_native(records: list[dict], files: dict[str, str]) -> None:
    """Revalidate native fixes against retained candidates without reseeding testmon."""
    for row in records:
        if row["baseline_source_sha256"] != digest(files):
            raise ValueError("Current fixture differs from the retained experiment baseline")
        root = Path(row["fixture_root"]).resolve()
        expected_root = (REPO_ROOT / ".test-impact" / "testmon-experiment").resolve()
        if not root.is_relative_to(expected_root):
            raise ValueError("Recorded fixture root escapes the experiment directory")
        candidate = {**files, **row["mutation"]["updates"]}
        for path in row["mutation"]["deletes"]:
            del candidate[path]
        observed = {path: (root / path).read_text(encoding="utf-8") for path in candidate}
        if digest(observed) != digest(candidate):
            raise ValueError(f"Retained candidate was modified outside the experiment: {root}")
        old = {path: text for path, text in files.items() if path.endswith(".py")}
        new = {path: text for path, text in candidate.items() if path.endswith(".py")}
        started = time.perf_counter()
        plan = affected_plan(inventory(list(candidate)), RULES, row["changed"], old, new,
                             "synthetic-baseline-" + digest(files), "synthetic-candidate-" + digest(candidate))
        planning_seconds = time.perf_counter() - started
        result = run_unittest(root, root.parent / ("native-refresh-" + uuid4().hex[:8] + ".json"), sorted(plan.reasons))
        result.update({"planning_seconds": planning_seconds, "plan": plan.document(),
                       "source_hashes": NATIVE_SOURCE_HASHES})
        row.setdefault("initial_native_selector", row["native_selector"])
        row.setdefault("initial_native_missed_failure_ids", row["native_missed_failure_ids"])
        row["native_selector"] = result
        row["native_missed_failure_ids"] = sorted(set(row["mutation"]["expected"]) - failing_ids(result))
        print(f"native refresh {row['index']}/{len(records)} {row['mutation']['name']}: "
              f"misses={len(row['native_missed_failure_ids'])}", flush=True)


def write_reports(records: list[dict], output: Path, report: Path, versions: dict[str, str]) -> None:
    # Exit 5 means no tests collected, never a successful green result.
    for row in records:
        row["raw_false_green"] = bool(row["raw_missed_failure_ids"]) and row["raw_testmon"]["returncode"] == 0
        row["raw_zero_test_exit"] = row["raw_testmon"]["returncode"] == 5
    document = {
        "schema_version": 1, "scope": "synthetic fixtures, not historical PNC changes",
        "adoption_gate_established": False, "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(), "versions": versions,
        "cases_completed": len(records), "records": records,
    }
    output.write_text(json.dumps(document, indent=2), encoding="utf-8")
    raw_misses = sum(bool(row["raw_missed_failure_ids"]) for row in records)
    native_misses = sum(bool(row["native_missed_failure_ids"]) for row in records)
    tool_errors = sum(row["raw_tool_error"] for row in records)
    false_greens = sum(row["raw_false_green"] for row in records)
    zero_test_exits = sum(row["raw_zero_test_exit"] for row in records)
    native_fallbacks = sum(bool(row["native_selector"]["plan"]["fallbacks"]) for row in records)
    lines = [
        "# Synthetic pytest/testmon experiment", "",
        "This is an isolated synthetic fault experiment, not an audit of historical PNC changes. "
        "The adoption gate is **not established**. Whole-PNC parity, historical recall, and meaningful "
        "iteration-time savings require separate evidence.", "",
        f"Completed **{len(records)}** independent mutations. Versions: " + ", ".join(f"{key} {value}" for key, value in versions.items()) + ".", "",
        "Every case starts in a new directory, runs a clean full unittest baseline, seeds testmon "
        "from the same unchanged fixture with `--testmon --testmon-noselect`, verifies identical IDs, "
        "applies one mutation, and checks exact failing IDs with independent full unittest before "
        "running raw affected testmon. Native selection also executes its selected unittest modules. "
        "Every subprocess blocks network auditing events and disables pytest plugin autoload; only "
        "the installed testmon plugin is explicitly loaded. No PNC runtime, account config, or live "
        "fixture is used. No global configuration is changed.", "",
        f"Raw testmon misses: **{raw_misses} cases**; native misses: **{native_misses} cases**; "
        f"raw testmon tool errors: **{tool_errors} cases**. Tool errors are not successful runs.", "",
        f"Of the missed cases, **{false_greens}** returned exit 0; **{zero_test_exits}** returned "
        "pytest exit 5 (no tests collected), which is nonzero and must not be called green.", "",
        f"Native full-fallback decisions: **{native_fallbacks} cases**. The baseline deliberately includes "
        "an unresolved dynamic importer, which makes native selection conservatively broad for most "
        "Python edits. This comparison measures recall, not native selection precision or PNC iteration speed.", "",
        "The mandatory guard independently runs architecture/public-contract checks, plus all synthetic "
        "resource tests for resource mutations. It bypasses testmon filtering. Missing/corrupt state "
        "requires a separate full-run fallback; a guard limited to contracts/resources is not a substitute.", "",
        "| Mutation | Full failures | Raw selected | Raw missed | Native missed | Guarded missed | Raw exit |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in records:
        lines.append(f"| {row['mutation']['name']} | {len(row['mutation']['expected'])} | "
                     f"{len(row['raw_testmon']['executed'])} | {len(row['raw_missed_failure_ids'])} | "
                     f"{len(row['native_missed_failure_ids'])} | {len(row['guarded_missed_failure_ids'])} | "
                     f"{row['raw_testmon']['returncode']} |")
    for category in ("source-as-data", "static-resource", "cache"):
        missed = [row["mutation"]["name"] for row in records
                  if row["mutation"]["category"] == category and row["raw_missed_failure_ids"]]
        if missed:
            lines.extend(["", f"Raw misses in {category}: " + ", ".join(missed) + "."])
    guard_misses = [row["mutation"]["name"] for row in records if row["guarded_missed_failure_ids"]]
    if guard_misses:
        lines.extend(["", "Architecture/public-contract/resource guards alone still miss: " +
                      ", ".join(guard_misses) + ". Setup dependencies need explicit owning-module "
                      "coverage; package initialization and invalid selection state need conservative "
                      "full fallback. Do not adopt raw testmon plus only architecture/resource guards. "
                      "The independent full run is the verified failure oracle for every such case."])
    original_native_misses = [row["mutation"]["name"] for row in records
                              if row.get("initial_native_missed_failure_ids")]
    if original_native_misses:
        lines.extend(["", "Initial native misses preserved in JSON before revalidation: " +
                      ", ".join(original_native_misses) + ". The table reports the latest native recheck; "
                      "the initial native result and original testmon result remain attached to each case."])
    if records:
        medians = {key: statistics.median(row[key]["seconds"] for row in records)
                   for key in ("full_unittest", "raw_testmon", "native_selector")}
        lines.extend(["", "Median subprocess wall times (tiny fixtures, not PNC performance evidence): " +
                      ", ".join(f"{key} {value:.3f}s" for key, value in medians.items()) + ". "
                      "Native timing excludes separately recorded planning time; testmon includes its analysis. "
                      "Baseline seeding and mandatory-guard time are recorded separately in JSON."])
    lines.extend(["", "Machine-readable results: " + str(output.relative_to(REPO_ROOT)).replace("\\", "/"),
                  "", "Rerun from the repository root:", "",
                  "```powershell", ".venv/Scripts/python.exe tools/experiment_test_selection.py", "```", "",
                  "After a native-selector fix, `--refresh-native` rechecks retained candidate sources "
                  "and reruns only native selection, preserving the original testmon evidence.", "",
                  "Each run preserves its case fixtures, baseline/affected XML, unittest JSON, subprocess logs, "
                  "source hashes, seed-cache hashes, exact missed IDs, and native selection reasons under "
                  "`.test-impact/testmon-experiment/`. Synthetic PNG/binary samples are byte-contract fixtures; "
                  "no image decoder, OCR, emulator, or external service is exercised.", ""])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Bounded engineering probe; omit for the full corpus")
    parser.add_argument("--refresh-native", action="store_true", help="Revalidate native fixes against retained candidates")
    arguments = parser.parse_args()
    if arguments.limit is not None and arguments.limit < 1:
        parser.error("--limit must be positive")
    versions = {name: importlib.metadata.version(name) for name in EXPECTED_VERSIONS}
    if versions != EXPECTED_VERSIONS:
        raise ValueError(f"Expected installed experiment versions {EXPECTED_VERSIONS}, got {versions}")
    experiment_root = REPO_ROOT / ".test-impact" / "testmon-experiment"
    output = experiment_root / "results.json"
    report = REPO_ROOT / "reviewed_plans" / "PNC_TESTMON_EXPERIMENT.md"
    files = baseline_files()
    if arguments.refresh_native:
        if arguments.limit is not None:
            parser.error("--limit cannot be combined with --refresh-native")
        records = json.loads(output.read_text(encoding="utf-8"))["records"]
        refresh_native(records, files)
        write_reports(records, output, report, versions)
        return 0
    run_root = experiment_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
    run_root.mkdir(parents=True)
    if arguments.limit is not None:
        # An engineering probe must not replace the completed full-corpus report.
        output = run_root / "results.json"
        report = run_root / "summary.md"
    cases = mutations(files)
    records = []
    for index, mutation in enumerate(cases[:arguments.limit], 1):
        record = execute_case(index, mutation, files, run_root)
        records.append(record)
        write_reports(records, output, report, versions)
        print(f"{index}/{len(cases[:arguments.limit])} {mutation.name}: "
              f"raw misses={len(record['raw_missed_failure_ids'])}, "
              f"native misses={len(record['native_missed_failure_ids'])}, "
              f"raw exit={record['raw_testmon']['returncode']}", flush=True)
    print(f"JSON: {output}\nSummary: {report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
