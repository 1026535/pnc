"""Route-preview tool tests."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class PreviewWorldMapSearchRouteTests(unittest.TestCase):
    """Validates the live route-preview tool's bounded execution behavior."""

    def test_main_flushes_buffered_diagnostics_when_execution_fails(self) -> None:
        """Flushes shared buffered traversal logs even when the optional execution phase raises."""

        module = _load_preview_tool_module()
        service = _FakeSearchService(raise_on_move=True)
        connected = SimpleNamespace(
            runner=SimpleNamespace(prove_preflight_state=lambda *args, **kwargs: object()),
            runtime=SimpleNamespace(world_map_search_service=service),
        )
        application = SimpleNamespace(
            script_runner=SimpleNamespace(
                config=SimpleNamespace(require_account=lambda account_id: account_id),
                build_connected_runtime_bundle=lambda account: connected,
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

        self.assertEqual(len(service.flush_runtime_states), 1)
        self.assertEqual(service.flush_runtime_states[0], {"buffered": True})


class _FakeSearchService:
    """Provides the narrow preview-tool search-service contract needed by the test."""

    def __init__(self, *, raise_on_move: bool) -> None:
        """Stores whether the fake movement call should fail after touching runtime state."""

        self.raise_on_move = raise_on_move
        self.flush_runtime_states: list[dict[str, object]] = []

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
        runtime_state: dict[str, object],
    ) -> object:
        """Touches the shared runtime state and then raises to exercise the tool's finally block."""

        del observation, plan, step, label_prefix
        runtime_state["buffered"] = True
        if self.raise_on_move:
            raise RuntimeError("preview move failed")
        return object()

    def flush_runtime_diagnostics(self, *, runtime_state: dict[str, object] | None) -> None:
        """Records the shared runtime state the preview tool flushed."""

        assert runtime_state is not None
        self.flush_runtime_states.append(dict(runtime_state))


def _load_preview_tool_module() -> object:
    """Loads the preview tool module from disk with its sibling bootstrap helper on `sys.path`."""

    repo_root = Path(__file__).resolve().parents[1]
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
