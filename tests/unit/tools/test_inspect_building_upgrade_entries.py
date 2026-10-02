"""Building inspection tool runtime-lifecycle tests."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.support.paths import REPOSITORY_ROOT


class InspectBuildingUpgradeEntriesTests(unittest.TestCase):
    """Checks the building inspection entry point scopes its workflow to the runtime bundle."""

    def test_successful_report_is_materialized_before_runtime_cleanup(self) -> None:
        """Keeps preflight and the emitted report inside the acquired bundle."""

        module = _load_module()
        connected = _FakeConnectedRuntime()
        application = _application(connected)
        runner = SimpleNamespace(
            flow_planner=SimpleNamespace(
                ensure_home_city=Mock(),
                home_city_navigator=SimpleNamespace(focus_step_budget=Mock(return_value=0)),
            )
        )
        connected.runner = runner

        def complete_preflight(**kwargs: object) -> object:
            self.assertTrue(connected.active)
            return object()

        def emit_report(*args: object, **kwargs: object) -> None:
            self.assertTrue(connected.active)

        with (
            patch.object(module, "build_application_runner", return_value=application),
            patch.object(module, "execute_live_flow_until", side_effect=complete_preflight),
            patch.object(module, "print", side_effect=emit_report),
            patch.object(
                sys,
                "argv",
                [
                    "inspect_building_upgrade_entries.py",
                    "--targets",
                    "",
                    "--targeted-only",
                ],
            ),
        ):
            self.assertEqual(0, module.main())

        self.assertEqual(1, connected.enter_calls)
        self.assertEqual(1, connected.exit_calls)
        self.assertFalse(connected.active)

    def test_preflight_failure_closes_runtime(self) -> None:
        """Releases the bundle when the first live survey step fails."""

        module = _load_module()
        connected = _FakeConnectedRuntime()
        application = _application(connected)
        connected.runner = SimpleNamespace(flow_planner=SimpleNamespace(ensure_home_city=Mock()))

        with (
            patch.object(module, "build_application_runner", return_value=application),
            patch.object(
                module,
                "execute_live_flow_until",
                side_effect=RuntimeError("building preflight failed"),
            ),
            patch.object(
                sys,
                "argv",
                ["inspect_building_upgrade_entries.py", "--targets", "", "--targeted-only"],
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "building preflight failed"):
                module.main()

        self.assertEqual(1, connected.enter_calls)
        self.assertEqual(1, connected.exit_calls)
        self.assertEqual(RuntimeError, connected.exit_args[0])
        self.assertFalse(connected.active)


class _FakeConnectedRuntime:
    """Tracks one canonical context boundary around the connected runner."""

    runner: object

    def __init__(self) -> None:
        self.enter_calls = 0
        self.exit_calls = 0
        self.exit_args: tuple[object, object, object] | None = None
        self.active = False

    def __enter__(self) -> "_FakeConnectedRuntime":
        self.enter_calls += 1
        self.active = True
        return self

    def __exit__(self, exception_type: object, exception: object, traceback: object) -> None:
        self.exit_calls += 1
        self.exit_args = (exception_type, exception, traceback)
        self.active = False


def _application(connected: _FakeConnectedRuntime) -> SimpleNamespace:
    """Builds the minimal application facade consumed by the tool."""

    return SimpleNamespace(
        script_runner=SimpleNamespace(
            config=SimpleNamespace(require_account=lambda account_id: account_id),
            build_connected_runtime_bundle=Mock(return_value=connected),
        )
    )


def _load_module() -> object:
    """Loads the repository tool by path with its bootstrap module discoverable."""

    tools_directory = REPOSITORY_ROOT / "tools"
    module_path = tools_directory / "inspect_building_upgrade_entries.py"
    sys.path.insert(0, str(tools_directory))
    try:
        spec = importlib.util.spec_from_file_location("test_inspect_building_upgrade_entries_module", module_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load inspect_building_upgrade_entries.py for testing.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
