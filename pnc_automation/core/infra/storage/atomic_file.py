"""Byte-oriented atomic file publication for durable local state."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from time import sleep

from pnc_automation.core.lifecycle import close_preserving_error

WINDOWS_REPLACE_RETRY_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.16, 0.32)


def atomic_write_bytes(
    destination: Path,
    payload: bytes,
    *,
    prefix: str = "atomic-",
    suffix: str = ".tmp",
    replace: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None] | None = None,
    sleep_function: Callable[[float], None] = sleep,
) -> None:
    """Flushes a complete sibling temporary file before replacing ``destination``.

    The same temporary path is retried for transient Windows sharing failures.  A
    failed replacement leaves the previous destination untouched when the platform
    provides that normal ``os.replace`` contract; the temporary file is removed only
    after the operation has failed.
    """

    if not isinstance(payload, bytes):
        raise TypeError("Atomic file payload must be bytes.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    replace_function = os.replace if replace is None else replace
    temporary_path: Path | None = None
    operation_error: BaseException | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=prefix,
            suffix=suffix,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            _write_all(handle, payload)
            handle.flush()
            os.fsync(handle.fileno())
        replace_flushed_file(
            temporary_path,
            destination,
            replace=replace_function,
            sleep_function=sleep_function,
        )
        temporary_path = None
    except BaseException as error:
        operation_error = error
    if temporary_path is not None and temporary_path.exists():
        close_preserving_error(
            lambda: temporary_path.unlink(),
            operation_error,
            message="Atomic file publication and temporary-file cleanup both failed.",
        )
    if operation_error is not None:
        raise operation_error


def replace_flushed_file(
    source: Path,
    destination: Path,
    *,
    replace: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None] | None = None,
    sleep_function: Callable[[float], None] = sleep,
) -> None:
    """Publishes one already-flushed temporary file with bounded sharing retries."""

    replace_function = os.replace if replace is None else replace
    for attempt in range(len(WINDOWS_REPLACE_RETRY_DELAYS) + 1):
        try:
            replace_function(source, destination)
            return
        except OSError as error:
            if (
                getattr(error, "winerror", None) not in {5, 32, 33}
                or attempt == len(WINDOWS_REPLACE_RETRY_DELAYS)
            ):
                raise
            sleep_function(WINDOWS_REPLACE_RETRY_DELAYS[attempt])


def _write_all(handle: object, payload: bytes) -> None:
    """Writes every payload byte and rejects a no-progress or short write."""

    offset = 0
    while offset < len(payload):
        written = handle.write(payload[offset:])  # type: ignore[attr-defined]
        if not isinstance(written, int) or written <= 0:
            raise OSError("Atomic file write made no progress.")
        offset += written
