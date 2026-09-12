"""Source-level guards for the Phase 3 production ownership boundaries."""

from __future__ import annotations

import ast
import unittest
from importlib.util import resolve_name
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "pnc_automation"


class ProductionOwnershipTests(unittest.TestCase):
    """Checks imports without loading composition or connecting any runtime."""

    def assert_no_imports(self, root: Path, forbidden: tuple[str, ...]) -> None:
        offenders: list[str] = []
        paths = (root,) if root.is_file() else sorted(root.rglob("*.py"))
        self.assertTrue(paths, f"No sources found under {root}")
        for path in paths:
            relative = path.relative_to(REPO_ROOT).with_suffix("")
            package = ".".join(relative.parts[:-1])
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                targets: list[str] = []
                if isinstance(node, ast.Import):
                    targets = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:
                        base = resolve_name("." * node.level + base, package)
                    targets = [base, *(f"{base}.{alias.name}" for alias in node.names)]
                for target in targets:
                    if any(target == prefix or target.startswith(prefix + ".") for prefix in forbidden):
                        offenders.append(f"{relative}:{node.lineno}:{target}")
        self.assertEqual(offenders, [])

    def test_core_has_no_application_imports(self) -> None:
        self.assert_no_imports(PACKAGE_ROOT / "core", ("pnc_automation.app",))

    def test_pnc_has_no_authoring_runtime_or_automation_imports(self) -> None:
        self.assert_no_imports(
            PACKAGE_ROOT / "app/pnc",
            (
                "pnc_automation.app.authoring",
                "pnc_automation.app.runtime",
                "pnc_automation.app.automation",
                "pnc_automation.app.entrypoints",
            ),
        )

    def test_script_authoring_has_no_concrete_tasks_or_composition_imports(self) -> None:
        self.assert_no_imports(
            PACKAGE_ROOT / "app/authoring/scripts",
            ("pnc_automation.app.automation.tasks", "pnc_automation.app.entrypoints"),
        )

    def test_automation_has_no_composition_imports(self) -> None:
        self.assert_no_imports(
            PACKAGE_ROOT / "app/automation",
            ("pnc_automation.app.entrypoints",),
        )

    def test_moved_values_have_one_definition(self) -> None:
        owners = {
            "CastleIdentity": "app/pnc/domain/castles.py",
            "CastleRosterOrdering": "app/pnc/domain/castles.py",
            "PncAccountCastleRosterConfig": "app/pnc/domain/castles.py",
            "castle_identity_key": "app/pnc/domain/castles.py",
            "ObservationMode": "core/vision/observation_policy.py",
            "ObservationArtifactKind": "app/pnc/domain/observation_policy.py",
            "ResolvedObservationArtifactPolicy": "app/pnc/domain/observation_policy.py",
            "build_default_task_registry": "app/entrypoints/task_registry.py",
            "ConnectedClaimOnlyRunnerFactory": "app/entrypoints/daily_maintenance.py",
            "TaskRegistry": "app/authoring/scripts/registry.py",
        }
        found: dict[str, list[str]] = {name: [] for name in owners}
        for path in PACKAGE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in found:
                    found[node.name].append(path.relative_to(PACKAGE_ROOT).as_posix())
        self.assertEqual(found, {name: [owner] for name, owner in owners.items()})

    def test_production_does_not_use_legacy_observation_imports(self) -> None:
        for name in ("observation_mode", "observation_artifacts"):
            with self.subTest(name=name):
                self.assertFalse((PACKAGE_ROOT / "app/runtime" / f"{name}.py").exists())
                self.assert_no_imports(PACKAGE_ROOT, (f"pnc_automation.app.runtime.{name}",))
