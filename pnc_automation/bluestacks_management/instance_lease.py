"""Process-scoped exclusive ownership for managed BlueStacks instances."""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from pnc_automation.core.errors import InstanceBusyError

DEFAULT_INSTANCE_LEASE_ROOT = Path(tempfile.gettempdir()) / "pnc-automation-instance-leases"


@dataclass(slots=True)
class ProcessInstanceLease:
    """One ref-counted operation reference to a native instance lock."""

    display_name: str
    path: Path
    _registry: "InstanceLeaseRegistry"
    _lease_key: str
    _released: bool = field(default=False, init=False, repr=False)

    def release(self) -> None:
        """Releases this operation reference and the native lock when no references remain."""

        if self._released:
            return
        self._released = True
        self._registry._release_reference(self._lease_key)


@dataclass(slots=True)
class InstanceLeaseBundle:
    """Owns a complete multi-instance operation bundle until explicitly closed."""

    leases: tuple[ProcessInstanceLease, ...]
    _closed: bool = field(default=False, init=False, repr=False)

    def __iter__(self) -> Iterator[ProcessInstanceLease]:
        """Iterates over the operation's instance references."""

        return iter(self.leases)

    def __len__(self) -> int:
        """Returns the number of instances in this operation bundle."""

        return len(self.leases)

    def __getitem__(self, index: int) -> ProcessInstanceLease:
        """Returns one lease reference by bundle position."""

        return self.leases[index]

    def close(self) -> None:
        """Releases every instance reference, including after a failed operation."""

        if self._closed:
            return
        self._closed = True
        for lease in self.leases:
            lease.release()

    release = close

    def __enter__(self) -> "InstanceLeaseBundle":
        """Enters an explicitly scoped multi-instance operation."""

        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        """Releases the operation bundle on normal or exceptional exit."""

        self.close()


@dataclass(slots=True)
class _NativeInstanceLease:
    """Owns the file handle and native lock shared by operation references."""

    display_name: str
    path: Path
    handle: BinaryIO

    def release(self) -> None:
        """Releases the native lock and closes its file handle."""

        _unlock_file(self.handle)
        self.handle.close()


