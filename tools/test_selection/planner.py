"""Compute fail-closed selection without executing application or test code."""

from __future__ import annotations

import ast
from fnmatch import fnmatchcase

from tools.test_selection.models import SelectionPlan, TestModule, module_name
from tools.test_selection.ownership import OwnershipRules, group_matches
from tools.test_selection.python_graph import build_graph


def public_contract(source: str) -> tuple[str, ...]:
    """Fingerprint declarations and import surfaces that need static consumers."""
    tree = ast.parse(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    declarations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            declarations.append(ast.dump(ast.Tuple(elts=[
                ast.Constant(node.name), node.args, *node.decorator_list,
                node.returns or ast.Constant(None), *node.type_params,
            ]), include_attributes=False))
        elif isinstance(node, ast.ClassDef):
            declarations.append(ast.dump(ast.Tuple(elts=[
                ast.Constant(node.name), *node.bases, *node.keywords,
                *node.decorator_list, *node.type_params,
            ]), include_attributes=False))
        elif isinstance(node, (ast.TypeAlias, ast.Import, ast.ImportFrom)):
            declarations.append(ast.dump(node, include_attributes=False))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            ancestor = parents[node]
            while ancestor is not tree and not isinstance(
                    ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                ancestor = parents[ancestor]
            if ancestor is not tree:
                continue
            # Bindings may be aliases, fields, or constants; avoid guessing by name.
            declarations.append(ast.dump(node, include_attributes=False))
    return tuple(declarations)


def _component_owner(path: str) -> str:
    return path.removeprefix("pnc_automation/").rpartition("/")[0].replace("/", ".")


def _owns_component(test: TestModule, owner: str) -> bool:
    return test.component == owner or bool(owner and test.component.startswith(owner + "."))


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
    declaration_changes: set[str] = set()
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
                                declaration_changes.add(path)
                        except SyntaxError:
                            plan.full(tests, f"cannot parse changed source: {path}")
                elif (not path.startswith(("tests/", "tools/"))
                      and not rules.resource_groups(path)):
                    plan.full(tests, f"unknown Python owner: {path}")
    if plan.fallbacks:
        return plan
    # Coverage does not prove dependencies on unexecuted declarations or imports.
    # A mixed diff uses the same static floor throughout; coverage remains additive.
    if declaration_changes:
        coverage_selected_tiers = frozenset()
    changed_python = {module_name(p) for p in changed if p.endswith(".py")}
    graph = build_graph(old, new)
    production_paths = {
        module_name(path): path for path in {*old, *new}
        if path.startswith("pnc_automation/")
    }
    mapped_contracts = graph.consumers(set(production_paths))
    for rule in rules.resources:
        if any(fnmatchcase(path, rule.pattern) for path in production_paths.values()):
            mapped_contracts.update(
                test.module for test in tests if test.tier == "contract"
                and any(group_matches(test, group) for group in rule.groups)
            )
    for test in tests:
        if test.tier == "architecture":
            plan.add(test.module, "mandatory architecture checks")
        elif test.tier == "contract" and test.module not in mapped_contracts:
            plan.add(test.module, "conservative contract check without production ownership")
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
        dependents = graph.consumers({name})
        owner_matches = []
        if path.startswith("pnc_automation/"):
            owner = _component_owner(path)
            consumer_owners = {
                _component_owner(production_paths[module])
                for module in dependents if module in production_paths
            } if path in declaration_changes else set()
            for test in tests:
                if test.tier in coverage_selected_tiers:
                    continue
                if _owns_component(test, owner):
                    owner_matches.append(test)
                    plan.add(test.module, f"component owner: {path}")
                elif any(_owns_component(test, component) for component in consumer_owners):
                    owner_matches.append(test)
                    plan.add(test.module, f"downstream component owner: {path}")
        matches = [
            test for test in tests
            if test.module in dependents
            and test.tier not in coverage_selected_tiers
        ]
        for test in matches:
            plan.add(test.module, f"reverse import dependency: {path}")
        if name in graph.uncertain:
            plan.full(tests, f"unmodeled changed source: {path}")
        if path in declaration_changes:
            for module in {test.module for test in matches + owner_matches}:
                plan.add(module, f"declaration/import surface changed: {path}")
        if not matches and not owner_matches and changed_test is None and not groups:
            plan.full(tests, f"no test dependency established: {path}")
    if not plan.reasons:
        plan.full(tests, "changed files have no established test mapping")
    return plan
