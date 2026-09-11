"""Conservative, durable memory-pressure recovery for BlueStacks instances."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pnc_automation.bluestacks_management.instance_lease import DEFAULT_INSTANCE_LEASE_ROOT, InstanceLeaseRegistry
from pnc_automation.bluestacks_management.process_control import run_powershell, wait_for_instance_state
from pnc_automation.bluestacks_management.recovery_state import (
    MAX_PERSISTED_LAUNCH_ATTEMPTS,
    InstanceRecoveryRecord,
    RecoveryStateStore,
)
from pnc_automation.core.config.host import (
    BlueStacksHostConfig,
    BlueStacksMemoryPolicy,
    is_memory_restart_eligible,
)
from pnc_automation.core.errors import ConfigurationError, InstanceBusyError
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksInstanceResolver,
    BlueStacksRunningInstance,
    BlueStacksRuntimeCatalog,
)


class BlueStacksProcessStopper(Protocol):
    """Stops one exact player PID selected under its instance lease."""

    def stop_process(self, process_id: int) -> None:
        """Requests a bounded stop or raises a host-control error."""


@dataclass(frozen=True, slots=True)
class PowerShellBlueStacksProcessStopper:
    """Requests graceful player closure followed by a bounded forced fallback."""

    powershell_path: str = "powershell"
    timeout_seconds: float = 35.0

    def stop_process(self, process_id: int) -> None:
        """Stops the previously revalidated PID without unbounded subprocess waits."""

        script = (
            f"$process = Get-Process -Id {process_id} -ErrorAction Stop; "
            "$closed = $process.CloseMainWindow(); "
            "if ($closed) { "
            "Wait-Process -Id $process.Id -Timeout 20 -ErrorAction SilentlyContinue; "
            "$process = Get-Process -Id $process.Id -ErrorAction SilentlyContinue }; "
            "if ($null -ne $process) { Stop-Process -Id $process.Id -Force -ErrorAction Stop }"
        )
        run_powershell(
            powershell_path=self.powershell_path,
            script=script,
            timeout_seconds=self.timeout_seconds,
            failure_message="Failed to stop the BlueStacks player process.",
            failure_phase="stop",
        )


class MemoryMonitorDisposition(StrEnum):
    """Reports health separately from pending, blocked, and exhausted recovery."""

    HEALTHY = "healthy"
    OVER_LIMIT = "over_limit"
    COOLDOWN = "cooldown"
    BUSY = "busy"
    RESTARTED = "restarted"
    RESTART_FAILED = "restart_failed"
    RECOVERY_PENDING = "recovery_pending"
    RECOVERY_COMPLETED = "recovery_completed"
    RECOVERY_BLOCKED = "recovery_blocked"
    RECOVERY_EXHAUSTED = "recovery_exhausted"
    MEMORY_UNAVAILABLE = "memory_unavailable"


@dataclass(frozen=True, slots=True)
class MemoryMonitorResult:
    """Contains only non-secret instance identity, measurements, and failure phases."""

    display_name: str
    working_set_mb: float | None
    consecutive_over_limit_samples: int
    disposition: MemoryMonitorDisposition
    failure_phase: str | None = None


class HostConfigProvider(Protocol):
    """Supplies freshly validated host configuration, without game configuration."""

    def __call__(self) -> BlueStacksHostConfig:
        """Loads the current authority or fails closed."""


@dataclass(slots=True)
class BlueStacksInstanceMemoryMonitor:
    """Serializes every recovery transition under the physical instance lease."""

    config_provider: HostConfigProvider
    resolver: BlueStacksInstanceResolver
    lease_registry_factory: Callable[[], InstanceLeaseRegistry] = InstanceLeaseRegistry
    process_stopper: BlueStacksProcessStopper = field(default_factory=PowerShellBlueStacksProcessStopper)
    recovery_store: RecoveryStateStore = field(
        default_factory=lambda: RecoveryStateStore(DEFAULT_INSTANCE_LEASE_ROOT / "state")
    )
    sleep: Callable[[float], None] = time.sleep
    wall_time: Callable[[], float] = time.time
    restart_poll_attempts: int = 30
    restart_poll_interval_seconds: float = 2.0
    restart_launch_attempts: int = 3
    policy: BlueStacksMemoryPolicy = field(default_factory=BlueStacksMemoryPolicy, init=False)
    eligible_display_names: frozenset[str] = field(default_factory=frozenset, init=False)
    _over_limit_counts: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _active_config: BlueStacksHostConfig | None = field(default=None, init=False, repr=False)

    def sample_once(self) -> tuple[MemoryMonitorResult, ...]:
        """Reconciles durable intents before considering new running-instance pressure."""

        self._reload_config()
        pending = self.recovery_store.load_all()
        results = [self._reconcile_pending(record) for record in pending]
        if not self.policy.enabled:
            return tuple(results)
        catalog = self.resolver.load_runtime_catalog()
        metadata_path = self.resolver.config_path.resolve()
        pending_names = {record.display_name.casefold() for record in pending}
        names_seen: set[str] = set()
        for running in catalog.running_instances:
            matches = tuple(record for record in catalog.records if record.instance_key == running.instance_key)
            if len(matches) != 1:
                continue
            display_name = matches[0].display_name
            if display_name not in self.eligible_display_names or display_name.casefold() in pending_names:
                continue
            names_seen.add(display_name)
            results.append(self._evaluate_running(display_name, running, metadata_path))
        for display_name in set(self._over_limit_counts) - names_seen:
            self._over_limit_counts.pop(display_name, None)
        return tuple(results)

    def watch(self) -> None:
        """Samples continuously; the CLI owns result logging and supervision."""

        while True:
            self.sample_once()
            self.sleep(self.policy.sample_interval_seconds)

    def _reload_config(self) -> None:
        """Changes policy immediately and lets invalid reloads reach the supervisor."""

        try:
            config = self.config_provider()
        except Exception as error:
            raise ConfigurationError("BlueStacks host configuration reload failed.", failure_phase="config_reload") from error
        if config != self._active_config:
            self._over_limit_counts.clear()
        roles = config.roles_by_instance()
        self.eligible_display_names = frozenset(
            instance.display_name
            for instance in config.instances
            if is_memory_restart_eligible(roles.get(instance.id, frozenset()), config.memory_policy.restart_roles)
        )
        self.policy = config.memory_policy
        self.resolver = replace(self.resolver, config_path=config.metadata_path)
        self._active_config = config

    def _evaluate_running(
        self, display_name: str, running: BlueStacksRunningInstance, metadata_path: Path
    ) -> MemoryMonitorResult:
        """Requires sustained pressure, then rechecks all inputs under ownership."""

        mb = _working_set_mb(running)
        if mb is None or mb <= self.policy.max_working_set_mb:
            self._over_limit_counts.pop(display_name, None)
            disposition = MemoryMonitorDisposition.MEMORY_UNAVAILABLE if mb is None else MemoryMonitorDisposition.HEALTHY
            return self._result(display_name, mb, disposition)
        count = self._over_limit_counts.get(display_name, 0) + 1
        self._over_limit_counts[display_name] = count
        if count < self.policy.consecutive_over_limit_samples:
            return self._result(display_name, mb, MemoryMonitorDisposition.OVER_LIMIT)
        leases = self.lease_registry_factory()
        try:
            leases.acquire(display_name=display_name, timeout_seconds=0)
            self._reload_config()
            if not self._authorized(display_name):
                return self._result(display_name, mb, MemoryMonitorDisposition.RECOVERY_BLOCKED, "role_revoked")
            if self._over_limit_counts.get(display_name, 0) < self.policy.consecutive_over_limit_samples:
                return self._result(display_name, mb, MemoryMonitorDisposition.OVER_LIMIT)
            # A competing monitor may have committed intent/cooldown after our snapshot.
            if self._pending_for_display(display_name):
                return self._result(display_name, mb, MemoryMonitorDisposition.RECOVERY_PENDING)
            last_restart = self.recovery_store.load_cooldown(display_name)
            if last_restart is not None and self.wall_time() - last_restart < self.policy.restart_cooldown_seconds:
                return self._result(display_name, mb, MemoryMonitorDisposition.COOLDOWN)
            catalog = self.resolver.load_runtime_catalog()
            record = InstanceRecoveryRecord(
                display_name=display_name,
                instance_key=running.instance_key,
                metadata_path=str(metadata_path),
                original_pid=running.process_id,
                stop_intent=True,
            )
            if not self._identity_matches(record, catalog):
                return self._result(display_name, mb, MemoryMonitorDisposition.RECOVERY_BLOCKED, "identity_changed")
            current = tuple(item for item in catalog.running_instances if item.instance_key == running.instance_key)
            if len(current) != 1 or current[0].process_id != running.process_id:
                self._over_limit_counts.pop(display_name, None)
                return self._result(display_name, mb, MemoryMonitorDisposition.OVER_LIMIT)
            current_mb = _working_set_mb(current[0])
            if current_mb is None or current_mb <= self.policy.max_working_set_mb:
                self._over_limit_counts.pop(display_name, None)
                disposition = MemoryMonitorDisposition.MEMORY_UNAVAILABLE if current_mb is None else MemoryMonitorDisposition.HEALTHY
                return self._result(display_name, current_mb, disposition)
            self.recovery_store.save(record)  # No stop is allowed if this commit fails.
            try:
                self.process_stopper.stop_process(running.process_id)
                self._wait_for_state(running.instance_key, running=False)
            except Exception:
                record = record.with_failure(phase="stop", next_retry_at=None)
                self.recovery_store.save(record)
            self._over_limit_counts.pop(display_name, None)
            return self._recover_locked(record, initial_restart=True)
        except InstanceBusyError:
            return self._result(display_name, mb, MemoryMonitorDisposition.BUSY)
        finally:
            leases.release_all()

    def _reconcile_pending(self, snapshot: InstanceRecoveryRecord) -> MemoryMonitorResult:
        """Reloads intent under its lease, including completion and blocked-state writes."""

        leases = self.lease_registry_factory()
        try:
            leases.acquire(display_name=snapshot.display_name, timeout_seconds=0)
            current = self._pending_for_display(snapshot.display_name)
            record = next((item for item in current if item.instance_key == snapshot.instance_key), None)
            if record is None:
                return self._result(snapshot.display_name, None, MemoryMonitorDisposition.RECOVERY_COMPLETED)
            return self._recover_locked(record, initial_restart=False)
        except InstanceBusyError:
            return self._result(snapshot.display_name, None, MemoryMonitorDisposition.BUSY)
        finally:
            leases.release_all()

    def _recover_locked(self, record: InstanceRecoveryRecord, *, initial_restart: bool) -> MemoryMonitorResult:
        """Recovers only recorded open instances; every retry revalidates fresh authority."""

        limit = min(3, max(1, self.restart_launch_attempts))
        launches = 0
        while True:
            self._reload_config()
            if not self.policy.enabled:
                return self._blocked(record, "policy_disabled")
            catalog = self.resolver.load_runtime_catalog()
            if not self._identity_matches(record, catalog):
                return self._blocked(record, "identity_changed")
            matching = tuple(item for item in catalog.running_instances if item.instance_key == record.instance_key)
            original_present = any(item.process_id == record.original_pid for item in catalog.running_instances)
            if original_present or len(matching) > 1:
                return self._failed(record, "stop_wait")
            if matching:
                # Includes a late launch, or an external relaunch after budget exhaustion.
                self.recovery_store.save_cooldown(record.display_name, self.wall_time())
                self.recovery_store.remove(record)
                disposition = MemoryMonitorDisposition.RESTARTED if initial_restart else MemoryMonitorDisposition.RECOVERY_COMPLETED
                return self._result(record.display_name, _working_set_mb(matching[0]), disposition)
            if not record.stop_intent:
                return self._blocked(record, "stop_wait")
            if not self._authorized(record.display_name):
                return self._blocked(record, "role_revoked")
            # The monitor may have crashed after stopping but before confirming the stop.
            if not record.stop_confirmed:
                record = replace(record, stop_confirmed=True)
                self.recovery_store.save(record)
            if record.launch_attempts >= MAX_PERSISTED_LAUNCH_ATTEMPTS:
                record = record.with_failure(phase="launch_budget_exhausted", next_retry_at=None)
                self.recovery_store.save(record)
                return self._result(record.display_name, None, MemoryMonitorDisposition.RECOVERY_EXHAUSTED, "launch_budget_exhausted")
            if launches >= limit:
                return self._failed(record, record.failure_phase or "launch")
            if launches == 0 and record.next_retry_at is not None and record.next_retry_at > self.wall_time():
                return self._result(record.display_name, None, MemoryMonitorDisposition.RECOVERY_PENDING, record.failure_phase)
            record = replace(
                record,
                launch_attempts=record.launch_attempts + 1,
                failure_phase="launch",
                next_retry_at=self.wall_time() + self.policy.sample_interval_seconds,
            )
            self.recovery_store.save(record)  # Count before launch, even if the process dies here.
            launches += 1
            try:
                self.resolver.instance_launcher.launch_instance(record.instance_key)
            except Exception:
                continue
            try:
                self._wait_for_state(record.instance_key, running=True)
            except Exception:
                record = record.with_failure(phase="launch_wait", next_retry_at=record.next_retry_at)
                self.recovery_store.save(record)
            # Fresh discovery on the next iteration prevents duplicate launches after timeout.

    def _pending_for_display(self, display_name: str) -> tuple[InstanceRecoveryRecord, ...]:
        """Finds all existing intents before allowing a new stop for this display."""

        return tuple(
            record for record in self.recovery_store.load_all()
            if record.display_name.casefold() == display_name.casefold()
        )

    def _identity_matches(self, record: InstanceRecoveryRecord, catalog: BlueStacksRuntimeCatalog) -> bool:
        """Prevents a changed metadata path or display mapping from redirecting recovery."""

        matches = catalog.find_records_by_display_name(record.display_name)
        return (
            self.resolver.config_path.resolve() == Path(record.metadata_path).resolve()
            and len(matches) == 1
            and matches[0].instance_key == record.instance_key
        )

    def _authorized(self, display_name: str) -> bool:
        """Applies the freshly loaded canonical role predicate."""

        return self.policy.enabled and display_name in self.eligible_display_names

    def _blocked(self, record: InstanceRecoveryRecord, phase: str) -> MemoryMonitorResult:
        """Retains blocked intent without resetting its retry budget or retry time."""

        self.recovery_store.save(record.with_failure(phase=phase, next_retry_at=record.next_retry_at))
        return self._result(record.display_name, None, MemoryMonitorDisposition.RECOVERY_BLOCKED, phase)

    def _failed(self, record: InstanceRecoveryRecord, phase: str) -> MemoryMonitorResult:
        """Retains per-instance failure while allowing other instances to be monitored."""

        self.recovery_store.save(record.with_failure(phase=phase, next_retry_at=record.next_retry_at))
        return self._result(record.display_name, None, MemoryMonitorDisposition.RESTART_FAILED, phase)

    def _wait_for_state(self, instance_key: str, *, running: bool) -> None:
        """Uses bounded process discovery for startup and shutdown confirmation."""

        wait_for_instance_state(
            source=self.resolver.running_instance_source,
            instance_key=instance_key,
            running=running,
            attempts=self.restart_poll_attempts,
            interval_seconds=self.restart_poll_interval_seconds,
            sleep=self.sleep,
        )

    def _result(
        self,
        display_name: str,
        working_set_mb: float | None,
        disposition: MemoryMonitorDisposition,
        failure_phase: str | None = None,
    ) -> MemoryMonitorResult:
        """Builds a stable rounded result without raw subprocess/config diagnostics."""

        return MemoryMonitorResult(
            display_name=display_name,
            working_set_mb=None if working_set_mb is None else round(working_set_mb, 1),
            consecutive_over_limit_samples=self._over_limit_counts.get(display_name, 0),
            disposition=disposition,
            failure_phase=failure_phase,
        )


def _working_set_mb(instance: BlueStacksRunningInstance) -> float | None:
    """Converts an optional process working set to megabytes."""

    return None if instance.working_set_bytes is None else instance.working_set_bytes / (1024 * 1024)
