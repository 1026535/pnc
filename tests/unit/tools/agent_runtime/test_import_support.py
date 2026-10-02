"""Verify packaged agent scripts load through clean, scoped imports."""

import sys
from types import ModuleType
import unittest

from tests.support.agent_runtime.imports import agent_script_import_path


class AgentScriptImportTests(unittest.TestCase):
    def test_import_uses_packaged_script_and_restores_module_and_path_state(self) -> None:
        fake = ModuleType("devin_worker")
        fake.__file__ = "other-test-fixture/devin_worker.py"
        previous = sys.modules.get("devin_worker")
        previous_path = sys.path.copy()
        sys.modules["devin_worker"] = fake
        try:
            with agent_script_import_path("devin-implement") as directory:
                import devin_worker as worker

                self.assertEqual(worker.__file__, str(directory / "devin_worker.py"))
                self.assertIs(sys.modules["devin_worker"], worker)
            self.assertEqual(sys.path, previous_path)
            self.assertIs(sys.modules["devin_worker"], fake)
        finally:
            if previous is None:
                sys.modules.pop("devin_worker", None)
            else:
                sys.modules["devin_worker"] = previous


if __name__ == "__main__":
    unittest.main()
