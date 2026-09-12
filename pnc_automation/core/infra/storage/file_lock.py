"""Strict native cross-process path locks used by durable archive stores."""

from __future__ import annotations

import errno
import math
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from pnc_automation.core.lifecycle import close_preserving_error
from pnc_automation.core.infra.storage.native_locking import ensure_lock_byte, lock_file_nonblocking, unlock_file


class StorageLockBusyError(TimeoutError):
    """Raised when a native storage lock cannot be acquired within its budget."""


class StorageLockReentryError(RuntimeError):
    """Raised when one thread tries to start a nested transaction on one stream."""


@dataclass(slots=True)
class NativePathLock:
    """Owns one stable lock-file handle and its native OS lock."""

    path: Path
    handle: BinaryIO
    _released: bool = field(default=False, init=False, repr=False)

    def release(self) -> None:
        """Releases the native lock and closes its handle exactly once."""

        if self._released:
            return
        self._released = True
        try:
            unlock_file(self.handle)
        except BaseException as error:
            close_preserving_error(
                self.handle.close,
                error,
                message="Storage lock release and handle cleanup both failed.",
            )
            raise
        else:
            self.handle.close()


@dataclass(slots=True)
class NativePathLockManager:
    """Acquires validated native locks with finite cross-process wait budgets."""

    timeout_seconds: float = 5.0
    poll_interval_seconds: float = 0.05

    def __post_init__(self) -> None:
        _validate_timeout(self.timeout_seconds)
        _validate_poll_interval(self.poll_interval_seconds)

    def acquire(self, path: Path, *, timeout_seconds: float | None = None) -> NativePathLock:
        """Waits for one path lock, rejecting same-thread reentry."""

        canonical_path = _canonical_lock_path(path)
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        _validate_timeout(timeout)
        key = str(canonical_path)
        thread_id = threading.get_ident()
        deadline = time.monotonic() + timeout
        with _HELD_LOCK:
            if _HELD_PATHS.get(key) == thread_id:
                raise StorageLockReentryError(f"Storage lock is already owned by this thread: {canonical_path}")

        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            with _HELD_LOCK:
                held_by = _HELD_PATHS.get(key)
            if held_by is None:
                handle = canonical_path.open("a+b", buffering=0)
                try:
                    ensure_lock_byte(handle)
                    lock_file_nonblocking(handle)
                except OSError as error:
                    close_preserving_error(
                        handle.close,
                        error,
                        message="Storage lock acquisition and handle cleanup both failed.",
                    )
                    if not _is_lock_contention(error):
                        raise
                else:
                    with _HELD_LOCK:
                        current_owner = _HELD_PATHS.get(key)
                        if current_owner is None:
                            _HELD_PATHS[key] = thread_id
                            return NativePathLock(path=canonical_path, handle=handle)
                    _unlock_and_close(handle)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StorageLockBusyError(f"Timed out waiting for storage lock: {canonical_path}")
            time.sleep(min(self.poll_interval_seconds, remaining))

    def release(self, lock: NativePathLock) -> None:
        """Releases a lock and removes its process-local ownership marker."""

        key = str(lock.path)
        try:
            lock.release()
        finally:
            with _HELD_LOCK:
                _HELD_PATHS.pop(key, None)


_HELD_LOCK = threading.Lock()
_HELD_PATHS: dict[str, int] = {}


def _canonical_lock_path(path: Path) -> Path:
    """Normalizes lock aliases without requiring the lock file to exist."""

    resolved = path.expanduser().resolve(strict=False)
    return Path(os.path.normcase(str(resolved)))


def _validate_timeout(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Storage lock timeout must be a finite non-negative number.")


def _validate_poll_interval(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("Storage lock poll interval must be a finite positive number.")


def _unlock_and_close(handle: BinaryIO) -> None:
    try:
        unlock_file(handle)
    finally:
        handle.close()


def _is_lock_contention(error: OSError) -> bool:
    return error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK, errno.EPERM} or getattr(error, "winerror", None) in {5, 32, 33}
