"""Run-script loader tests."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from pnc_automation.app.authoring.scripts.loader import load_run_script
from pnc_automation.app.authoring.scripts.models import CastleRefRepeatBlock, ScriptStep
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.core.errors import ScriptValidationError


class ScriptLoaderTests(unittest.TestCase):
    """Validates YAML script parsing and task-id handling."""

    def test_load_run_script_parses_steps(self) -> None:
        """Loads a valid automation script into typed steps and castle references."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "daily.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: daily_castle_maintenance
                    steps:
                      - task: login
                      - task: building_upgrade
                        castle_ref: main
                        params:
                          priority: [castle, wall]
                          allow_speedups: false
                      - task: gathering
                        params:
                          preferred_resources: [food, wood]
                          max_parallel_marches: 2
                      - task: send_alliance_chat_message
                        params:
                          message: bot shall invade
                    """
                ).strip(),
                encoding="utf-8",
            )

            script = load_run_script(script_path)

            self.assertEqual(script.name, "daily_castle_maintenance")
            self.assertEqual(script.steps[0].task, TaskId.LOGIN)
            self.assertEqual(script.steps[1].castle_ref, "main")
            self.assertIsNone(script.steps[1].castle)
            self.assertEqual(script.steps[1].params["priority"], ["castle", "wall"])
            self.assertEqual(script.steps[3].task, TaskId.SEND_ALLIANCE_CHAT_MESSAGE)
            self.assertEqual(script.steps[3].params["message"], "bot shall invade")

    def test_load_run_script_rejects_unknown_tasks(self) -> None:
        """Fails fast when the script references an unsupported task id."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "invalid.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: invalid
                    steps:
                      - task: unknown_task
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ScriptValidationError):
                load_run_script(script_path)

    def test_load_run_script_rejects_inline_castle_targets(self) -> None:
        """Fails fast when a run script still uses the removed inline castle schema."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "invalid.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: invalid
                    steps:
                      - task: building_upgrade
                        castle:
                          kingdom: K230
                          castle_name: Main
                        params:
                          priority: [castle]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ScriptValidationError):
                load_run_script(script_path)

    def test_load_run_script_rejects_unexpected_root_keys(self) -> None:
        """Fails fast when the script root includes unsupported schema keys."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "invalid.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: invalid
                    unexpected_root: true
                    steps:
                      - task: login
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ScriptValidationError) as error_context:
                load_run_script(script_path)

        self.assertEqual(error_context.exception.details["extra_keys"], ["unexpected_root"])

    def test_load_run_script_rejects_unexpected_task_step_keys(self) -> None:
        """Fails fast when an ordinary task step includes unsupported schema keys."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "invalid.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: invalid
                    steps:
                      - task: login
                        unexpected: true
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ScriptValidationError) as error_context:
                load_run_script(script_path)

        self.assertEqual(error_context.exception.details["step_path"], "steps[0]")
        self.assertEqual(error_context.exception.details["extra_keys"], ["unexpected"])

    def test_load_run_script_rejects_unexpected_repeat_block_keys(self) -> None:
        """Fails fast when a repeat block includes unsupported schema keys."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "invalid.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: invalid
                    steps:
                      - castle_refs: [main]
                        unexpected: true
                        steps:
                          - task: building_upgrade
                            params:
                              priority: [castle]
                              allow_speedups: false
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ScriptValidationError) as error_context:
                load_run_script(script_path)

        self.assertEqual(error_context.exception.details["step_path"], "steps[0]")
        self.assertEqual(error_context.exception.details["extra_keys"], ["unexpected"])

    def test_load_run_script_parses_collect_kingdom_chat_routine(self) -> None:
        """Loads the heartbeat routine shape used for scheduler-driven Kingdom Chat polling."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "kingdom_chat_heartbeat.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: kingdom_chat_heartbeat
                    steps:
                      - task: ensure_game_running
                      - task: login
                      - task: collect_kingdom_chat
                        castle_ref: main
                    """
                ).strip(),
                encoding="utf-8",
            )

            script = load_run_script(script_path)

            self.assertEqual(script.steps[2].task, TaskId.COLLECT_KINGDOM_CHAT)
            self.assertEqual(script.steps[2].castle_ref, "main")

    def test_load_run_script_parses_multi_castle_repeat_block(self) -> None:
        """Loads one repeat block into an explicit authored node with nested ordinary task steps."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "multi_castle.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: daily_castle_maintenance
                    steps:
                      - task: ensure_game_running
                      - castle_refs: [main, farm]
                        steps:
                          - task: building_upgrade
                            params:
                              priority: [castle, wall]
                              allow_speedups: false
                          - task: research
                            params:
                              priority: [economy, development]
                    """
                ).strip(),
                encoding="utf-8",
            )

            script = load_run_script(script_path)

            self.assertEqual(len(script.steps), 2)
            self.assertIsInstance(script.steps[0], ScriptStep)
            self.assertIsInstance(script.steps[1], CastleRefRepeatBlock)
            repeat_block = script.steps[1]
            assert isinstance(repeat_block, CastleRefRepeatBlock)
            self.assertEqual(repeat_block.castle_refs, ("main", "farm"))
            self.assertEqual([step.task for step in repeat_block.steps], [TaskId.BUILDING_UPGRADE, TaskId.RESEARCH])

    def test_load_run_script_rejects_repeat_block_that_mixes_task_and_castle_refs(self) -> None:
        """Fails fast when one authored node tries to be both a task step and a repeat block."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "invalid.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: invalid
                    steps:
                      - task: building_upgrade
                        castle_refs: [main]
                        steps:
                          - task: research
                            params:
                              priority: [economy]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ScriptValidationError) as error_context:
                load_run_script(script_path)

        self.assertEqual(error_context.exception.details["step_path"], "steps[0]")

    def test_load_run_script_rejects_repeat_block_with_empty_castle_refs(self) -> None:
        """Fails fast when a repeat block does not declare any target aliases."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "invalid.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: invalid
                    steps:
                      - castle_refs: []
                        steps:
                          - task: building_upgrade
                            params:
                              priority: [castle]
                              allow_speedups: false
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ScriptValidationError):
                load_run_script(script_path)

    def test_load_run_script_rejects_repeat_block_with_empty_steps(self) -> None:
        """Fails fast when a repeat block omits its nested workflow body."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "invalid.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: invalid
                    steps:
                      - castle_refs: [main]
                        steps: []
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ScriptValidationError):
                load_run_script(script_path)

    def test_load_run_script_rejects_nested_repeat_step_castle_ref_override(self) -> None:
        """Fails fast when a repeat block's nested task step tries to declare its own castle alias."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "invalid.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: invalid
                    steps:
                      - castle_refs: [main]
                        steps:
                          - task: building_upgrade
                            castle_ref: farm
                            params:
                              priority: [castle]
                              allow_speedups: false
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ScriptValidationError) as error_context:
                load_run_script(script_path)

        self.assertEqual(error_context.exception.details["step_path"], "steps[0].steps[0]")


if __name__ == "__main__":
    unittest.main()

