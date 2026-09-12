"""Bounded host-process controls shared by monitor and fleet recovery."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksRunningInstanceSource,
)


def run_powershell(
    *,
    powershell_path: str,
    script: str,
    timeout_seconds: float,
    failure_message: str,
    failure_phase: str,
) -> subprocess.CompletedProcess[str]:
    """Runs one host PowerShell operation with a bounded timeout and safe diagnostics."""

    try:
        completed = subprocess.run(
            [powershell_path, "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise ConfigurationError(
            failure_message,
            failure_phase=failure_phase,
            timeout_seconds=timeout_seconds,
            timed_out=True,
        ) from error
    if completed.returncode != 0:
        raise ConfigurationError(
            failure_message,
            failure_phase=failure_phase,
            returncode=completed.returncode,
        )
    return completed


def wait_for_instance_state(
    *,
    source: BlueStacksRunningInstanceSource,
    instance_key: str,
    running: bool,
    attempts: int,
    interval_seconds: float,
    sleep: Callable[[float], None],
) -> None:
    """Polls a bounded process snapshot for one exact instance state."""

    bounded_attempts = max(1, attempts)
    discovery_failures = 0
    last_discovery_error: ConfigurationError | None = None
    for attempt_index in range(bounded_attempts):
        try:
            present = any(item.instance_key == instance_key for item in source.list_running_instances())
        except ConfigurationError as error:
            # A process can disappear between the CIM query and property
            # materialization during stop/start. Retry the whole snapshot, but
            # never infer target state from an incomplete row.
            discovery_failures += 1
            last_discovery_error = error
        else:
            last_discovery_error = None
            if present is running:
                return
        if attempt_index < bounded_attempts - 1 and interval_seconds > 0:
            sleep(interval_seconds)
    expected = "start" if running else "stop"
    if last_discovery_error is not None:
        failure_phase = "launch_wait" if running else "stop_wait"
        raise ConfigurationError(
            f"BlueStacks instance '{instance_key}' {expected} could not be confirmed because process discovery failed.",
            instance_key=instance_key,
            expected_running=running,
            state_poll_attempts=bounded_attempts,
            discovery_failures=discovery_failures,
            failure_phase=failure_phase,
        ) from last_discovery_error
    raise ConfigurationError(
        f"BlueStacks instance '{instance_key}' did not {expected} during recovery.",
        instance_key=instance_key,
        expected_running=running,
        state_poll_attempts=bounded_attempts,
    )
