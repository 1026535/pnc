"""Exercise the consultation snapshot's ignored-file detection offline."""

import subprocess
import tempfile
import unittest
from pathlib import Path

import consult_game_knowledge as consult


class SnapshotTests(unittest.TestCase):
    """Verify ignored config edits are detected while volatile runtime dirs stay out of scope."""

    def setUp(self):
        """Build one isolated repository with an ignored config file and runtime dir."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / ".gitignore").write_text("config/*.yaml\n.local-data/\n")
        (self.repo / "config").mkdir()
        subprocess.run(["git", "-C", str(self.repo), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Snapshot test", "-c",
                        "user.email=test@localhost", "commit", "-qm", "Seed snapshot test"], check=True)
        self.run_dir = self.repo / ".local-data" / "devin-game-knowledge" / "run"

    def test_ignored_config_edit_is_detected(self):
        """A consultation mutating ignored local config cannot report an unchanged worktree."""
        secret = self.repo / "config" / "local.yaml"
        secret.write_text("token: first\n")
        before = consult.snapshot(self.repo, self.run_dir)
        secret.write_text("token: changed\n")
        after = consult.snapshot(self.repo, self.run_dir)
        self.assertIn("config/local.yaml", after["ignored"])
        self.assertNotEqual(before, after)

    def test_run_dir_output_is_excluded(self):
        """The launcher's own evidence directory never makes the worktree look changed."""
        before = consult.snapshot(self.repo, self.run_dir)
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "prompt.txt").write_text("prompt\n")
        self.assertEqual(before, consult.snapshot(self.repo, self.run_dir))


if __name__ == "__main__":
    unittest.main()
