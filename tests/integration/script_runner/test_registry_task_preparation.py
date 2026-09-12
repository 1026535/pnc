"""Registry task preparation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
from pnc_automation.app.automation.engine.task import (
    CastleTargetPolicy,
    CoreWorkflowTaskDefinition,
    TaskId,
    require_no_params,
)
from pnc_automation.core.errors import ScriptValidationError

from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)


class RegistryTaskPreparationTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves registry task preparation."""

    def test_prepare_script_validates_task_parameters_before_execution(self) -> None:
        """Fails fast with step metadata when task-specific params are invalid."""

        registry = build_default_task_registry()
        script = RunScript(
            name="invalid",
            path=Path("invalid.yaml"),
            steps=(
                ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),
                ScriptStep(task=TaskId.GATHERING, params={"preferred_resources": ["food"], "max_parallel_marches": 0}),
            ),
        )

        with self.assertRaises(ScriptValidationError) as error_context:
            registry.prepare_script(script)

        self.assertEqual(error_context.exception.details["step_index"], 1)
        self.assertEqual(error_context.exception.details["task"], TaskId.GATHERING)

    def test_task_registry_rejects_duplicate_task_ids(self) -> None:
        """Rejects duplicate task ids instead of silently shadowing one task."""

        with self.assertRaises(ValueError):
            definition = CoreWorkflowTaskDefinition(
                id=TaskId.ENSURE_GAME_RUNNING,
                castle_target_policy=CastleTargetPolicy.DISALLOWED,
                parameter_parser=lambda params: require_no_params(TaskId.ENSURE_GAME_RUNNING, params),
            )
            TaskRegistry(tasks=(definition, definition))

    def test_default_task_registry_includes_chat_tasks(self) -> None:
        """Exposes both chat send tasks and the Kingdom Chat monitor through the standard registry."""

        registry = build_default_task_registry()

        self.assertEqual(registry.require(TaskId.SEND_ALLIANCE_CHAT_MESSAGE).id, TaskId.SEND_ALLIANCE_CHAT_MESSAGE)
        self.assertEqual(registry.require(TaskId.SEND_WORLD_CHAT_MESSAGE).id, TaskId.SEND_WORLD_CHAT_MESSAGE)
        self.assertEqual(registry.require(TaskId.COLLECT_KINGDOM_CHAT).id, TaskId.COLLECT_KINGDOM_CHAT)
