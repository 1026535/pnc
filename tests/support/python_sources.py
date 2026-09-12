"""Shared parsed Python-source snapshots for repository architecture tests."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from tests.support.paths import REPOSITORY_ROOT


PACKAGE_ROOT = REPOSITORY_ROOT / "pnc_automation"


@dataclass(frozen=True, slots=True)
class ParsedPythonSource:
    """One parsed source file and the package context needed for import resolution."""

    path: Path
    relative_path: Path
    current_package: str
    tree: ast.AST


@lru_cache(maxsize=1)
def repository_python_sources() -> tuple[ParsedPythonSource, ...]:
    """Returns the process-local immutable snapshot of production Python sources."""

    return tuple(
        parse_python_source(
            path=path,
            repo_root=REPOSITORY_ROOT,
            package_root=PACKAGE_ROOT,
        )
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
    )


def repository_python_sources_under(root: Path) -> tuple[ParsedPythonSource, ...]:
    """Returns cached repository sources below one production package path."""

    resolved_root = root.resolve()
    return tuple(
        source
        for source in repository_python_sources()
        if source.path == resolved_root or resolved_root in source.path.parents
    )


def parse_python_source(*, path: Path, repo_root: Path, package_root: Path) -> ParsedPythonSource:
    """Parses one source directly; callers use this for isolated synthetic files."""

    resolved_path = path.resolve()
    resolved_repo_root = repo_root.resolve()
    resolved_package_root = package_root.resolve()
    relative_path = resolved_path.relative_to(resolved_repo_root)
    module_name = _module_name_for_path(path=resolved_path, package_root=resolved_package_root)
    current_package = module_name if resolved_path.stem == "__init__" else module_name.rpartition(".")[0]
    return ParsedPythonSource(
        path=resolved_path,
        relative_path=relative_path,
        current_package=current_package,
        tree=ast.parse(resolved_path.read_text(encoding="utf-8"), filename=str(resolved_path)),
    )


def iter_import_targets(source: ParsedPythonSource) -> tuple[tuple[int, str], ...]:
    """Returns semantically resolved import targets from one parsed source."""

    targets: list[tuple[int, str]] = []
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Import):
            targets.extend((node.lineno, alias.name) for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom):
            base_target = _resolve_import_base(
                module=node.module,
                level=node.level,
                current_package=source.current_package,
            )
            if base_target is None:
                continue
            targets.append((node.lineno, base_target))
            targets.extend(
                (node.lineno, f"{base_target}.{alias.name}")
                for alias in node.names
                if alias.name != "*"
            )
    return tuple(targets)


def _module_name_for_path(*, path: Path, package_root: Path) -> str:
    """Returns the fully qualified module name for one package source."""

    relative_path = path.relative_to(package_root).with_suffix("")
    parts = relative_path.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join((package_root.name, *parts))


def _resolve_import_base(*, module: str | None, level: int, current_package: str) -> str | None:
    """Resolves the absolute base module for one import-from statement."""

    if level == 0:
        return module
    package_parts = current_package.split(".")
    parent_depth = level - 1
    if parent_depth > len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - parent_depth]
    if module is not None:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)
