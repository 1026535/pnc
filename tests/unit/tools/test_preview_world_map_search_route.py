"""Route-preview tool tests."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.diagnostics.async_diagnostic_writer import AsyncDiagnosticWriterError
from tests.support.paths import REPOSITORY_ROOT


class PreviewWorldMapSearchRouteTests(unittest.TestCase):
    """Validates the live route-preview tool's bounded execution behavior."""

    def test_main_propagates_execution_failure_without_traversal_flush_api(self) -> None:
        """Propagates an optional execution failure without relying on traversal-owned log flushing."""

        module = _load_preview_tool_module()
        service = _FakeSearchService(raise_on_move=True)
        connected = _FakeConnectedRuntime(
            runner=SimpleNamespace(prove_preflight_state=lambda *args, **kwargs: object()),
            runtime=SimpleNamespace(world_map_search_service=service),
        )
        application = SimpleNamespace(
            script_runner=SimpleNamespace(
                config=SimpleNamespace(require_account=lambda account_id: account_id),
                build_connected_runtime_bundle=lambda account, required_role=None: connected,
            )
        )

        with patch.object(module, "build_application_runner", return_value=application), patch.object(
            sys,
            "argv",
            [
                "preview_world_map_search_route.py",
                "--account",
                "testing",
                "--radius",
                "10",
                "--execute-first",
                "1",
            ],
        ), patch.object(module, "print"):
            with self.assertRaisesRegex(RuntimeError, "preview move failed"):
                module.main()
        self.assertEqual(service.move_calls, 1)
        self.assertEqual(1, connected.enter_calls)
        self.assertEqual(1, connected.exit_calls)
        self.assertEqual(RuntimeError, connected.exit_args[0])

    def test_valid_preview_returns_without_movement_and_closes_runtime(self) -> None:
        """Keeps preview-only behavior inside the acquired runtime lifetime."""

        module = _load_preview_tool_module()
        service = _FakeSearchService(raise_on_move=False)
        connected = _FakeConnectedRuntime(
            runner=SimpleNamespace(prove_preflight_state=lambda *args, **kwargs: object()),
            runtime=SimpleNamespace(world_map_search_service=service),
        )

        with patch.object(module, "build_application_runner", return_value=_application(connected)), patch.object(
            sys,
            "argv",
            ["preview_world_map_search_route.py", "--account", "testing", "--radius", "10"],
        ), patch.object(module, "print") as print_mock:
            self.assertEqual(0, module._run_preview())

        self.assertEqual(0, service.move_calls)
        self.assertEqual(1, connected.enter_calls)
        self.assertEqual(1, connected.exit_calls)
        self.assertEqual(1, print_mock.call_count)
        self.assertIn('"checkpoint_count": 1', print_mock.call_args.args[0])

    def test_preflight_failure_closes_runtime(self) -> None:
        """Releases an acquired runtime when route preflight fails."""

        module = _load_preview_tool_module()
        connected = _FakeConnectedRuntime(
            runner=SimpleNamespace(
                prove_preflight_state=Mock(side_effect=RuntimeError("preflight failed")),
            ),
            runtime=SimpleNamespace(world_map_search_service=_FakeSearchService(raise_on_move=False)),
        )

        with patch.object(module, "build_application_runner", return_value=_application(connected)), patch.object(
            sys,
            "argv",
            ["preview_world_map_search_route.py", "--account", "testing", "--radius", "10"],
        ):
            with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                module._run_preview()

        self.assertEqual(1, connected.enter_calls)
        self.assertEqual(1, connected.exit_calls)
        self.assertEqual(RuntimeError, connected.exit_args[0])

    def test_main_reports_final_sink_failure_instead_of_returning_success(self) -> None:
        """Turns a final-batch logging failure into a failed command result."""

        module = _load_preview_tool_module()
        service = _FakeSearchService(raise_on_move=False)
        connected = _FakeConnectedRuntime(
            runner=SimpleNamespace(prove_preflight_state=lambda *args, **kwargs: object()),
            runtime=SimpleNamespace(world_map_search_service=service),
        )
        application = SimpleNamespace(
            script_runner=SimpleNamespace(
                config=SimpleNamespace(require_account=lambda account_id: account_id),
                build_connected_runtime_bundle=lambda account, required_role=None: connected,
            )
        )

        with patch.object(module, "build_application_runner", return_value=application), patch.object(
            sys,
            "argv",
            ["preview_world_map_search_route.py", "--account", "testing", "--radius", "10"],
        ), patch.object(module, "print"), patch(
            "pnc_automation.core.infra.diagnostics.logging_setup.shutdown_logging",
            side_effect=AsyncDiagnosticWriterError("final sink failure"),
        ):
            with self.assertRaisesRegex(AsyncDiagnosticWriterError, "final sink failure"):
                module.main()
        self.assertEqual(1, connected.exit_calls)

    def test_invalid_request_is_rejected_before_application_construction(self) -> None:
        """Rejects malformed route arguments before config loading or runtime acquisition."""

        for arguments in (
            ["--account", "testing", "--origin", "explicit_coordinate", "--radius", "10"],
            [
                "--account",
                "testing",
                "--origin",
                "explicit_coordinate",
                "--origin-x",
                "512",
                "--origin-y",
                "100",
                "--radius",
                "10",
            ],
            ["--account", "testing", "--min-x", "1"],
            ["--account", "testing", "--radius", "10", "--head", "0"],
            ["--account", "testing", "--radius", "10", "--tail", "-1"],
        ):
            with self.subTest(arguments=arguments):
                module = _load_preview_tool_module()
                application_factory = Mock()
                with patch.object(module, "build_application_runner", application_factory), patch.object(
                    sys,
                    "argv",
                    ["preview_world_map_search_route.py", *arguments],
                ):
                    with self.assertRaises(SelectorResolutionError):
                        module._run_preview()
                application_factory.assert_not_called()


