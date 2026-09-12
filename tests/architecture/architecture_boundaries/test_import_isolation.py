"""Fresh-process import checks preserve public exports and isolate inner layers."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class ImportIsolationTests(unittest.TestCase):
    """Imports only; no application or connected runtime is constructed."""

    def run_import_check(self, source: str) -> None:
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_registry_import_does_not_load_concrete_tasks_or_composition(self) -> None:
        self.run_import_check("""
            import sys
            from pnc_automation.app.authoring.scripts.registry import TaskRegistry
            assert TaskRegistry.__name__ == 'TaskRegistry'
            forbidden = ('pnc_automation.app.entrypoints.', 'pnc_automation.app.automation.tasks.')
            assert not any(name.startswith(forbidden) for name in sys.modules)
        """)

    def test_domain_imports_do_not_load_authoring_or_runtime(self) -> None:
        self.run_import_check("""
            import sys
            import pnc_automation.app.pnc.domain.castles
            import pnc_automation.app.pnc.domain.observation_policy
            forbidden = (
                'pnc_automation.app.authoring.', 'pnc_automation.app.runtime.',
                'pnc_automation.app.entrypoints.', 'pnc_automation.app.automation.',
            )
            assert not any(name.startswith(forbidden) for name in sys.modules)
        """)

    def test_app_public_exports_are_lazy_cached_and_compatible(self) -> None:
        self.run_import_check("""
            import sys
            import pnc_automation.app as app
            assert app.__all__ == ['ApplicationRunner', 'build_application_runner']
            assert set(app.__all__).issubset(dir(app))
            assert 'pnc_automation.app.entrypoints.app' not in sys.modules
            try:
                app.not_a_public_export
            except AttributeError:
                pass
            else:
                raise AssertionError('Unknown exports must fail')
            assert 'pnc_automation.app.entrypoints.app' not in sys.modules
            from pnc_automation.app import ApplicationRunner, build_application_runner
            from pnc_automation.app.entrypoints import app as implementation
            assert ApplicationRunner is implementation.ApplicationRunner
            assert build_application_runner is implementation.build_application_runner
            assert app.__dict__['ApplicationRunner'] is ApplicationRunner
            assert app.__dict__['build_application_runner'] is build_application_runner
            import pnc_automation
            assert pnc_automation.ApplicationRunner is ApplicationRunner
            assert pnc_automation.build_application_runner is build_application_runner
        """)

    def test_default_registry_retains_order_and_canonical_lookup(self) -> None:
        self.run_import_check("""
            from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
            registry = build_default_task_registry()
            expected = (
                'ensure_game_running', 'popup_recovery', 'login', 'select_castle',
                'refresh_castle_roster', 'send_alliance_chat_message',
                'send_world_chat_message', 'send_mail', 'collect_mail',
                'collect_kingdom_chat', 'open_building', 'building_construct',
                'building_upgrade', 'research', 'gathering', 'campaign',
            )
            assert tuple(str(task.id) for task in registry.tasks) == expected
            assert all(registry.require(task.id) is task for task in registry.tasks)
        """)

    def test_legacy_observation_modules_are_unavailable(self) -> None:
        self.run_import_check("""
            from importlib.util import find_spec
            for name in ('observation_mode', 'observation_artifacts'):
                assert find_spec('pnc_automation.app.runtime.' + name) is None
        """)
