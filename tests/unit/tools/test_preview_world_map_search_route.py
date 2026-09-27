"""Route-preview tool tests."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pnc_automation.core.infra.diagnostics.async_diagnostic_writer import AsyncDiagnosticWriterError
from tests.support.paths import REPOSITORY_ROOT


class PreviewWorldMapSearchRouteTests(unittest.TestCase):
    """Validates the live route-preview tool's bounded execution behavior."""

    def test_main_propagates_execution_failure_without_traversal_flush_api(self) -> None:
        """Propagates an optional execution failure without relying on traversal-owned log flushing."""

        module = _load_preview_tool_module()
        service = _FakeSearchService(raise_on_move=True)
        connected = SimpleNamespace(
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

    def test_main_reports_final_sink_failure_instead_of_returning_success(self) -> None:
        """Turns a final-batch logging failure into a failed command result."""

        module = _load_preview_tool_module()
        service = _FakeSearchService(raise_on_move=False)
        connected = SimpleNamespace(
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
