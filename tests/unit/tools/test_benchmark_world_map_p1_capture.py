"""Offline lifetime tests for the world-map P1 capture benchmark."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from types import SimpleNamespace

from tests.support.paths import REPOSITORY_ROOT


class BenchmarkWorldMapP1CaptureTests(unittest.TestCase):
    """Proves benchmark measurement and cleanup stay inside the connected lease."""

    def test_measurement_runs_before_runtime_cleanup(self) -> None:
        module = _load_benchmark_module()
        state = SimpleNamespace(entered=False, exited=False)

        class ConnectedRuntime:
            def __enter__(self) -> object:
                state.entered = True
                return self

            def __exit__(self, _type: object, _error: object, _traceback: object) -> None:
                state.exited = True

        report = module._with_connected_runtime(
            ConnectedRuntime(),
            lambda connected: {"measured_inside": state.entered and not state.exited},
        )

        self.assertEqual({"measured_inside": True}, report)
        self.assertTrue(state.exited)

    def test_runtime_cleanup_runs_when_measurement_fails(self) -> None:
        module = _load_benchmark_module()
        state = SimpleNamespace(exited=False)

        class ConnectedRuntime:
            def __enter__(self) -> object:
                return self

            def __exit__(self, _type: object, _error: object, _traceback: object) -> None:
                state.exited = True

        with self.assertRaisesRegex(RuntimeError, "benchmark failure"):
            module._with_connected_runtime(
                ConnectedRuntime(),
                lambda _connected: (_ for _ in ()).throw(RuntimeError("benchmark failure")),
            )

        self.assertTrue(state.exited)


def _load_benchmark_module() -> object:
    """Loads the standalone benchmark and its repository bootstrap for unit coverage."""

    tools_directory = REPOSITORY_ROOT / "tools"
    sys.path.insert(0, str(tools_directory))
    try:
        module_path = tools_directory / "benchmark_world_map_p1_capture.py"
        module_name = "test_benchmark_world_map_p1_capture_module"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load benchmark_world_map_p1_capture.py for testing.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)
        return module
    finally:
        sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
