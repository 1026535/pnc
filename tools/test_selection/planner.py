"""Compute fail-closed selection without executing application or test code."""

from __future__ import annotations

import ast
from fnmatch import fnmatchcase

from tools.test_selection.models import SelectionPlan, TestModule, module_name
from tools.test_selection.ownership import OwnershipRules, group_matches
from tools.test_selection.python_graph import build_graph


def public_contract(source: str) -> tuple[str, ...]:
    """Conservatively detect public signatures, constants, decorators, and types."""
    tree = ast.parse(source)
    declarations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                not node.name.startswith("_") or node.name.startswith("__") and node.name.endswith("__")):
            declarations.append(ast.dump(ast.Tuple(elts=[ast.Constant(node.name), node.args, *node.decorator_list, node.returns or ast.Constant(None)]), include_attributes=False))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            declarations.append(ast.dump(ast.Tuple(elts=[ast.Constant(node.name), *node.bases, *node.decorator_list]), include_attributes=False))
        elif isinstance(node, ast.TypeAlias):
            declarations.append(ast.dump(node, include_attributes=False))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            # Include class fields/constants; local assignments are conservative too.
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and (t.id.isupper() or isinstance(node, ast.AnnAssign)) for t in targets):
                declarations.append(ast.dump(node, include_attributes=False))
    return tuple(declarations)


def affected_plan(
    tests: tuple[TestModule, ...], rules: OwnershipRules, changed: list[str],
    old: dict[str, str], new: dict[str, str], base: str, head: str,
) -> SelectionPlan:
    plan = SelectionPlan("affected", base, head, changed)
    if not tests:
        raise ValueError("No portable test modules discovered")
    graph = build_graph(old, new)
    changed_python = {module_name(p) for p in changed if p.endswith(".py")}
    def documentation_only(path: str) -> bool:
        return (path.lower().endswith((".md", ".rst", ".txt"))
                and not rules.resource_groups(path)
                and not any(fnmatchcase(path, rule) for rule in rules.full)
                and any(fnmatchcase(path, rule) for rule in rules.documentation))

    code_change = any(not documentation_only(p) for p in changed)
    if code_change and (not old or not new):
        plan.full(tests, "missing source snapshot")
    if code_change:
        for test in tests:
            if test.tier in {"architecture", "contract"}:
                plan.add(test.module, "mandatory architecture/public contract checks")
    if changed_python:
        # Unknown application dynamic loading may connect any two components.
        uncertain = sorted(m for m in graph.uncertain if m.startswith("pnc_automation."))
        if uncertain:
            plan.full(tests, "unmodeled application dynamic imports: " + ", ".join(uncertain))
        # Dynamic test loaders or supporting tools may consume any changed module.
        # Include them and their callers even when another static consumer exists.
        uncertain_consumers = graph.consumers(graph.uncertain)
        for test in tests:
            if test.module in uncertain_consumers:
                plan.add(test.module, "conservative unresolved dynamic dependency")
    for path in changed:
        if any(fnmatchcase(path, pattern) for pattern in rules.full):
            plan.full(tests, f"shared contract/infrastructure: {path}")
            continue
        if documentation_only(path):
            continue
        groups = rules.resource_groups(path)
        for test in tests:
            if any(group_matches(test, g) for g in groups):
                plan.add(test.module, f"explicit resource ownership: {path}")
        if not path.endswith(".py"):
            if not groups:
                plan.full(tests, f"unknown non-Python dependency: {path}")
            continue
        name = module_name(path)
        if path not in old and path not in new:
            plan.full(tests, f"changed Python path missing from snapshots: {path}")
        if path.startswith("pnc_automation/"):
            if path not in old or path not in new:
                plan.full(tests, f"added/deleted production module: {path}")
            else:
                try:
                    if public_contract(old[path]) != public_contract(new[path]):
                        plan.full(tests, f"public declaration changed: {path}")
                except SyntaxError:
                    plan.full(tests, f"cannot parse changed source: {path}")
            owner = path.removeprefix("pnc_automation/").rsplit("/", 1)[0].replace("/", ".")
            for test in tests:
                if test.component == owner or test.component.startswith(owner + "."):
                    plan.add(test.module, f"component owner: {path}")
        elif not path.startswith(("tests/", "tools/")):
            plan.full(tests, f"unknown Python owner: {path}")
        dependents = graph.consumers({name})
        matches = [test for test in tests if test.module in dependents]
        for test in matches:
            plan.add(test.module, f"reverse import dependency: {path}")
        if name in graph.uncertain:
            plan.full(tests, f"unmodeled changed source: {path}")
        if not matches and not groups:
            plan.full(tests, f"no test dependency established: {path}")
    if changed and code_change and not plan.reasons:
        plan.full(tests, "changed files have no established test mapping")
    return plan
