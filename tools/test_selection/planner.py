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
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
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
            ancestor = parents[node]
            while ancestor is not tree and not isinstance(
                    ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                ancestor = parents[ancestor]
            if ancestor is not tree:
                continue
            # Module constants and class fields are part of the public contract.
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and (t.id.isupper() or isinstance(node, ast.AnnAssign)) for t in targets):
                declarations.append(ast.dump(node, include_attributes=False))
    return tuple(declarations)


def affected_plan(
    tests: tuple[TestModule, ...], rules: OwnershipRules, changed: list[str],
    old: dict[str, str], new: dict[str, str], base: str, head: str,
    *,
    coverage_selected_tiers: frozenset[str] = frozenset(),
) -> SelectionPlan:
    plan = SelectionPlan("affected", base, head, changed)
    if not tests:
        raise ValueError("No portable test modules discovered")

    def documentation_only(path: str) -> bool:
        return (path.lower().endswith((".md", ".rst", ".txt"))
                and not rules.resource_groups(path)
                and not any(fnmatchcase(path, rule) for rule in rules.full)
                and any(fnmatchcase(path, rule) for rule in rules.documentation))

    code_change = any(not documentation_only(p) for p in changed)
    if not code_change:
        return plan
    if not old or not new:
        plan.full(tests, "missing source snapshot")
        return plan
    # A known full fallback needs no import graph; parsing both source trees is
    # the expensive part of selection and cannot narrow an already full plan.
    for path in changed:
        if any(fnmatchcase(path, pattern) for pattern in rules.full):
            plan.full(tests, f"shared contract/infrastructure: {path}")
        elif not documentation_only(path):
            if not path.endswith(".py") and not rules.resource_groups(path):
                plan.full(tests, f"unknown non-Python dependency: {path}")
            elif path.endswith(".py"):
                if path not in old and path not in new:
                    plan.full(tests, f"changed Python path missing from snapshots: {path}")
                elif path.startswith("pnc_automation/"):
                    if path not in old or path not in new:
                        plan.full(tests, f"added/deleted production module: {path}")
                    else:
                        try:
                            if public_contract(old[path]) != public_contract(new[path]):
                                plan.full(tests, f"public declaration changed: {path}")
                        except SyntaxError:
                            plan.full(tests, f"cannot parse changed source: {path}")
                elif not path.startswith(("tests/", "tools/")):
                    plan.full(tests, f"unknown Python owner: {path}")
    if plan.fallbacks:
        return plan
    changed_python = {module_name(p) for p in changed if p.endswith(".py")}
    graph = build_graph(old, new)
    for test in tests:
        if test.tier == "architecture" or (
                test.tier == "contract"
                and test.tier not in coverage_selected_tiers):
            plan.add(test.module, "mandatory architecture/public contract checks")
    # Unknown application dynamic loading may connect any two components,
    # including resources consumed through those imports.
    uncertain = sorted(m for m in graph.uncertain if m.startswith("pnc_automation."))
    if uncertain:
        plan.full(tests, "unmodeled application dynamic imports: " + ", ".join(uncertain))
    if changed_python:
        # Dynamic test loaders or supporting tools may consume any changed module.
        # Include them and their callers even when another static consumer exists.
        uncertain_consumers = graph.consumers(graph.uncertain)
        for test in tests:
            if (test.module in uncertain_consumers
                    and test.tier not in coverage_selected_tiers):
                plan.add(test.module, "conservative unresolved dynamic dependency")
    for path in changed:
        if documentation_only(path):
            continue
        groups = rules.resource_groups(path)
        for test in tests:
            if any(group_matches(test, g) for g in groups):
                plan.add(test.module, f"explicit resource ownership: {path}")
        if not path.endswith(".py"):
            continue
        name = module_name(path)
        changed_test = next((test for test in tests if test.path == path), None)
        if changed_test is not None:
            plan.add(changed_test.module, f"changed test module: {path}")
        if path.startswith("pnc_automation/"):
            owner = path.removeprefix("pnc_automation/").rsplit("/", 1)[0].replace("/", ".")
            for test in tests:
                if (test.tier not in coverage_selected_tiers
                        and (test.component == owner
                             or test.component.startswith(owner + "."))):
                    plan.add(test.module, f"component owner: {path}")
        dependents = graph.consumers({name})
        matches = [
            test for test in tests
            if test.module in dependents
            and test.tier not in coverage_selected_tiers
        ]
        for test in matches:
            plan.add(test.module, f"reverse import dependency: {path}")
        if name in graph.uncertain:
            plan.full(tests, f"unmodeled changed source: {path}")
        owner_matches = [
            test for test in tests
            if path.startswith("pnc_automation/")
            and test.tier not in coverage_selected_tiers
            and (test.component == owner or test.component.startswith(owner + "."))
        ] if path.startswith("pnc_automation/") else []
        if not matches and not owner_matches and changed_test is None and not groups:
            plan.full(tests, f"no test dependency established: {path}")
    if not plan.reasons:
        plan.full(tests, "changed files have no established test mapping")
    return plan
