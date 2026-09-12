"""Shared atomic publication fault-boundary tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_windows_sharing_retry_uses_exact_attempts_and_delays(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "state.json"
            calls = 0
            delays: list[float] = []

            def replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
                nonlocal calls
                calls += 1
                if calls <= len(atomic_file.WINDOWS_REPLACE_RETRY_DELAYS):
                    error = OSError("sharing")
                    error.winerror = 32  # type: ignore[attr-defined]
                    raise error
                os.replace(source, target)

            atomic_file.atomic_write_bytes(destination, b"new", replace=replace, sleep_function=delays.append)
            self.assertEqual(len(atomic_file.WINDOWS_REPLACE_RETRY_DELAYS) + 1, calls)
            self.assertEqual(list(atomic_file.WINDOWS_REPLACE_RETRY_DELAYS), delays)
            self.assertEqual(b"new", destination.read_bytes())

    def test_persistent_windows_sharing_denial_preserves_destination_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "state.json"
            destination.write_bytes(b"old")
            calls = 0
            delays: list[float] = []

            def deny(_source: str | os.PathLike[str], _target: str | os.PathLike[str]) -> None:
                nonlocal calls
                calls += 1
                error = OSError("sharing")
                error.winerror = 32  # type: ignore[attr-defined]
                raise error

            with self.assertRaises(OSError):
                atomic_file.atomic_write_bytes(destination, b"new", replace=deny, sleep_function=delays.append)
            self.assertEqual(len(atomic_file.WINDOWS_REPLACE_RETRY_DELAYS) + 1, calls)
            self.assertEqual(list(atomic_file.WINDOWS_REPLACE_RETRY_DELAYS), delays)
            self.assertEqual(b"old", destination.read_bytes())
            self.assertEqual((), tuple(destination.parent.glob("atomic-*.tmp")))

    def test_replace_failure_and_cleanup_failure_are_both_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "state.json"

            def fail_replace(_source: str | os.PathLike[str], _target: str | os.PathLike[str]) -> None:
                raise OSError("primary replace failure")

            with patch.object(Path, "unlink", side_effect=PermissionError("cleanup failure")):
                with self.assertRaises(BaseExceptionGroup) as captured:
                    atomic_file.atomic_write_bytes(destination, b"new", replace=fail_replace)
            messages = [str(error) for error in captured.exception.exceptions]
            self.assertTrue(any("primary replace failure" in message for message in messages))
            self.assertTrue(any("cleanup failure" in message for message in messages))

    def test_fsync_failure_preserves_previous_destination_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "state.json"
            destination.write_bytes(b"old")
            with patch.object(atomic_file.os, "fsync", side_effect=OSError("injected fsync failure")):
                with self.assertRaisesRegex(OSError, "fsync failure"):
                    atomic_file.atomic_write_bytes(destination, b"new")
            self.assertEqual(b"old", destination.read_bytes())
            self.assertEqual((), tuple(destination.parent.glob("atomic-*.tmp")))


if __name__ == "__main__":
    unittest.main()
