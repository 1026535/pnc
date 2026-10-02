"""YOLO prototype live-entry runtime-lifecycle tests."""

from __future__ import annotations

import importlib.util
import logging
import sys
import tempfile
import unittest
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.support.paths import REPOSITORY_ROOT


class PrototypeYoloTests(unittest.TestCase):
    """Checks live capture and report generation share one runtime lifetime."""

    def test_live_capture_and_summary_finish_before_runtime_cleanup(self) -> None:
        """Keeps capture, inference, frame report, and final summary inside the bundle."""

        module = _load_module()
        connected = _FakeConnectedRuntime()
        detector = SimpleNamespace(model_sha256="fake-digest", class_names=("test",))
        shadow = _FakeShadow(connected)
        application = _application(connected)
        previous_threshold = logging.root.manager.disable

        with _preserve_global_logging_threshold() as restored_threshold:
            with tempfile.TemporaryDirectory() as temporary_directory:
                with (
                    patch.object(module, "YoloOnnxDetector", return_value=detector),
                    patch.object(module, "YoloShadowObserver", return_value=shadow),
                    patch.object(module, "load_class_map", return_value={}),
                    patch.object(module, "build_application_runner", return_value=application),
                    patch.object(module, "save_report", side_effect=_report_inside(connected)),
                    patch.object(module, "print"),
                    patch.object(
                        sys,
                        "argv",
                        [
                            "prototype_yolo.py",
                            "--model",
                            "model.onnx",
                            "--live",
                            "--output-dir",
                            temporary_directory,
                        ],
                    ),
                ):
                    self.assertEqual(0, module.main())

        self.assertEqual(previous_threshold, restored_threshold)
        self.assertEqual(previous_threshold, logging.root.manager.disable)
        self.assertEqual(1, connected.enter_calls)
        self.assertEqual(1, connected.exit_calls)
        self.assertFalse(connected.active)
        self.assertEqual(1, shadow.observe_calls)

    def test_live_report_failure_closes_runtime(self) -> None:
        """Releases the live runtime when output materialization fails after capture."""

        module = _load_module()
        connected = _FakeConnectedRuntime()
        detector = SimpleNamespace(model_sha256="fake-digest", class_names=("test",))
        shadow = _FakeShadow(connected)
        application = _application(connected)
        previous_threshold = logging.root.manager.disable

        with _preserve_global_logging_threshold() as restored_threshold:
            with tempfile.TemporaryDirectory() as temporary_directory:
                with (
                    patch.object(module, "YoloOnnxDetector", return_value=detector),
                    patch.object(module, "YoloShadowObserver", return_value=shadow),
                    patch.object(module, "load_class_map", return_value={}),
                    patch.object(module, "build_application_runner", return_value=application),
                    patch.object(module, "save_report", side_effect=_report_inside(connected)),
                    patch.object(
                        Path,
                        "write_text",
                        side_effect=OSError("summary write failed"),
                    ),
                    patch.object(module, "print"),
                    patch.object(
                        sys,
                        "argv",
                        [
                            "prototype_yolo.py",
                            "--model",
                            "model.onnx",
                            "--live",
                            "--output-dir",
                            temporary_directory,
                        ],
                    ),
                ):
                    with self.assertRaisesRegex(OSError, "summary write failed"):
                        module.main()

        self.assertEqual(previous_threshold, restored_threshold)
        self.assertEqual(previous_threshold, logging.root.manager.disable)
        self.assertEqual(1, connected.enter_calls)
        self.assertEqual(1, connected.exit_calls)
        self.assertFalse(connected.active)
        self.assertEqual(OSError, connected.exit_args[0])


class _FakeConnectedRuntime:
    """Tracks whether every fake live operation remains inside the bundle."""

    def __init__(self) -> None:
        self.enter_calls = 0
        self.exit_calls = 0
        self.exit_args: tuple[object, object, object] = (None, None, None)
        self.active = False
        self.runner = object()
        self.runtime = SimpleNamespace(
            observation_service=_FakeObservationService(self),
            session=_FakeSession(self),
        )

    def __enter__(self) -> "_FakeConnectedRuntime":
        self.enter_calls += 1
        self.active = True
        return self

    def __exit__(self, exception_type: object, exception: object, traceback: object) -> None:
        self.exit_calls += 1
        self.exit_args = (exception_type, exception, traceback)
        self.active = False


class _FakeObservationService:
    """Provides one captured frame while asserting the runtime is active."""

    def __init__(self, connected: _FakeConnectedRuntime) -> None:
        """Stores the bundle whose lifetime guards observation."""

        self.connected = connected
        self.castle_roster_store: object | None = object()

    def capture_observation(self, label: str) -> SimpleNamespace:
        """Returns a minimal screenshot/observation pair inside the active bundle."""

        del label
        if not self.connected.active:
            raise AssertionError("Live capture ran outside the connected runtime bundle.")
        return SimpleNamespace(
            screenshot=SimpleNamespace(image=object()),
            observation=object(),
        )


class _FakeSession:
    """Models the session foregrounding operation performed before capture."""

    def __init__(self, connected: _FakeConnectedRuntime) -> None:
        """Stores the bundle whose lifetime guards session use."""

        self.connected = connected

    def ensure_app_foregrounded(self) -> None:
        """Asserts foregrounding happens before runtime cleanup."""

        if not self.connected.active:
            raise AssertionError("Foregrounding ran outside the connected runtime bundle.")


class _FakeShadow:
    """Models one inference request without loading model weights."""

    def __init__(self, connected: _FakeConnectedRuntime) -> None:
        """Stores the bundle used to check inference lifetime."""

        self.connected = connected
        self.observe_calls = 0

    def observe(self, screenshot: object, observation: object) -> object:
        """Records inference only while its connected services remain open."""

        del screenshot, observation
        if not self.connected.active:
            raise AssertionError("YOLO inference ran outside the connected runtime bundle.")
        self.observe_calls += 1
        return object()


def _application(connected: _FakeConnectedRuntime) -> SimpleNamespace:
    """Builds the minimal application facade consumed by the tool."""

    return SimpleNamespace(
        script_runner=SimpleNamespace(
            config=SimpleNamespace(require_account=lambda account_id: account_id),
            build_connected_runtime_bundle=Mock(return_value=connected),
        )
    )


def _report_inside(connected: _FakeConnectedRuntime) -> Callable[..., dict[str, object]]:
    """Returns a fake report writer that rejects calls beyond runtime cleanup."""

    def save_report(*args: object, **kwargs: object) -> dict[str, object]:
        if not connected.active:
            raise AssertionError("YOLO report was materialized outside the connected runtime bundle.")
        return {"frame": "ok"}

    return save_report


@contextmanager
def _preserve_global_logging_threshold() -> Iterator[int]:
    """Restores the process-wide logging disable level after an entry-point test."""

    threshold = logging.root.manager.disable
    try:
        yield threshold
    finally:
        logging.disable(threshold)


def _load_module() -> object:
    """Loads the repository tool by path with its bootstrap module discoverable."""

    tools_directory = REPOSITORY_ROOT / "tools"
    module_path = tools_directory / "prototype_yolo.py"
    sys.path.insert(0, str(tools_directory))
    try:
        spec = importlib.util.spec_from_file_location("test_prototype_yolo_module", module_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load prototype_yolo.py for testing.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
