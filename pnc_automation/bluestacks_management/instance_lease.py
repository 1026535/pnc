"""Process-scoped exclusive ownership for managed BlueStacks instances."""

from __future__ import annotations

import atexit
import hashlib
import json
import math
import os
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from pnc_automation.bluestacks_management.instance_reservation import (
    RESERVATION_RECEIPT_ENV,
    InstanceReservation,
    InstanceReservationClaim,
    InstanceReservationStatus,
    InstanceReservationStore,
    _foreign_reservation_error,
    require_safe_label,
    resolve_reservation_duration,
)
from pnc_automation.core.errors import InstanceBusyError, InstanceReservedError
from pnc_automation.core.lifecycle import close_preserving_error
from pnc_automation.core.infra.storage.native_locking import (
    ensure_lock_byte as _ensure_lock_byte,
    lock_file_nonblocking as _lock_file_nonblocking,
    unlock_file as _unlock_file,
)

DEFAULT_INSTANCE_LEASE_ROOT = Path(tempfile.gettempdir()) / "pnc-automation-instance-leases"


@dataclass(slots=True)
class ProcessInstanceLease:
    """One ref-counted operation reference to a native instance lock."""

    display_name: str
    path: Path
    _registry: "InstanceLeaseRegistry"
    _lease_key: str
    _released: bool = field(default=False, init=False, repr=False)

    def release(self, *, finalizer: Callable[[], None] | None = None) -> None:
        """Releases this reference and runs a requested finalizer at process-idle."""

        if self._released:
            return
        self._released = True
        self._registry._release_reference(self._lease_key, finalizer=finalizer)


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
        errors: list[BaseException] = []
        for lease in self.leases:
            try:
                lease.release()
            except BaseException as error:
                errors.append(error)
        _raise_release_errors(errors)

    release = close

    def __enter__(self) -> "InstanceLeaseBundle":
        """Enters an explicitly scoped multi-instance operation."""

        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        """Releases the operation bundle on normal or exceptional exit."""

        active_error = _exception if isinstance(_exception, BaseException) else None
        close_preserving_error(
            self.close,
            active_error,
            message="Reserved workflow and BlueStacks phase cleanup both failed.",
        )


@dataclass(slots=True)
class _NativeInstanceLease:
    """Owns the file handle and native lock shared by operation references."""

    display_name: str
    path: Path
    handle: BinaryIO

    def release(self) -> None:
        """Releases the native lock and closes its file handle."""

        try:
            _unlock_file(self.handle)
        except BaseException as error:
            close_preserving_error(
                self.handle.close,
                error,
                message="BlueStacks lease release and handle cleanup both failed.",
            )
            raise
        else:
            self.handle.close()


