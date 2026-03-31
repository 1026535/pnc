"""Architecture invariants for the canonical package layout."""

from __future__ import annotations

import ast
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "pnc_automation"


class PackageArchitectureTests(unittest.TestCase):
    """Enforces the package ownership boundaries defined by the architecture plan."""

    def test_core_does_not_import_app(self) -> None:
        """Keeps reusable core modules free from application-layer dependencies."""

        offenders = _find_import_violations(
            root=PACKAGE_ROOT / "core",
            forbidden_prefixes=("pnc_automation.app.",),
        )
        self.assertEqual(offenders, [])

    def test_core_vision_does_not_import_pnc_application_types(self) -> None:
        """Keeps generic vision helpers free from P&C-specific meaning."""

        offenders = _find_import_violations(
            root=PACKAGE_ROOT / "core" / "vision",
            forbidden_prefixes=("pnc_automation.app.pnc.",),
        )
        self.assertEqual(offenders, [])

    def test_pnc_layer_does_not_import_automation_layer(self) -> None:
        """Keeps P&C meaning independent from automation orchestration code."""

        offenders = _find_import_violations(
            root=PACKAGE_ROOT / "app" / "pnc",
            forbidden_prefixes=("pnc_automation.app.automation.",),
        )
        self.assertEqual(offenders, [])

    def test_legacy_top_level_packages_are_removed(self) -> None:
        """Removes the obsolete pre-refactor package roots instead of keeping wrappers alive."""

        legacy_paths = (
            PACKAGE_ROOT / "adb",
            PACKAGE_ROOT / "automation",
            PACKAGE_ROOT / "capture",
            PACKAGE_ROOT / "config",
            PACKAGE_ROOT / "diagnostics",
            PACKAGE_ROOT / "emulator",
            PACKAGE_ROOT / "pnc",
            PACKAGE_ROOT / "scripts",
            PACKAGE_ROOT / "vision",
        )
        existing = [path.name for path in legacy_paths if path.exists()]
        self.assertEqual(existing, [])

    def test_import_checker_rejects_absolute_forbidden_imports(self) -> None:
        """Flags forbidden absolute imports instead of relying on fragile text matching."""

        offenders = _find_import_violations_for_source(
            relative_path=Path("pnc_automation/core/example.py"),
            source="import pnc_automation.app.pnc.domain.observation\n",
            forbidden_prefixes=("pnc_automation.app.",),
        )
        self.assertEqual(offenders, ["pnc_automation/core/example.py:1:pnc_automation.app.pnc.domain.observation"])

    def test_import_checker_rejects_relative_forbidden_imports(self) -> None:
        """Flags forbidden relative imports after resolving them against the current module path."""

        offenders = _find_import_violations_for_source(
            relative_path=Path("pnc_automation/core/example.py"),
            source="from ..app.pnc.domain import observation\n",
            forbidden_prefixes=("pnc_automation.app.",),
        )
        self.assertEqual(
            offenders,
            [
                "pnc_automation/core/example.py:1:pnc_automation.app.pnc.domain",
                "pnc_automation/core/example.py:1:pnc_automation.app.pnc.domain.observation",
            ],
        )


def _find_import_violations(
    *,
    root: Path,
    forbidden_prefixes: tuple[str, ...],
    package_root: Path = PACKAGE_ROOT,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    """Returns every semantic import under one package root that targets a forbidden prefix."""

    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        violations.extend(
            _find_import_violations_in_file(
                path=path,
                forbidden_prefixes=forbidden_prefixes,
                package_root=package_root,
                repo_root=repo_root,
            )
        )
    return violations


def _find_import_violations_for_source(
    *,
    relative_path: Path,
    source: str,
    forbidden_prefixes: tuple[str, ...],
) -> list[str]:
    """Runs the semantic import checker against one synthetic module source."""

    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temp_directory:
        temp_root = Path(temp_directory)
        path = temp_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return _find_import_violations(
            root=path.parent,
            forbidden_prefixes=forbidden_prefixes,
            package_root=temp_root / "pnc_automation",
            repo_root=temp_root,
        )


def _find_import_violations_in_file(
    *,
    path: Path,
    forbidden_prefixes: tuple[str, ...],
    package_root: Path,
    repo_root: Path,
) -> list[str]:
    """Returns every forbidden import target resolved from one module file."""

    module_name = _module_name_for_path(path=path, package_root=package_root)
    current_package = _package_name_for_module(module_name=module_name, path=path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for line_number, target in _iter_import_targets(tree=tree, current_package=current_package):
        if _is_forbidden_import(target, forbidden_prefixes):
            relative_path = path.relative_to(repo_root).as_posix()
            violations.append(f"{relative_path}:{line_number}:{target}")
    return violations


def _module_name_for_path(*, path: Path, package_root: Path) -> str:
    """Returns the fully qualified module name for one Python file under the package root."""

    relative_path = path.relative_to(package_root).with_suffix("")
    parts = relative_path.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join((package_root.name, *parts))


def _package_name_for_module(*, module_name: str, path: Path) -> str:
    """Returns the package name used to resolve relative imports for one module."""

    if path.stem == "__init__":
        return module_name
    module_parts = module_name.split(".")
    return ".".join(module_parts[:-1])


def _iter_import_targets(*, tree: ast.AST, current_package: str) -> list[tuple[int, str]]:
    """Returns every semantically resolved import target referenced by one module AST."""

    targets: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend((node.lineno, alias.name) for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom):
            targets.extend(
                (node.lineno, target)
                for target in _resolve_import_from_targets(node=node, current_package=current_package)
            )
    return targets


def _resolve_import_from_targets(*, node: ast.ImportFrom, current_package: str) -> tuple[str, ...]:
    """Resolves one `from ... import ...` node into absolute module targets."""

    base_target = _resolve_import_base(module=node.module, level=node.level, current_package=current_package)
    if base_target is None:
        return ()
    targets = [base_target]
    for alias in node.names:
        if alias.name == "*":
            continue
        targets.append(f"{base_target}.{alias.name}")
    return tuple(targets)


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


def _is_forbidden_import(target: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    """Returns whether one absolute import target violates the requested boundary prefixes."""

    return any(_matches_forbidden_prefix(target=target, forbidden_prefix=prefix) for prefix in forbidden_prefixes)


def _matches_forbidden_prefix(*, target: str, forbidden_prefix: str) -> bool:
    """Returns whether one target equals or sits beneath one forbidden package prefix."""

    normalized_prefix = forbidden_prefix.rstrip(".")
    return target == normalized_prefix or target.startswith(f"{normalized_prefix}.")


if __name__ == "__main__":
    unittest.main()
