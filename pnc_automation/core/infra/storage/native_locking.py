"""Shared native OS locking primitives for process-owned local files."""

from __future__ import annotations

import os
from typing import BinaryIO


def ensure_lock_byte(handle: BinaryIO) -> None:
    """Ensures a one-byte region exists for Windows byte-range locking."""

    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)


def lock_file_nonblocking(handle: BinaryIO) -> None:
    """Takes a non-blocking exclusive lock using msvcrt or fcntl."""

    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def unlock_file(handle: BinaryIO) -> None:
    """Releases one native exclusive file lock."""

    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
