"""Conservative Python dependency graph, including package and lazy exports."""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from dataclasses import dataclass

from tools.test_selection.models import module_name


def _known_lazy_calls(tree: ast.Module) -> set[int]:
    """Recognize only the canonical getter's table-derived import argument."""
    accepted = set()
    for function in tree.body:
        if not isinstance(function, ast.FunctionDef) or function.name != "__getattr__":
            continue
        entries, module_variables = set(), set()
        for node in ast.walk(function):
            if not isinstance(node, ast.Assign):
                continue
            if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                    and isinstance(node.value.func.value, ast.Name)
                    and node.value.func.value.id == "_LAZY_EXPORTS" and node.value.func.attr == "get"):
                entries.update(t.id for t in node.targets if isinstance(t, ast.Name))
            if isinstance(node.value, ast.Name) and node.value.id in entries:
                for target in node.targets:
                    if isinstance(target, ast.Tuple) and target.elts and isinstance(target.elts[0], ast.Name):
                        module_variables.add(target.elts[0].id)
        for node in ast.walk(function):
            if (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in module_variables):
                accepted.add(id(node))
    return accepted


@dataclass
class ImportGraph:
    reverse: dict[str, set[str]]
    uncertain: set[str]

    def consumers(self, modules: set[str]) -> set[str]:
        seen = set(modules)
        pending = deque(sorted(modules))
        while pending:
            for consumer in self.reverse.get(pending.popleft(), set()):
                if consumer not in seen:
                    seen.add(consumer)
                    pending.append(consumer)
        return seen


def build_graph(*snapshots: dict[str, str]) -> ImportGraph:
    """Union base and candidate edges, including imports removed in the candidate."""
    reverse: dict[str, set[str]] = defaultdict(set)
    uncertain: set[str] = set()
    for sources in snapshots:
        modules = {module_name(path) for path in sources}
        packages = {module_name(p) for p in sources if p.endswith("/__init__.py")}
        lazy_exports: dict[str, dict[str, str]] = {}
        for path, source in sources.items():
            if "_LAZY_EXPORTS" not in source:
                continue
            try:
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node, (ast.Assign, ast.AnnAssign)):
                        names = node.targets if isinstance(node, ast.Assign) else [node.target]
                        if any(isinstance(n, ast.Name) and n.id == "_LAZY_EXPORTS" for n in names):
                            exports = ast.literal_eval(node.value)
                            if (not isinstance(exports, dict) or any(
                                    not isinstance(key, str) or not isinstance(value, (tuple, list))
                                    or len(value) != 2 or not all(isinstance(v, str) and v for v in value)
                                    for key, value in exports.items())):
                                raise ValueError("Malformed lazy export table")
                            lazy_exports[module_name(path)] = {key: value[0] for key, value in exports.items()}
            except (SyntaxError, ValueError, TypeError, AttributeError, IndexError):
                uncertain.add(module_name(path))
        for path, source in sources.items():
            owner = module_name(path)
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError:
                uncertain.add(owner)
                continue
            package = owner if path.endswith("/__init__.py") else owner.rpartition(".")[0]
            known_lazy_calls = _known_lazy_calls(tree) if owner in lazy_exports else set()
            targets = set()
            aliases: dict[str, str] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    targets.update(alias.name for alias in node.names)
                    for alias in node.names:
                        aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
                elif isinstance(node, ast.ImportFrom):
                    prefix = node.module or ""
                    if node.level:
                        parts = package.split(".")
                        if node.level > len(parts):
                            uncertain.add(owner)
                            continue
                        prefix = ".".join(parts[:len(parts) - node.level + 1] + ([prefix] if prefix else []))
                    targets.add(prefix)
                    targets.update(f"{prefix}.{alias.name}" for alias in node.names)
                    for alias in node.names:
                        exported = lazy_exports.get(prefix, {})
                        if alias.name == "*":
                            targets.update(exported.values())
                        elif alias.name in exported:
                            targets.add(exported[alias.name])
                        aliases[alias.asname or alias.name] = f"{prefix}.{alias.name}"
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    names = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(isinstance(n, ast.Name) and n.id == "_LAZY_EXPORTS" for n in names):
                        try:
                            exports = ast.literal_eval(node.value)
                            # The declaration is not an eager dependency: callers of
                            # a named lazy export own its implementation edge.
                            if not isinstance(exports, dict):
                                uncertain.add(owner)
                        except (ValueError, TypeError, AttributeError, IndexError):
                            uncertain.add(owner)
                elif isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                    name = aliases.get(name, name).rsplit(".", 1)[-1]
                    if name in {"import_module", "__import__"}:
                        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            target = node.args[0].value
                            if target.startswith("."):
                                uncertain.add(owner)
                            else:
                                targets.add(target)
                        elif id(node) not in known_lazy_calls:
                            uncertain.add(owner)
                    elif name in {"exec", "eval", "spec_from_file_location", "run_path", "run_module"}:
                        uncertain.add(owner)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    chain = []
                    value = node
                    while isinstance(value, ast.Attribute):
                        chain.insert(0, value.attr)
                        value = value.value
                    if isinstance(value, ast.Name) and value.id in aliases:
                        qualified = ".".join([aliases[value.id], *chain])
                        package_name, _, attribute = qualified.rpartition(".")
                        target = lazy_exports.get(package_name, {}).get(attribute)
                        if target:
                            targets.add(target)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr" and node.args:
                    value = node.args[0]
                    chain = []
                    while isinstance(value, ast.Attribute):
                        chain.insert(0, value.attr)
                        value = value.value
                    if isinstance(value, ast.Name) and value.id in aliases:
                        qualified = ".".join([aliases[value.id], *chain])
                        targets.update(lazy_exports.get(qualified, {}).values())
            # Importing any submodule executes all its parent packages.
            for i in range(1, len(owner.split("."))):
                parent = ".".join(owner.split(".")[:i])
                if parent in packages:
                    reverse[parent].add(owner)
            for target in targets:
                if target in modules:
                    reverse[target].add(owner)
                # Imported symbol may be an attribute: retain dependency on its module.
                for i in range(1, len(target.split("."))):
                    parent = ".".join(target.split(".")[:i])
                    if parent in packages:
                        reverse[parent].add(owner)
    return ImportGraph(dict(reverse), uncertain)
