"""Lease-aware shutdown and crash recovery for resolved BlueStacks processes."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from pnc_automation.bluestacks_management.instance_lease import (
    DEFAULT_INSTANCE_LEASE_ROOT,
    InstanceLeaseRegistry,
)
from pnc_automation.bluestacks_management.instance_memory_monitor import (
    BlueStacksProcessStopper,
    HostConfigProvider,
    PowerShellBlueStacksProcessStopper,
)
from pnc_automation.bluestacks_management.process_control import wait_for_instance_state
from pnc_automation.core.config.host import (
    LiveAutomationRole,
    capabilities_for_roles,
)
from pnc_automation.core.errors import ConfigurationError, InstanceBusyError
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksInstanceResolver,
    BlueStacksRunningInstanceSource,
)

_SHUTDOWN_INTENT_FIELDS = frozenset(
    {
        "display_name",
        "intent_id",
        "instance_id",
        "instance_key",
        "process_id",
        "metadata_path",
        "requested_at",
        "grace_period_seconds",
        "not_before",
    }
)
_SHUTDOWN_INTENT_POLL_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class InstanceShutdownIntent:
    """Records an exact process that should close after its task-series lease ends."""

    display_name: str
    intent_id: str
    instance_id: str
    instance_key: str
    process_id: int
    metadata_path: str
    requested_at: float
    grace_period_seconds: float
    not_before: float | None = None

    def __post_init__(self) -> None:
        """Rejects malformed durable shutdown identity."""

        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.display_name,
                self.intent_id,
                self.instance_id,
                self.instance_key,
                self.metadata_path,
            )
        ):
            raise ValueError("Shutdown intent identity fields must be non-empty.")
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int) or self.process_id <= 0:
            raise ValueError("Shutdown intent process_id must be positive.")
        if (
            isinstance(self.requested_at, bool)
            or not isinstance(self.requested_at, (int, float))
            or not math.isfinite(float(self.requested_at))
            or self.requested_at < 0
        ):
            raise ValueError("Shutdown intent requested_at must be finite and non-negative.")
        if (
            isinstance(self.grace_period_seconds, bool)
            or not isinstance(self.grace_period_seconds, (int, float))
            or not math.isfinite(float(self.grace_period_seconds))
            or self.grace_period_seconds < 0
        ):
            raise ValueError("Shutdown intent grace_period_seconds must be finite and non-negative.")
        if self.not_before is not None and (
            isinstance(self.not_before, bool)
            or not isinstance(self.not_before, (int, float))
            or not math.isfinite(float(self.not_before))
            or self.not_before < 0
        ):
            raise ValueError("Shutdown intent not_before must be null or a finite non-negative timestamp.")


@dataclass(frozen=True, slots=True)
class InstanceShutdownIntentStore:
    """Persists phase cleanup intent so a host monitor can recover after process exit."""

    root: Path = DEFAULT_INSTANCE_LEASE_ROOT / "shutdown-intents"

    def load_all(self) -> tuple[InstanceShutdownIntent, ...]:
        """Loads every strict intent record."""

        if not self.root.exists():
            return ()
        records: list[InstanceShutdownIntent] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                record = self._load_path(path)
            except FileNotFoundError:
                # A normally completing leased phase may remove its intent
                # between directory enumeration and this read.
                continue
            if path != self.path_for(record.display_name, record.instance_key):
                raise ConfigurationError("BlueStacks shutdown intent identity is invalid.")
            records.append(record)
        return tuple(records)

    def load(self, *, display_name: str, instance_key: str) -> InstanceShutdownIntent | None:
        """Loads the current intent for one exact host identity, if present."""

        path = self.path_for(display_name, instance_key)
        try:
            record = self._load_path(path)
        except FileNotFoundError:
            return None
        if (
            record.display_name.casefold() != display_name.strip().casefold()
            or record.instance_key != instance_key.strip()
        ):
            raise ConfigurationError("BlueStacks shutdown intent identity is invalid.")
        return record

    def save(self, record: InstanceShutdownIntent) -> None:
        """Atomically persists one exact-process cleanup intent."""

        destination = self.path_for(record.display_name, record.instance_key)
        payload = json.dumps(_serialize_shutdown_intent(record), sort_keys=True, separators=(",", ":"))
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ConfigurationError(
                "BlueStacks shutdown intent could not be persisted.",
                failure_phase="state_write",
            ) from error

    def remove(self, *, display_name: str, instance_key: str) -> None:
        """Removes one completed or invalidated intent."""

        try:
            self.path_for(display_name, instance_key).unlink(missing_ok=True)
        except OSError as error:
            raise ConfigurationError(
                "BlueStacks shutdown intent could not be cleared.",
                failure_phase="state_write",
            ) from error

    def path_for(self, display_name: str, instance_key: str) -> Path:
        """Returns the stable non-secret path for one instance identity."""

        key = f"{display_name.strip().casefold()}\0{instance_key.strip()}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def _load_path(self, path: Path) -> InstanceShutdownIntent:
        """Loads one allow-listed intent document without echoing its values."""

        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfigurationError(
                "BlueStacks shutdown intent is malformed.",
                state_file=path.name,
            ) from error
        if not isinstance(payload, dict) or set(payload) != _SHUTDOWN_INTENT_FIELDS:
            raise ConfigurationError(
                "BlueStacks shutdown intent schema is invalid.",
                state_file=path.name,
            )
        try:
            return InstanceShutdownIntent(
                display_name=_require_string(payload["display_name"]),
                intent_id=_require_string(payload["intent_id"]),
                instance_id=_require_string(payload["instance_id"]),
                instance_key=_require_string(payload["instance_key"]),
                process_id=_require_positive_int(payload["process_id"]),
                metadata_path=_require_string(payload["metadata_path"]),
                requested_at=_require_nonnegative_number(payload["requested_at"]),
                grace_period_seconds=_require_nonnegative_number(payload["grace_period_seconds"]),
                not_before=_require_optional_nonnegative_number(payload["not_before"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ConfigurationError(
                "BlueStacks shutdown intent fields are invalid.",
                state_file=path.name,
            ) from error


class StaleShutdownDisposition(StrEnum):
    """Reports durable phase cleanup reconciliation."""

    BUSY = "stale_shutdown_busy"
    WAITING = "stale_shutdown_waiting"
    CANCELED = "stale_shutdown_canceled"
    CLOSED = "stale_shutdown_closed"
    ALREADY_STOPPED = "stale_shutdown_already_stopped"
    BLOCKED = "stale_shutdown_blocked"
    FAILED = "stale_shutdown_failed"


@dataclass(frozen=True, slots=True)
class StaleShutdownResult:
    """Reports one non-secret abandoned-phase cleanup result."""

    display_name: str
    disposition: StaleShutdownDisposition
    failure_phase: str | None = None


@dataclass(frozen=True, slots=True)
class PowerShellBlueStacksInstanceCloser:
    """Stops one process only when the live process identity still matches the session."""

    running_instance_source: BlueStacksRunningInstanceSource
    process_stopper: BlueStacksProcessStopper = field(default_factory=PowerShellBlueStacksProcessStopper)
    poll_attempts: int = 30
    poll_interval_seconds: float = 2.0
    sleep: Callable[[float], None] = time.sleep
    metadata_path: Path | None = None
    intent_store: InstanceShutdownIntentStore | None = None
    wall_time: Callable[[], float] = time.time
    intent_id_factory: Callable[[], str] = field(default=lambda: uuid.uuid4().hex, repr=False)
    lease_registry_factory: Callable[[], InstanceLeaseRegistry] = field(
        default=InstanceLeaseRegistry,
        repr=False,
    )

    def register_close_intent(
        self,
        instance: BlueStacksInstance,
        *,
        grace_period_seconds: float,
    ) -> str:
        """Persists exact-process intent while the live task still owns its lease."""

        store = self._require_intent_store(instance)
        if self.metadata_path is None:
            raise ConfigurationError(
                "BlueStacks phase cleanup requires host metadata identity.",
                display_name=instance.display_name,
                failure_phase="state_write",
            )
        instance_key, process_id = _require_runtime_identity(instance)
        intent_id = self.intent_id_factory()
        store.save(
            InstanceShutdownIntent(
                display_name=instance.display_name,
                intent_id=intent_id,
                instance_id=instance.id,
                instance_key=instance_key,
                process_id=process_id,
                metadata_path=str(self.metadata_path.resolve()),
                requested_at=self.wall_time(),
                grace_period_seconds=grace_period_seconds,
            )
        )
        return intent_id

    def cancel_close_intent(self, instance: BlueStacksInstance) -> None:
        """Cancels stale phase cleanup when new keep-warm work claims the instance."""

        store = self._require_intent_store(instance)
        instance_key, _process_id = _require_runtime_identity(instance)
        store.remove(display_name=instance.display_name, instance_key=instance_key)

    def finalize_close_intent(self, instance: BlueStacksInstance, *, intent_id: str) -> None:
        """Waits for follow-up work, then reclaims and revalidates before shutdown."""

        store = self._require_intent_store(instance)
        instance_key, _process_id = _require_runtime_identity(instance)
        leases = self.lease_registry_factory()
        try:
            try:
                leases.acquire(display_name=instance.display_name, timeout_seconds=0)
            except InstanceBusyError:
                # Newly queued work won the post-release race. It now owns the
                # decision to cancel or replace this intent.
                return
            current = store.load(display_name=instance.display_name, instance_key=instance_key)
            if current is None or current.intent_id != intent_id:
                return
            armed = replace(
                current,
                not_before=self.wall_time() + current.grace_period_seconds,
            )
            store.save(armed)
        finally:
            leases.release_all()
        remaining_seconds = armed.grace_period_seconds
        while remaining_seconds > 0:
            delay_seconds = min(
                remaining_seconds,
                _SHUTDOWN_INTENT_POLL_INTERVAL_SECONDS,
            )
            self.sleep(delay_seconds)
            remaining_seconds -= delay_seconds
            current = store.load(display_name=instance.display_name, instance_key=instance_key)
            if current is None or current.intent_id != intent_id:
                # A follow-up task made an explicit keep-warm or replacement
                # decision, so this completed task need not wait for the limit.
                return

        leases = self.lease_registry_factory()
        try:
            try:
                leases.acquire(display_name=instance.display_name, timeout_seconds=0)
            except InstanceBusyError:
                # A newly arrived task owns the instance. Its cleanup policy may
                # cancel or replace this intent; otherwise the host monitor retries.
                return
            current = store.load(display_name=instance.display_name, instance_key=instance_key)
            if current is None or current.intent_id != intent_id:
                return
            if current.not_before is None or current.not_before > self.wall_time():
                return
            self.close_instance(instance)
        finally:
            leases.release_all()

    def close_instance(self, instance: BlueStacksInstance) -> None:
        """Rechecks the leased instance before closing it and confirms process exit."""

        instance_key, process_id = _require_runtime_identity(instance)
        running = tuple(
            item
            for item in self.running_instance_source.list_running_instances()
            if item.instance_key == instance_key
        )
        if len(running) != 1 or running[0].process_id != process_id:
            raise ConfigurationError(
                "BlueStacks shutdown was withheld because the resolved process identity changed.",
                display_name=instance.display_name,
                instance_key=instance_key,
                expected_process_id=process_id,
                current_process_ids=tuple(item.process_id for item in running),
                failure_phase="shutdown_revalidation",
            )
        self.process_stopper.stop_process(process_id)
        wait_for_instance_state(
            source=self.running_instance_source,
            instance_key=instance_key,
            running=False,
            attempts=self.poll_attempts,
            interval_seconds=self.poll_interval_seconds,
            sleep=self.sleep,
        )
        if self.intent_store is not None:
            self.intent_store.remove(display_name=instance.display_name, instance_key=instance_key)

    def _require_intent_store(self, instance: BlueStacksInstance) -> InstanceShutdownIntentStore:
        """Returns configured durable state or rejects unsafe lifecycle management."""

        if self.intent_store is None:
            raise ConfigurationError(
                "BlueStacks phase cleanup requires durable shutdown state.",
                display_name=instance.display_name,
                failure_phase="state_write",
            )
        return self.intent_store


@dataclass(slots=True)
class BlueStacksStaleInstanceShutdownReconciler:
    """Closes abandoned phase targets only after acquiring their now-idle lease."""

    config_provider: HostConfigProvider
    resolver: BlueStacksInstanceResolver
    intent_store: InstanceShutdownIntentStore = field(default_factory=InstanceShutdownIntentStore)
    lease_registry_factory: Callable[[], InstanceLeaseRegistry] = InstanceLeaseRegistry
    process_stopper: BlueStacksProcessStopper = field(default_factory=PowerShellBlueStacksProcessStopper)
    poll_attempts: int = 30
    poll_interval_seconds: float = 2.0
    sleep: Callable[[float], None] = time.sleep
    wall_time: Callable[[], float] = time.time

    def reconcile_all(self) -> tuple[StaleShutdownResult, ...]:
        """Reconciles every durable intent without blocking on an active task lease."""

        return tuple(self._reconcile(intent) for intent in self.intent_store.load_all())

    def _reconcile(self, intent: InstanceShutdownIntent) -> StaleShutdownResult:
        """Revalidates authority and exact PID under an exclusive lease before stopping."""

        if intent.not_before is not None and intent.not_before > self.wall_time():
            return StaleShutdownResult(intent.display_name, StaleShutdownDisposition.WAITING)
        leases = self.lease_registry_factory()
        try:
            leases.acquire(display_name=intent.display_name, timeout_seconds=0)
        except InstanceBusyError:
            return StaleShutdownResult(intent.display_name, StaleShutdownDisposition.BUSY)
        try:
            current = self.intent_store.load(
                display_name=intent.display_name,
                instance_key=intent.instance_key,
            )
            if current is None:
                return StaleShutdownResult(intent.display_name, StaleShutdownDisposition.CANCELED)
            if current.intent_id != intent.intent_id:
                return StaleShutdownResult(intent.display_name, StaleShutdownDisposition.WAITING)
            if current.not_before is None:
                self.intent_store.save(
                    replace(
                        current,
                        not_before=self.wall_time() + current.grace_period_seconds,
                    )
                )
                return StaleShutdownResult(intent.display_name, StaleShutdownDisposition.WAITING)
            if current.not_before > self.wall_time():
                return StaleShutdownResult(intent.display_name, StaleShutdownDisposition.WAITING)
            intent = current
            config = self.config_provider()
            resolver = replace(self.resolver, config_path=config.metadata_path)
            if Path(intent.metadata_path).resolve() != config.metadata_path.resolve():
                return self._blocked(intent, "identity_changed")
            try:
                instance_binding = config.require_instance(intent.instance_id)
            except ConfigurationError:
                return self._blocked(intent, "identity_changed")
            if instance_binding.display_name.casefold() != intent.display_name.casefold():
                return self._blocked(intent, "identity_changed")
            roles = config.roles_by_instance().get(intent.instance_id, frozenset())
            if LiveAutomationRole.READ_ONLY in roles or not capabilities_for_roles(roles).allow_instance_launch:
                return self._blocked(intent, "role_revoked")
            catalog = resolver.load_runtime_catalog()
            records = catalog.find_records_by_display_name(intent.display_name)
            if len(records) != 1 or records[0].instance_key != intent.instance_key:
                return self._blocked(intent, "identity_changed")
            running = tuple(
                item for item in catalog.running_instances if item.instance_key == intent.instance_key
            )
            if not running:
                self.intent_store.remove(
                    display_name=intent.display_name,
                    instance_key=intent.instance_key,
                )
                return StaleShutdownResult(
                    intent.display_name,
                    StaleShutdownDisposition.ALREADY_STOPPED,
                )
            if len(running) != 1 or running[0].process_id != intent.process_id:
                return self._blocked(intent, "identity_changed")
            closer = PowerShellBlueStacksInstanceCloser(
                running_instance_source=resolver.running_instance_source,
                process_stopper=self.process_stopper,
                poll_attempts=self.poll_attempts,
                poll_interval_seconds=self.poll_interval_seconds,
                sleep=self.sleep,
                metadata_path=config.metadata_path,
                intent_store=self.intent_store,
                wall_time=self.wall_time,
            )
            closer.close_instance(
                BlueStacksInstance(
                    id=intent.instance_id,
                    display_name=intent.display_name,
                    device_id="",
                    app_package="",
                    host_instance_key=intent.instance_key,
                    process_id=intent.process_id,
                )
            )
            return StaleShutdownResult(intent.display_name, StaleShutdownDisposition.CLOSED)
        except Exception as error:
            details = getattr(error, "details", {})
            phase = details.get("failure_phase") if isinstance(details, dict) else None
            return StaleShutdownResult(
                intent.display_name,
                StaleShutdownDisposition.FAILED,
                phase if isinstance(phase, str) else "shutdown",
            )
        finally:
            leases.release_all()

    def _blocked(self, intent: InstanceShutdownIntent, phase: str) -> StaleShutdownResult:
        """Invalidates an unsafe old intent instead of targeting a replacement process."""

        self.intent_store.remove(display_name=intent.display_name, instance_key=intent.instance_key)
        return StaleShutdownResult(intent.display_name, StaleShutdownDisposition.BLOCKED, phase)


def _require_runtime_identity(instance: BlueStacksInstance) -> tuple[str, int]:
    """Returns the host identity needed for safe shutdown."""

    if instance.host_instance_key is None or instance.process_id is None:
        raise ConfigurationError(
            "BlueStacks shutdown requires a resolved host instance key and process identity.",
            display_name=instance.display_name,
            instance_key=instance.host_instance_key,
            process_id=instance.process_id,
            failure_phase="shutdown_identity",
        )
    return instance.host_instance_key, instance.process_id


def _serialize_shutdown_intent(record: InstanceShutdownIntent) -> dict[str, object]:
    """Builds the strict persisted shutdown-intent schema."""

    return {
        "display_name": record.display_name,
        "intent_id": record.intent_id,
        "instance_id": record.instance_id,
        "instance_key": record.instance_key,
        "process_id": record.process_id,
        "metadata_path": record.metadata_path,
        "requested_at": record.requested_at,
        "grace_period_seconds": record.grace_period_seconds,
        "not_before": record.not_before,
    }


def _require_string(value: Any) -> str:
    """Validates one required persisted string."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected non-empty string")
    return value


def _require_positive_int(value: Any) -> int:
    """Validates one required persisted PID."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("expected positive integer")
    return value


def _require_nonnegative_number(value: Any) -> float:
    """Validates one persisted wall-clock timestamp."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected finite number")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError("expected finite non-negative number")
    return numeric


def _require_optional_nonnegative_number(value: Any) -> float | None:
    """Validates one optional persisted wall-clock timestamp."""

    if value is None:
        return None
    return _require_nonnegative_number(value)
