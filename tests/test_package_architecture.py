"""Architecture invariants for the canonical package layout."""

from __future__ import annotations

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


def _find_import_violations(*, root: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    """Returns every import line under one package root that targets a forbidden prefix."""

    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith(("from ", "import ")):
                continue
            if not any(prefix in stripped for prefix in forbidden_prefixes):
                continue
            violations.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{stripped}")
    return violations


if __name__ == "__main__":
    unittest.main()
