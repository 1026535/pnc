"""Native storage-lock ownership tests."""

from __future__ import annotations

import subprocess
import math
import sys
import tempfile
import time
import unittest
from pathlib import Path

from pnc_automation.core.infra.storage.file_lock import (
    NativePathLockManager,
    StorageLockBusyError,
    StorageLockReentryError,
)


class NativePathLockTests(unittest.TestCase):
    """Proves same-process and subprocess lock exclusion without stale-lock deletion."""

    def test_same_thread_reentry_is_rejected_and_release_allows_next_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "stream.lock"
            manager = NativePathLockManager(timeout_seconds=0.1, poll_interval_seconds=0.01)
            held = manager.acquire(path)
            with self.assertRaises(StorageLockReentryError):
                manager.acquire(path)
            manager.release(held)
            next_lock = manager.acquire(path)
            manager.release(next_lock)

    def test_separate_process_contention_is_bounded_and_release_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            lock_path = root / "stream.lock"
            ready = root / "ready"
            release = root / "release"
            worker = Path(__file__).resolve().parents[5] / "tests" / "support" / "core" / "infra" / "storage" / "lock_worker.py"
            process = subprocess.Popen(
                [sys.executable, str(worker), str(lock_path), str(ready), str(release)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=Path(__file__).resolve().parents[5],
            )
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if not ready.exists():
                    stdout, stderr = process.communicate(timeout=5)
                    self.fail(f"Lock worker did not signal readiness: stdout={stdout!r} stderr={stderr!r}")
                manager = NativePathLockManager(timeout_seconds=0.15, poll_interval_seconds=0.01)
                with self.assertRaises(StorageLockBusyError):
                    manager.acquire(lock_path)
                release.touch()
                self.assertEqual(0, process.wait(timeout=5))
                process.communicate(timeout=5)
                owned = manager.acquire(lock_path)
                manager.release(owned)
            finally:
                if process.poll() is None:
                    release.touch()
                    process.kill()
                    process.wait(timeout=5)
                    process.communicate(timeout=5)

    def test_lock_timeout_and_poll_inputs_are_strictly_bounded(self) -> None:
        with self.assertRaises(ValueError):
            NativePathLockManager(timeout_seconds=True)
        with self.assertRaises(ValueError):
            NativePathLockManager(timeout_seconds=-1)
        with self.assertRaises(ValueError):
            NativePathLockManager(timeout_seconds=math.inf)
        with self.assertRaises(ValueError):
            NativePathLockManager(poll_interval_seconds=True)
        with self.assertRaises(ValueError):
            NativePathLockManager(poll_interval_seconds=0)


if __name__ == "__main__":
    unittest.main()
