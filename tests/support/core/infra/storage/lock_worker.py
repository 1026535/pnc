"""Child process used by the native lock contention test."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from pnc_automation.core.infra.storage.file_lock import NativePathLockManager


def main() -> int:
    lock_path, ready_path, release_path = map(Path, sys.argv[1:4])
    lock = NativePathLockManager(timeout_seconds=5, poll_interval_seconds=0.01).acquire(lock_path)
    try:
        ready_path.touch()
        deadline = time.monotonic() + 10
        while not release_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        NativePathLockManager(timeout_seconds=1, poll_interval_seconds=0.01).release(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