@dataclass(slots=True)
class InstanceLeaseRegistry:
    """Acquires bounded, ref-counted emulator leases for one PNC process."""

    root: Path = field(
        default_factory=lambda: DEFAULT_INSTANCE_LEASE_ROOT
    )
    wait_timeout_seconds: float = 120.0
    poll_interval_seconds: float = 0.25
    reservation_store: InstanceReservationStore | None = None
    _leases: dict[str, _NativeInstanceLease] = field(default_factory=dict, init=False, repr=False)
    _reference_counts: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _finalizers: dict[str, Callable[[], None]] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _default_reservation_store: InstanceReservationStore | None = field(default=None, init=False, repr=False)

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
        if (
            isinstance(wait_seconds, bool)
            or not isinstance(wait_seconds, (int, float))
            or not math.isfinite(wait_seconds)
            or wait_seconds < 0
        ):
            raise ValueError("Instance lease timeout must be finite and non-negative.")
        if (
            isinstance(self.poll_interval_seconds, bool)
            or not isinstance(self.poll_interval_seconds, (int, float))
            or not math.isfinite(self.poll_interval_seconds)
            or self.poll_interval_seconds <= 0
        ):
            raise ValueError("Instance lease poll interval must be finite and positive.")
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

            # A foreign active long reservation rejects admission immediately,
            # before any instance resolution or native-lock waiting.
            self._raise_for_foreign_reservations(frozenset(requested_keys))

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
                    # Recheck under the metadata mutex after taking the native
                    # locks so a claim racing publication cannot admit work that
                    # a concurrently published foreign reservation now covers.
                    with self._reservations().metadata_lock():
                        conflicts = self._reservation_conflicts(frozenset(requested_keys))
                    if conflicts:
                        raise _foreign_reservation_error(list(conflicts))
                except BaseException as error:
                    cleanup_errors: list[BaseException] = []
                    for lease in acquired.values():
                        try:
                            lease.release()
                        except BaseException as cleanup_error:
                            cleanup_errors.append(cleanup_error)
                    if cleanup_errors:
                        raise BaseExceptionGroup(
                            "BlueStacks lease acquisition and rollback both failed.",
                            [error, *cleanup_errors],
                        ) from None
                    if not isinstance(error, InstanceBusyError) or isinstance(error, InstanceReservedError):
                        raise
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

    def claim_reservation(
        self,
        display_names: tuple[str, ...],
        *,
        scope_id: str,
        owner_label: str,
        duration_seconds: float | None = None,
    ) -> InstanceReservationClaim:
        """Claims one all-or-none long reservation after proving every target idle.

        Native task locks establish idleness first; the private receipt is written
        and the record published under the short-held metadata mutex; the task
        locks are then released. Any held task lock or foreign active claim fails
        the whole bundle without partial state.
        """

        requested = _normalize_display_names(display_names)
        ordered = tuple(sorted(requested, key=lambda item: item[0]))
        scope_label = require_safe_label(scope_id, "scope_id")
        owner = require_safe_label(owner_label, "owner_label")
        duration = resolve_reservation_duration(duration_seconds)
        store = self._reservations()
        acquired: dict[str, _NativeInstanceLease] = {}
        try:
            for lease_key, display_name in ordered:
                acquired[lease_key] = self._acquire_once(
                    lease_key=lease_key,
                    display_name=display_name,
                )
            receipt, receipt_path = store.issue_receipt(scope_id=scope_label)
            try:
                reservation = store.publish_claim(
                    receipt=receipt,
                    owner_label=owner,
                    instances=tuple(display_name for _lease_key, display_name in ordered),
                    duration_seconds=duration,
                )
            except BaseException:
                store.remove_receipt(receipt_path)
                raise
        finally:
            for lease in acquired.values():
                lease.release()
        return InstanceReservationClaim(reservation=reservation, receipt_path=receipt_path)

    def renew_reservation(
        self,
        receipt_path: Path,
        *,
        duration_seconds: float | None = None,
    ) -> InstanceReservation:
        """Extends the caller's idle deadline through the authoritative store."""

        return self._reservations().renew(receipt_path, duration_seconds=duration_seconds)

    def release_reservation(self, receipt_path: Path) -> InstanceReservation | None:
        """Releases the caller's whole declared scope through the authoritative store."""

        return self._reservations().release(receipt_path)

    def reservation_status(
        self,
        display_names: tuple[str, ...],
    ) -> tuple[InstanceReservationStatus, ...]:
        """Builds secret-free per-instance status without ADB or emulator resolution."""

        store = self._reservations()
        records = store.load()
        now = store.now()
        statuses: list[InstanceReservationStatus] = []
        for display_name in display_names:
            lease_key = display_name.strip().casefold()
            covering = [record for record in records if lease_key in record.instance_keys]
            active = next((record for record in covering if record.is_active(now)), None)
            shown = active if active is not None else (covering[-1] if covering else None)
            if shown is None:
                state = "none"
            elif active is not None:
                state = "active"
            else:
                state = "expired"
            task_state = _probe_task_lock(self.root, lease_key)
            statuses.append(
                InstanceReservationStatus(
                    display_name=display_name,
                    reservation_state=state,
                    task_lock_state=task_state,
                    claimable=state != "active" and task_state == "idle",
                    scope_id=shown.scope_id if shown is not None else None,
                    owner_label=shown.owner_label if shown is not None else None,
                    expires_at=shown.expires_at if shown is not None else None,
                )
            )
        return tuple(statuses)

    def _reservations(self) -> InstanceReservationStore:
        """Returns the authoritative reservation store rooted at this lease root."""

        if self.reservation_store is not None:
            return self.reservation_store
        if self._default_reservation_store is None:
            self._default_reservation_store = InstanceReservationStore(lease_root=self.root)
        return self._default_reservation_store

    def _reservation_conflicts(
        self,
        requested_keys: frozenset[str],
    ) -> tuple[InstanceReservation, ...]:
        """Returns active foreign reservations intersecting the requested bundle."""

        store = self._reservations()
        covering = tuple(record for record in store.load() if record.covers_any(requested_keys))
        if not covering:
            return ()
        now = store.now()
        active = tuple(record for record in covering if record.is_active(now))
        if not active:
            return ()
        digest = self._presented_capability_digest(store)
        return tuple(
            record
            for record in active
            if digest is None or record.capability_digest != digest
        )

    def _presented_capability_digest(self, store: InstanceReservationStore) -> str | None:
        """Reads the caller's private receipt digest from the canonical env carrier."""

        raw_path = os.environ.get(RESERVATION_RECEIPT_ENV)
        if not raw_path:
            return None
        try:
            return store.read_receipt(Path(raw_path)).capability_digest
        except Exception:
            return None

    def _raise_for_foreign_reservations(self, requested_keys: frozenset[str]) -> None:
        """Rejects admission covered by an active foreign long reservation."""

        conflicts = self._reservation_conflicts(requested_keys)
        if conflicts:
            raise _foreign_reservation_error(list(conflicts))

    def _acquire_once(self, *, lease_key: str, display_name: str) -> _NativeInstanceLease:
        """Attempts one native lock acquisition without waiting."""

        self.root.mkdir(parents=True, exist_ok=True)
        path = _lease_lock_path(self.root, lease_key)
        # ``a+b`` is intentionally avoided: Windows opens append-mode handles with
        # append-on-write semantics, which caused owner JSON to accumulate on reuse.
        path.touch(exist_ok=True)
        handle = path.open("r+b", buffering=0)
        try:
            _ensure_lock_byte(handle)
            try:
                _lock_file_nonblocking(handle)
            except OSError as error:
                owner = _read_owner(handle)
                owner_description = _format_owner(owner)
                raise InstanceBusyError(
                    f"BlueStacks instance '{display_name}' is owned by another PNC process{owner_description}",
                    display_name=display_name,
                    owner_pid=owner.get("pid"),
                    acquired_at=owner.get("acquired_at"),
                ) from error
            _write_owner(handle, display_name=display_name)
        except BaseException as error:
            close_preserving_error(
                handle.close,
                error,
                message="BlueStacks lease acquisition and handle cleanup both failed.",
            )
            raise
        return _NativeInstanceLease(display_name=display_name, path=path, handle=handle)

    def _release_reference(
        self,
        lease_key: str,
        *,
        finalizer: Callable[[], None] | None = None,
    ) -> None:
        """Drops one reference, then finalizes after making the instance claimable."""

        native: _NativeInstanceLease | None = None
        pending_finalizer: Callable[[], None] | None = None
        with self._lock:
            count = self._reference_counts.get(lease_key, 0)
            if count <= 0:
                return
            if finalizer is not None:
                # The latest exact-process snapshot is the safest one to revalidate
                # when several child sessions request the same phase-end shutdown.
                self._finalizers[lease_key] = finalizer
            if count == 1:
                pending_finalizer = self._finalizers.get(lease_key)
                self._reference_counts.pop(lease_key, None)
                native = self._leases.pop(lease_key, None)
                self._finalizers.pop(lease_key, None)
            else:
                self._reference_counts[lease_key] = count - 1
        if native is not None:
            native.release()
        if pending_finalizer is not None:
            # A phase-end finalizer owns its own bounded re-acquisition. Running
            # it after release lets newly queued work claim or cancel shutdown.
            pending_finalizer()

    def release_all(self) -> None:
        """Releases every process-owned lease, primarily for clean shutdown and tests."""

        errors: list[BaseException] = []
        with self._lock:
            leased_items = tuple(self._leases.items())
            finalizers = tuple(
                self._finalizers[lease_key]
                for lease_key, _lease in leased_items
                if lease_key in self._finalizers
            )
            self._leases.clear()
            self._reference_counts.clear()
            self._finalizers.clear()
        for _lease_key, lease in leased_items:
            try:
                lease.release()
            except BaseException as error:
                errors.append(error)
        for finalizer in finalizers:
            try:
                # Release the whole declared bundle before any delayed cleanup
                # tries to re-acquire an individual instance.
                finalizer()
            except BaseException as error:
                errors.append(error)
        _raise_release_errors(errors)


