"""Fresh-process import checks isolate the pure world-map search planning owners."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

ISOLATION_CHECK = """
    import sys
    forbidden_prefixes = (
        'pnc_automation.app.pnc.navigation.screen_flows',
        'pnc_automation.app.pnc.navigation.spatial_navigation',
        'pnc_automation.app.pnc.navigation.world_map_analysis',
        'pnc_automation.app.pnc.navigation.world_map_survey_recorder',
        'pnc_automation.app.pnc.vision.observation_builder',
        'pnc_automation.app.automation.',
        'pnc_automation.app.runtime.',
        'pnc_automation.app.entrypoints.',
    )
    assert 'pnc_automation.app.pnc.navigation.world_map_search' not in sys.modules
    assert not any(
        name.startswith(forbidden_prefixes)
        for name in sys.modules
    )
"""


class WorldMapSearchPlanningIsolationTests(unittest.TestCase):
    """Imports only; no application or connected runtime is constructed."""

    def run_import_check(self, *modules: str, execute_tests: bool = False) -> None:
        source = "\n".join(f"import {module}" for module in modules) + "\n"
        if execute_tests:
            source += textwrap.dedent(f"""
                import unittest
                suite = unittest.defaultTestLoader.loadTestsFromNames({list(modules)!r})
                assert suite.countTestCases() > 0
                result = unittest.TestResult()
                suite.run(result)
                assert result.wasSuccessful(), result.errors + result.failures
                assert not result.skipped, result.skipped
            """)
        source += textwrap.dedent(ISOLATION_CHECK)
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_search_contracts_import_without_runtime_modules(self) -> None:
        """The contracts owner loads without world-map runtime or live-service composition."""

        self.run_import_check("pnc_automation.app.pnc.navigation.world_map_search_contracts")

    def test_search_planning_import_without_runtime_modules(self) -> None:
        """The planning owner loads without world-map runtime or live-service composition."""

        self.run_import_check("pnc_automation.app.pnc.navigation.world_map_search_planning")

    def test_pure_search_test_cohort_executes_without_runtime_modules(self) -> None:
        """The migrated pure test cohort resolves plans without the runtime facade or fixtures."""

        self.run_import_check(
            "tests.support.pnc.world_search.resolve_search_plan",
            "tests.support.pnc.world_search.search_request",
            "tests.unit.app.pnc.navigation.test_world_search_planning",
            "tests.unit.app.pnc.navigation.test_world_search_plan_rejection",
            "tests.unit.app.pnc.navigation.test_world_search_preview",
            "tests.unit.app.pnc.navigation.test_world_search_route_edges",
            execute_tests=True,
        )
