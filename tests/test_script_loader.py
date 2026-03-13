"""Run-script loader tests."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from pnc_automation.automation.scripts.loader import load_run_script
from pnc_automation.automation.task import TaskId
from pnc_automation.errors import ScriptValidationError


class ScriptLoaderTests(unittest.TestCase):
    """Validates YAML script parsing and task-id handling."""

    def test_load_run_script_parses_steps(self) -> None:
        """Loads a valid automation script into typed steps."""

        with tempfile.TemporaryDirectory() as temp_directory:
            script_path = Path(temp_directory) / "daily.yaml"
            script_path.write_text(
                textwrap.dedent(
                    """
                    name: daily_castle_maintenance
                    steps:
                      - task: login
                      - task: building_upgrade
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


if __name__ == "__main__":
    unittest.main()
