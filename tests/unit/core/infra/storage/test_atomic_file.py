"""Shared atomic publication fault-boundary tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pnc_automation.core.infra.storage import atomic_file


class AtomicFileTests(unittest.TestCase):
    """Proves sibling-temp publication preserves the old target on failed replace."""

    def test_failed_replace_preserves_previous_complete_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "state.json"
            destination.write_bytes(b"old")

            def fail_replace(_source: str | os.PathLike[str], _destination: str | os.PathLike[str]) -> None:
                raise OSError("injected replace failure")

            with self.assertRaisesRegex(OSError, "injected replace failure"):
                atomic_file.atomic_write_bytes(destination, b"new", replace=fail_replace)
            self.assertEqual(b"old", destination.read_bytes())
            self.assertEqual((), tuple(destination.parent.glob("atomic-*.tmp")))

    def test_replace_that_takes_effect_before_reporting_failure_is_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "state.json"
            destination.write_bytes(b"old")

            def replace_then_fail(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
                os.replace(source, target)
                raise OSError("reported after replacement")

            with self.assertRaisesRegex(OSError, "reported after replacement"):
                atomic_file.atomic_write_bytes(destination, b"new", replace=replace_then_fail)
            self.assertEqual(b"new", destination.read_bytes())

    def test_no_progress_write_is_rejected(self) -> None:
        class NoProgressHandle:
            def write(self, _payload: bytes) -> int:
                return 0

        with self.assertRaisesRegex(OSError, "no progress"):
            atomic_file._write_all(NoProgressHandle(), b"payload")


if __name__ == "__main__":
    unittest.main()
