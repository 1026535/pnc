"""Architecture invariants for the canonical package layout."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.support.paths import REPOSITORY_ROOT
from tests.support.python_sources import (
    ParsedPythonSource,
    iter_import_targets,
    parse_python_source,
    repository_python_sources_under,
)


REPO_ROOT = REPOSITORY_ROOT
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

    def test_host_management_import_does_not_eagerly_load_application(self) -> None:
        """Keeps a fresh host-management import free from OCR and application entrypoint imports."""

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import pnc_automation.bluestacks_management.__main__; "
                    "assert not any(name == 'pnc_automation.app' or name.startswith('pnc_automation.app.') "
                    "for name in sys.modules), sorted(name for name in sys.modules if name.startswith('pnc_automation.app'))"
                ),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_top_level_application_exports_remain_lazy_and_compatible(self) -> None:
        """Preserves the public from-import contract while deferring application loading."""

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import pnc_automation; "
                    "assert not any(name.startswith('pnc_automation.app') for name in sys.modules); "
                    "from pnc_automation import AutomationApi; "
                    "assert AutomationApi.__name__ == 'AutomationApi'"
                ),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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

    if package_root.resolve() == PACKAGE_ROOT and repo_root.resolve() == REPO_ROOT:
        sources = repository_python_sources_under(root)
    else:
        paths = (root,) if root.is_file() else sorted(root.rglob("*.py"))
        sources = tuple(
            parse_python_source(path=path, package_root=package_root, repo_root=repo_root)
            for path in paths
        )
    return [
        violation
        for source in sources
        for violation in _find_import_violations_in_file(
            source=source,
            forbidden_prefixes=forbidden_prefixes,
        )
    ]


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
    source: ParsedPythonSource,
    forbidden_prefixes: tuple[str, ...],
) -> list[str]:
    """Returns every forbidden import target resolved from one module file."""

    violations: list[str] = []
    for line_number, target in iter_import_targets(source):
        if _is_forbidden_import(target, forbidden_prefixes):
            violations.append(f"{source.relative_path.as_posix()}:{line_number}:{target}")
    return violations


def _is_forbidden_import(target: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    """Returns whether one absolute import target violates the requested boundary prefixes."""

    return any(_matches_forbidden_prefix(target=target, forbidden_prefix=prefix) for prefix in forbidden_prefixes)


def _matches_forbidden_prefix(*, target: str, forbidden_prefix: str) -> bool:
    """Returns whether one target equals or sits beneath one forbidden package prefix."""

    normalized_prefix = forbidden_prefix.rstrip(".")
    return target == normalized_prefix or target.startswith(f"{normalized_prefix}.")


if __name__ == "__main__":
    unittest.main()
