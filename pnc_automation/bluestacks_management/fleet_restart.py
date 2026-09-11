"""Exclusive whole-fleet BlueStacks restart orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time as datetime_time
from zoneinfo import ZoneInfo

from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry
from pnc_automation.bluestacks_management.instance_memory_monitor import (
    BlueStacksProcessStopper,
    PowerShellBlueStacksProcessStopper,
)
from pnc_automation.bluestacks_management.process_control import wait_for_instance_state
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksInstanceResolver,
    BlueStacksRunningInstance,
    BlueStacksRuntimeInstanceRecord,
)

TORONTO_MAINTENANCE_ZONE = ZoneInfo("America/Toronto")
MAINTENANCE_BOUNDARY_START = datetime_time(hour=1, minute=55)
MAINTENANCE_PRE_STOP_DEADLINE = datetime_time(hour=1, minute=58)
MAINTENANCE_WINDOW_END = datetime_time(hour=2)


def _as_toronto(now: datetime) -> datetime:
    """Normalizes aware and default-style naive clocks to Toronto-aware time."""

    if now.tzinfo is None:
        now = now.replace(tzinfo=TORONTO_MAINTENANCE_ZONE)
    return now.astimezone(TORONTO_MAINTENANCE_ZONE)


def is_maintenance_window(now: datetime | None = None) -> bool:
    """Returns whether the current time is inside the scheduled 01:55-02:00 window."""

    local_now = _as_toronto(datetime.now(tz=TORONTO_MAINTENANCE_ZONE) if now is None else now)
    return MAINTENANCE_BOUNDARY_START <= local_now.timetz().replace(tzinfo=None) < MAINTENANCE_WINDOW_END


def current_maintenance_pre_stop_deadline(now: datetime | None = None) -> datetime | None:
    """Returns the hard 01:58 Toronto stop deadline for the 01:55 maintenance window."""

    local_now = _as_toronto(datetime.now(tz=TORONTO_MAINTENANCE_ZONE) if now is None else now)
    local_time = local_now.timetz().replace(tzinfo=None)
    if MAINTENANCE_BOUNDARY_START <= local_time < MAINTENANCE_WINDOW_END:
        return datetime.combine(
            local_now.date(),
            MAINTENANCE_PRE_STOP_DEADLINE,
            tzinfo=TORONTO_MAINTENANCE_ZONE,
        )
    return None


@dataclass(frozen=True, slots=True)
class BlueStacksFleetRestartFailure:
    """Describes one structured partial failure without exposing host secrets."""

    display_name: str
    phase: str
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BlueStacksFleetRestartResult:
    """Reports displays that were actually stopped and relaunched by maintenance."""

    display_names: tuple[str, ...]
    previously_running: tuple[str, ...]
    failures: tuple[BlueStacksFleetRestartFailure, ...] = ()

    @property
    def succeeded(self) -> bool:
        """Returns whether every selected open instance completed without a recorded failure."""

        return not self.failures


@dataclass(slots=True)
class BlueStacksFleetRestarter:
    """Restarts a complete configured display-name bundle under exclusive ownership."""

    resolver: BlueStacksInstanceResolver
    process_stopper: BlueStacksProcessStopper = field(default_factory=PowerShellBlueStacksProcessStopper)
    lease_registry_factory: Callable[[], InstanceLeaseRegistry] = InstanceLeaseRegistry
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = field(
        default_factory=lambda: lambda: datetime.now(tz=TORONTO_MAINTENANCE_ZONE)
    )
    state_poll_attempts: int = 30
    state_poll_interval_seconds: float = 2.0

    def restart_running(
        self,
        display_names: tuple[str, ...],
        *,
        lease_timeout_seconds: float = 120.0,
        pre_stop_deadline: datetime | None = None,
    ) -> BlueStacksFleetRestartResult:
        """Snapshots and restarts only named instances that are currently running.

        The complete configured bundle is leased before host discovery. Once one
        process has been stopped, all recovery attempts continue even after the
        optional pre-stop deadline or an earlier stop/launch failure.
        """

        normalized = tuple(name.strip() for name in display_names)
        if not normalized or any(not name for name in normalized):
            raise ValueError("At least one non-empty BlueStacks display name is required.")
        if len({name.casefold() for name in normalized}) != len(normalized):
            raise ValueError("Fleet restart display names must be unique.")
        if pre_stop_deadline is not None and pre_stop_deadline.tzinfo is None:
            raise ValueError("Fleet restart pre_stop_deadline must be timezone-aware.")

        leases = self.lease_registry_factory()
        try:
            leases.acquire_many(normalized, timeout_seconds=lease_timeout_seconds)
            initial_catalog = self.resolver.load_runtime_catalog()
            targets_by_key = _validate_and_index_runtime_targets(
                normalized,
                initial_catalog.records,
            )
            configured_names = {name.casefold() for name in normalized}
            initial_targets = tuple(
                _FleetTarget(
                    display_name=record.display_name,
                    instance_key=running.instance_key,
                    process_id=running.process_id,
                )
                for running in initial_catalog.running_instances
                if (record := targets_by_key.get(running.instance_key)) is not None
                and record.display_name.casefold() in configured_names
            )
            if not initial_targets:
                return BlueStacksFleetRestartResult(display_names=(), previously_running=())

            stopped: list[_FleetTarget] = []
            confirmed_stopped: list[_FleetTarget] = []
            stop_revalidation_failures: set[str] = set()
            failures: list[BlueStacksFleetRestartFailure] = []

            restarted_names: list[str] = []
            try:
                for target in initial_targets:
                    if (
                        pre_stop_deadline is not None
                        and _as_toronto(self.now()) >= _as_toronto(pre_stop_deadline)
                    ):
                        failures.append(_pre_stop_deadline_failure(target, pre_stop_deadline))
                        continue
                    try:
                        running_snapshot = self.resolver.running_instance_source.list_running_instances()
                    except Exception as error:
                        failures.append(_failure(target.display_name, "stop_revalidation", error))
                        continue
                    current = _find_exact_running_instance(running_snapshot, target)
                    if current is None:
                        same_key = tuple(
                            item for item in running_snapshot if item.instance_key == target.instance_key
                        )
                        same_pid = any(item.process_id == target.process_id for item in running_snapshot)
                        if same_key or same_pid:
                            failures.append(
                                BlueStacksFleetRestartFailure(
                                    display_name=target.display_name,
                                    phase="stop_revalidation",
                                    message="The exact instance PID/identity changed before the stop request.",
                                    details={
                                        "instance_key": target.instance_key,
                                        "expected_process_id": target.process_id,
                                    },
                                )
                            )
                            continue
                        # The initial open target is already stopped. It is safe to
                        # recover it because the initial snapshot, not this sample,
                        # authorizes the relaunch.
                        stopped.append(target)
                        confirmed_stopped.append(target)
                        continue
                    if (
                        pre_stop_deadline is not None
                        and _as_toronto(self.now()) >= _as_toronto(pre_stop_deadline)
                    ):
                        failures.append(_pre_stop_deadline_failure(target, pre_stop_deadline))
                        continue
                    try:
                        self.process_stopper.stop_process(current.process_id)
                    except Exception as error:
                        failures.append(_failure(target.display_name, "stop", error))
                        stopped.append(target)
                        try:
                            if self._is_confirmed_stopped(target):
                                confirmed_stopped.append(target)
                            else:
                                stop_revalidation_failures.add(target.instance_key)
                                failures.append(_stop_not_confirmed_failure(target))
                        except Exception as revalidation_error:
                            stop_revalidation_failures.add(target.instance_key)
                            failures.append(
                                _failure(target.display_name, "stop_revalidation", revalidation_error)
                            )
                        continue
                    stopped.append(target)
                    try:
                        self._wait_for_state(instance_key=target.instance_key, running=False)
                    except Exception as error:
                        failures.append(_failure(target.display_name, "stop_wait", error))
                    try:
                        if not self._is_confirmed_stopped(target):
                            stop_revalidation_failures.add(target.instance_key)
                            failures.append(
                                _stop_not_confirmed_failure(target)
                            )
                            continue
                    except Exception as error:
                        stop_revalidation_failures.add(target.instance_key)
                        failures.append(_failure(target.display_name, "stop_revalidation", error))
                        continue
                    confirmed_stopped.append(target)
            finally:
                # Recovery belongs inside the lease-protected region and must
                # still run when a later target's enumeration or revalidation
                # raises unexpectedly.
                confirmed_keys = {target.instance_key for target in confirmed_stopped}
                for target in stopped:
                    if target.instance_key not in confirmed_keys:
                        # A transient discovery error during the ordinary stop
                        # path must not strand a target that is now confirmed
                        # stopped. Revalidate every stop attempt once more while
                        # the complete fleet lease is still held.
                        try:
                            if not self._is_confirmed_stopped(target):
                                if target.instance_key not in stop_revalidation_failures:
                                    failures.append(_stop_not_confirmed_failure(target))
                                continue
                        except Exception as error:
                            if target.instance_key not in stop_revalidation_failures:
                                failures.append(_failure(target.display_name, "stop_revalidation", error))
                            continue
                        confirmed_keys.add(target.instance_key)
                    try:
                        launch_allowed = self._revalidate_before_launch(target)
                    except Exception as error:
                        failures.append(_failure(target.display_name, "launch_revalidation", error))
                        continue
                    if not launch_allowed:
                        failures.append(
                            BlueStacksFleetRestartFailure(
                                display_name=target.display_name,
                                phase="launch_revalidation",
                                message=(
                                    "A BlueStacks process for the recorded instance identity is already "
                                    "running, so relaunch was withheld."
                                ),
                                details={
                                    "instance_key": target.instance_key,
                                    "expected_process_id": target.process_id,
                                },
                            )
                        )
                        continue
                    try:
                        self.resolver.instance_launcher.launch_instance(target.instance_key)
                    except Exception as error:
                        failures.append(_failure(target.display_name, "launch", error))
                        continue
                    try:
                        self._wait_for_state(instance_key=target.instance_key, running=True)
                    except Exception as error:
                        failures.append(_failure(target.display_name, "launch_wait", error))
                        continue
                    restarted_names.append(target.display_name)

            return BlueStacksFleetRestartResult(
                display_names=tuple(restarted_names),
                previously_running=tuple(target.display_name for target in initial_targets),
                failures=tuple(failures),
            )
        finally:
            leases.release_all()

    def _wait_for_state(self, *, instance_key: str, running: bool) -> None:
        """Waits boundedly for one exact player process state."""

        wait_for_instance_state(
            source=self.resolver.running_instance_source,
            instance_key=instance_key,
            running=running,
            attempts=self.state_poll_attempts,
            interval_seconds=self.state_poll_interval_seconds,
            sleep=self.sleep,
        )

    def _is_confirmed_stopped(self, target: _FleetTarget) -> bool:
        """Returns whether no process for the stopped instance identity remains visible."""

        return not any(
            item.instance_key == target.instance_key or item.process_id == target.process_id
            for item in self.resolver.running_instance_source.list_running_instances()
        )

    def _revalidate_before_launch(self, target: _FleetTarget) -> bool:
        """Checks current metadata and process presence immediately before relaunch."""

        records = tuple(
            record
            for record in self.resolver.load_runtime_instances()
            if record.display_name is not None
            and record.display_name.casefold() == target.display_name.casefold()
        )
        if len(records) != 1 or records[0].instance_key != target.instance_key:
            raise ConfigurationError(
                "BlueStacks metadata no longer maps the recorded display to the same instance.",
                display_name=target.display_name,
                expected_instance_key=target.instance_key,
                matching_instance_keys=tuple(record.instance_key for record in records),
            )
        running = self.resolver.running_instance_source.list_running_instances()
        return not any(
            item.instance_key == target.instance_key or item.process_id == target.process_id
            for item in running
        )


@dataclass(frozen=True, slots=True)
class _FleetTarget:
    """Captures the exact instance identity selected by the initial open snapshot."""

    display_name: str
    instance_key: str
    process_id: int


def _validate_and_index_runtime_targets(
    display_names: tuple[str, ...],
    records: tuple[BlueStacksRuntimeInstanceRecord, ...],
) -> dict[str, BlueStacksRuntimeInstanceRecord]:
    """Validates the post-lease display-name to instance-key mapping used by fleet recovery."""

    matched_by_key: dict[str, BlueStacksRuntimeInstanceRecord] = {}
    matched_display_names: dict[str, str] = {}
    for display_name in display_names:
        matches = tuple(
            record
            for record in records
            if record.display_name is not None
            and record.display_name.casefold() == display_name.casefold()
        )
        if len(matches) != 1:
            raise ConfigurationError(
                f"BlueStacks display name '{display_name}' is not uniquely mapped after lease acquisition.",
                display_name=display_name,
                matching_instance_keys=tuple(record.instance_key for record in matches),
            )
        record = matches[0]
        instance_key = record.instance_key
        prior_display_name = matched_display_names.get(instance_key)
        if prior_display_name is not None:
            raise ConfigurationError(
                "Fleet restart display names resolve to the same BlueStacks instance key.",
                display_names=(prior_display_name, display_name),
                instance_key=instance_key,
            )
        matched_display_names[instance_key] = display_name
        matched_by_key[instance_key] = record
    return matched_by_key


def _find_exact_running_instance(
    running_instances: tuple[BlueStacksRunningInstance, ...],
    target: _FleetTarget,
) -> BlueStacksRunningInstance | None:
    """Revalidates the exact host process identity immediately before stopping."""

    matches = tuple(item for item in running_instances if item.instance_key == target.instance_key)
    if len(matches) != 1 or matches[0].process_id != target.process_id:
        return None
    return matches[0]


def _failure(display_name: str, phase: str, error: Exception) -> BlueStacksFleetRestartFailure:
    """Converts one operational error to structured non-secret failure data."""

    return BlueStacksFleetRestartFailure(
        display_name=display_name,
        phase=phase,
        message=f"BlueStacks fleet {phase} operation failed.",
        details={"error_type": type(error).__name__},
    )


def _stop_not_confirmed_failure(target: _FleetTarget) -> BlueStacksFleetRestartFailure:
    """Builds the safe result for a stop whose old process identity remains visible."""

    return BlueStacksFleetRestartFailure(
        display_name=target.display_name,
        phase="stop_revalidation",
        message=(
            "Stop completion was not confirmed; the old BlueStacks instance identity "
            "is still present, so relaunch was withheld."
        ),
        details={
            "instance_key": target.instance_key,
            "expected_process_id": target.process_id,
        },
    )


def _pre_stop_deadline_failure(
    target: _FleetTarget,
    pre_stop_deadline: datetime,
) -> BlueStacksFleetRestartFailure:
    """Builds the safe result for a stop request that crossed the maintenance cutoff."""

    return BlueStacksFleetRestartFailure(
        display_name=target.display_name,
        phase="pre_stop_deadline",
        message="The fleet stop deadline passed before this stop request.",
        details={"pre_stop_deadline": pre_stop_deadline.isoformat()},
    )
