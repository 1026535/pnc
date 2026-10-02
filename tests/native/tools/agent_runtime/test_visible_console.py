"""Opt-in proof that a synthetic worker CLI attaches to its visible console."""

import os
from pathlib import Path
import unittest

from tests.support.agent_runtime.imports import agent_script_import_path
from tests.support.agent_runtime.worker_fixture import WorkerFixture

with agent_script_import_path("devin-implement"):
    import devin_worker as worker


@unittest.skipUnless(os.name == "nt", "Visible console attachment requires native Windows.")
@unittest.skipUnless(
    os.environ.get("PNC_RUN_NATIVE_AGENT_CONSOLE_TEST") == "1",
    "Set PNC_RUN_NATIVE_AGENT_CONSOLE_TEST=1 to launch the synthetic visible-console fixture.",
)
class VisibleConsoleAttachmentTests(unittest.TestCase):
    """Verify console attachment and both retained logs with a synthetic CLI."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = WorkerFixture(worker)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def setUp(self) -> None:
        self.args = self.fixture.prepare(self.id())
        self.run_dir = self.fixture.run_dir
        self.args.console = True

    def test_visible_console_preserves_both_logs(self) -> None:
        self.assertEqual(
            self.fixture.invoke("console", through_cli=True, allow_native_console=True), 0,
        )
        turn = Path(self.run_dir) / "turn-001"
        self.assertEqual(
            (turn / "stdout.log").read_text(encoding="utf-8"), "visible stdout: café\n",
        )
        self.assertEqual(
            (turn / "stderr.log").read_text(encoding="utf-8"), "visible stderr: café\n",
        )
        self.assertTrue(worker.read_json(Path(self.run_dir) / "state.json")["writers_stopped"])


if __name__ == "__main__":
    unittest.main()