class _FakeSearchService:
    """Provides the narrow preview-tool search-service contract needed by the test."""

    def __init__(self, *, raise_on_move: bool) -> None:
        """Stores whether the fake movement call should fail after touching runtime state."""

        self.raise_on_move = raise_on_move
        self.move_calls = 0

    def preview_route(self, request: object, observation: object, *, head: int, tail: int) -> dict[str, object]:
        """Returns one minimal preview document without depending on the real planner."""

        del request, observation, head, tail
        return {"checkpoint_count": 1}

    def resolve_plan(self, request: object, observation: object) -> object:
        """Returns one minimal plan carrying a single executable step."""

        del request, observation
        return SimpleNamespace(
            execution_plan=SimpleNamespace(
                steps=(
                    SimpleNamespace(
                        step_index=0,
                        checkpoint=SimpleNamespace(coordinate=(10, 0)),
                        traversal_segment_intent=SimpleNamespace(value="local_traverse"),
                    ),
                )
            )
        )

    def move_to_checkpoint(
        self,
        observation: object,
        *,
        plan: object,
        step: object,
        label_prefix: str,
    ) -> object:
        """Records the movement call and optionally raises to exercise failure propagation."""

        del observation, plan, step, label_prefix
        self.move_calls += 1
        if self.raise_on_move:
            raise RuntimeError("preview move failed")
        return object()


class _FakeConnectedRuntime:
    """Models the canonical bundle context and records its one cleanup boundary."""

    def __init__(self, *, runner: object, runtime: object) -> None:
        """Store the shared objects used inside the context."""

        self.runner = runner
        self.runtime = runtime
        self.enter_calls = 0
        self.exit_calls = 0
        self.exit_args: tuple[object, object, object] | None = None

    def __enter__(self) -> "_FakeConnectedRuntime":
        """Enter the connected runtime exactly once."""

        self.enter_calls += 1
        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        """Record cleanup while allowing the active exception to propagate."""

        self.exit_calls += 1
        self.exit_args = (_exception_type, _exception, _traceback)


def _application(connected: _FakeConnectedRuntime) -> SimpleNamespace:
    """Builds the small application surface used by the route-preview entry point."""

    return SimpleNamespace(
        script_runner=SimpleNamespace(
            config=SimpleNamespace(require_account=lambda account_id: account_id),
            build_connected_runtime_bundle=lambda account, required_role=None: connected,
        )
    )


def _load_preview_tool_module() -> object:
    """Loads the preview tool module from disk with its sibling bootstrap helper on `sys.path`."""

    repo_root = REPOSITORY_ROOT
    tools_directory = repo_root / "tools"
    module_path = tools_directory / "preview_world_map_search_route.py"
    sys.path.insert(0, str(tools_directory))
    try:
        spec = importlib.util.spec_from_file_location("test_preview_world_map_search_route_module", module_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load preview_world_map_search_route.py for testing.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