@dataclass(slots=True)
class InstanceLeaseRegistry:
    """Acquires bounded, ref-counted emulator leases for one PNC process."""

    root: Path = field(
        default_factory=lambda: DEFAULT_INSTANCE_LEASE_ROOT
    )
    wait_timeout_seconds: float = 120.0
    poll_interval_seconds: float = 0.25
    _leases: dict[str, _NativeInstanceLease] = field(default_factory=dict, init=False, repr=False)
    _reference_counts: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def acquire(
        self,
        *,
        display_name: str,
        timeout_seconds: float | None = None,
    ) -> ProcessInstanceLease:
        """Waits boundedly for one instance and returns one operation reference."""

        return self.acquire_many((display_name,), timeout_seconds=timeout_seconds)[0]

    def acquire_many(
        self,
        display_names: tuple[str, ...],
        *,
        timeout_seconds: float | None = None,
    ) -> tuple[ProcessInstanceLease, ...]:
        """Acquires a complete sorted bundle without retaining partial ownership while waiting."""

        requested = _normalize_display_names(display_names)
        wait_seconds = self.wait_timeout_seconds if timeout_seconds is None else timeout_seconds
        if wait_seconds < 0:
            raise ValueError("Instance lease timeout cannot be negative.")
        if self.poll_interval_seconds <= 0:
            raise ValueError("Instance lease poll interval must be positive.")
        ordered = tuple(sorted(requested, key=lambda item: item[0]))
        with self._lock:
            requested_keys = {key for key, _ in ordered}
            existing_keys = set(self._leases)
            new_keys = requested_keys - existing_keys
            if existing_keys and new_keys:
                raise RuntimeError(
                    "A PNC process cannot expand its emulator lease set after acquisition. "
                    "Declare the complete instance bundle before connecting to any instance."
                )

            deadline = time.monotonic() + wait_seconds
            while True:
                acquired: dict[str, _NativeInstanceLease] = {}
                try:
                    for lease_key, display_name in ordered:
                        if lease_key in self._leases:
                            continue
                        acquired[lease_key] = self._acquire_once(
                            lease_key=lease_key,
                            display_name=display_name,
                        )
                except InstanceBusyError as error:
                    for lease in acquired.values():
                        lease.release()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise InstanceBusyError(
                            f"Timed out after {wait_seconds:g} seconds waiting for a BlueStacks instance bundle. "
                            f"Last conflict: {error.message}",
                            **error.details,
                        ) from error
                    time.sleep(min(self.poll_interval_seconds, remaining))
                    continue

                self._leases.update(acquired)
                for lease_key, _display_name in ordered:
                    self._reference_counts[lease_key] = self._reference_counts.get(lease_key, 0) + 1
                return tuple(
                    ProcessInstanceLease(
                        display_name=display_name,
                        path=self._leases[lease_key].path,
                        _registry=self,
                        _lease_key=lease_key,
                    )
                    for lease_key, display_name in requested
                )

    def acquire_bundle(
        self,
        display_names: tuple[str, ...],
        *,
        timeout_seconds: float | None = None,
    ) -> InstanceLeaseBundle:
        """Acquires and returns one explicitly closable complete operation bundle."""

        return InstanceLeaseBundle(self.acquire_many(display_names, timeout_seconds=timeout_seconds))

    def _acquire_once(self, *, lease_key: str, display_name: str) -> _NativeInstanceLease:
        """Attempts one native lock acquisition without waiting."""

        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{hashlib.sha256(lease_key.encode('utf-8')).hexdigest()}.lock"
        # ``a+b`` is intentionally avoided: Windows opens append-mode handles with
        # append-on-write semantics, which caused owner JSON to accumulate on reuse.
        path.touch(exist_ok=True)
        handle = path.open("r+b", buffering=0)
        _ensure_lock_byte(handle)
        try:
            _lock_file_nonblocking(handle)
        except OSError as error:
            owner = _read_owner(handle)
            handle.close()
            owner_description = _format_owner(owner)
            raise InstanceBusyError(
                f"BlueStacks instance '{display_name}' is owned by another PNC process{owner_description}",
                display_name=display_name,
                owner_pid=owner.get("pid"),
                acquired_at=owner.get("acquired_at"),
            ) from error
        _write_owner(handle, display_name=display_name)
        return _NativeInstanceLease(display_name=display_name, path=path, handle=handle)

    def _release_reference(self, lease_key: str) -> None:
        """Drops one operation reference and closes the native lock at zero."""

        native: _NativeInstanceLease | None = None
        with self._lock:
            count = self._reference_counts.get(lease_key, 0)
            if count <= 0:
                return
            if count == 1:
                self._reference_counts.pop(lease_key, None)
                native = self._leases.pop(lease_key, None)
            else:
                self._reference_counts[lease_key] = count - 1
        if native is not None:
            native.release()

    def release_all(self) -> None:
        """Releases every process-owned lease, primarily for clean shutdown and tests."""

        with self._lock:
            leases = tuple(self._leases.values())
            self._leases.clear()
            self._reference_counts.clear()
        for lease in leases:
            lease.release()


def _normalize_display_names(display_names: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Normalizes and validates one requested lease bundle."""

    requested = tuple((name.strip().casefold(), name.strip()) for name in display_names)
    if not requested or any(not key for key, _ in requested):
        raise ValueError("At least one non-empty emulator display name is required for a lease bundle.")
    if len({key for key, _ in requested}) != len(requested):
        raise ValueError("An emulator lease bundle cannot contain duplicate display names.")
    return requested


def _ensure_lock_byte(handle: BinaryIO) -> None:
    """Ensures the file contains the byte used as the Windows lock region."""

    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)


def _lock_file_nonblocking(handle: BinaryIO) -> None:
    """Takes a non-blocking exclusive lock using the host platform's native primitive."""

    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: BinaryIO) -> None:
    """Releases the native file lock held by one process."""

    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_owner(handle: BinaryIO, *, display_name: str) -> None:
    """Replaces non-secret ownership diagnostics behind the locked byte."""

    metadata = {
        "pid": os.getpid(),
        "acquired_at": datetime.now(tz=UTC).isoformat(),
        "display_name": display_name,
    }
    payload = json.dumps(metadata, sort_keys=True).encode("utf-8")
    handle.seek(1)
    handle.write(payload)
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def _read_owner(handle: BinaryIO) -> dict[str, object]:
    """Reads best-effort diagnostics from a lock owned by another process."""

    try:
        handle.seek(1)
        decoded = json.loads(handle.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _format_owner(owner: dict[str, object]) -> str:
    """Builds a concise optional owner suffix without exposing command lines or credentials."""

    fields: list[str] = []
    pid = owner.get("pid")
    acquired_at = owner.get("acquired_at")
    if isinstance(pid, int):
        fields.append(f"PID {pid}")
    if isinstance(acquired_at, str) and acquired_at:
        fields.append(f"since {acquired_at}")
    return "" if not fields else f" ({', '.join(fields)})"


PROCESS_INSTANCE_LEASES = InstanceLeaseRegistry()
atexit.register(PROCESS_INSTANCE_LEASES.release_all)