def _raise_release_errors(errors: list[BaseException]) -> None:
    """Raises every finalizer failure after all native locks have been released."""

    if not errors:
        return
    if len(errors) == 1:
        raise errors[0]
    raise BaseExceptionGroup("Multiple BlueStacks lease finalizers failed.", errors)


def _lease_lock_path(root: Path, lease_key: str) -> Path:
    """Derives the per-instance native lock file from its normalized key."""

    return root / f"{hashlib.sha256(lease_key.encode('utf-8')).hexdigest()}.lock"


def _probe_task_lock(root: Path, lease_key: str) -> str:
    """Probes one native task lock without claiming it or touching diagnostics."""

    path = _lease_lock_path(root, lease_key)
    try:
        if not path.exists() or path.stat().st_size == 0:
            return "idle"
    except OSError:
        return "unknown"
    try:
        handle = path.open("r+b", buffering=0)
    except OSError:
        return "unknown"
    try:
        try:
            _lock_file_nonblocking(handle)
        except OSError:
            return "busy"
        try:
            _unlock_file(handle)
        except OSError:
            pass
        return "idle"
    finally:
        handle.close()


def _normalize_display_names(display_names: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Normalizes and validates one requested lease bundle."""

    requested = tuple((name.strip().casefold(), name.strip()) for name in display_names)
    if not requested or any(not key for key, _ in requested):
        raise ValueError("At least one non-empty emulator display name is required for a lease bundle.")
    if len({key for key, _ in requested}) != len(requested):
        raise ValueError("An emulator lease bundle cannot contain duplicate display names.")
    return requested


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
