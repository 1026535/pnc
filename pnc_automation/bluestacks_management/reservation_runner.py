"""Run an existing command inside a managed BlueStacks reservation scope.

For example::

    py -m pnc_automation.bluestacks_management run-reserved \
        --instance "Instance A" --scope-id "daily-check" -- \
        py tools/existing_check.py

The child inherits ``PNC_INSTANCE_RESERVATION_RECEIPT``. New and existing
reservations are renewed while the command runs and kept active after it exits
unless ``release_on_exit`` marks terminal scope completion.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import time

from pnc_automation.bluestacks_management.instance_lease import (
    DEFAULT_INSTANCE_LEASE_ROOT,
    InstanceLeaseRegistry,
)
from pnc_automation.bluestacks_management.instance_reservation import (
    RESERVATION_RECEIPT_ENV,
    resolve_reservation_duration,
)
from pnc_automation.core.config.host import (
    BlueStacksHostConfig,
    load_bluestacks_host_config,
)
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.lifecycle import close_preserving_error


@dataclass(frozen=True, slots=True)
class ReservedCommandResult:
    """Carries the child exit code and any receipt for a retained reservation."""

    return_code: int
    retained_receipt_path: Path | None


def run_reserved_command(
    command: Sequence[str | os.PathLike[str]],
    *,
    instances: Sequence[str] | None = None,
    scope_id: str | None = None,
    owner_label: str = "agent",
    config_path: str | Path = "config/accounts.yaml",
    lease_root: Path = DEFAULT_INSTANCE_LEASE_ROOT,
    duration_seconds: float | None = None,
    receipt_path: str | Path | None = None,
    release_on_exit: bool = False,
) -> ReservedCommandResult:
    """Runs a command with a claimed or resumed reservation and safe cleanup.

    With no receipt, ``instances`` and ``scope_id`` are required. New and
    existing reservations are renewed and preserved unless ``release_on_exit``
    marks this as terminal scope completion.
    """

    command_args = tuple(os.fspath(part) for part in command)
    if not command_args or not command_args[0]:
        raise ValueError("A command is required after the reservation options.")
    validate_shared_lease_root(lease_root)

    duration = resolve_reservation_duration(duration_seconds)
    registry = InstanceLeaseRegistry(root=lease_root)
    requested_receipt = receipt_path or os.environ.get(RESERVATION_RECEIPT_ENV) or None
    owns_claim = requested_receipt is None

    if owns_claim:
        if not instances:
            raise ValueError("At least one --instance is required when claiming a reservation.")
        if not scope_id:
            raise ValueError("--scope-id is required when claiming a reservation.")
        host_config = load_bluestacks_host_config(config_path)
        configured_instances = resolve_configured_instances(host_config, tuple(instances))
        claim = registry.claim_reservation(
            configured_instances,
            scope_id=scope_id,
            owner_label=owner_label,
            duration_seconds=duration,
        )
        receipt = claim.receipt_path
        release_after_run = release_on_exit
    else:
        if instances or scope_id:
            raise ValueError("Do not specify --instance or --scope-id when resuming a receipt.")
        receipt = Path(requested_receipt)
        release_after_run = release_on_exit

    renewal_interval = duration / 3
    process: subprocess.Popen[bytes] | None = None
    operation_error: BaseException | None = None
    return_code: int | None = None
    try:
        # Renew before handing the receipt to the child so an expired
        # inherited scope fails before its script can touch the emulator.
        registry.renew_reservation(receipt, duration_seconds=duration)
        child_environment = os.environ.copy()
        child_environment[RESERVATION_RECEIPT_ENV] = str(receipt)
        process = subprocess.Popen(
            command_args,
            env=child_environment,
            start_new_session=(os.name != "nt"),
        )
        next_renewal = time.monotonic() + renewal_interval
        while True:
            return_code = process.poll()
            if return_code is not None:
                break
            remaining = next_renewal - time.monotonic()
            if remaining > 0:
                time.sleep(min(1.0, remaining))
                continue
            registry.renew_reservation(receipt, duration_seconds=duration)
            next_renewal = time.monotonic() + renewal_interval
    except BaseException as error:
        operation_error = error
        raise
    finally:
        if process is not None and (process.poll() is None or operation_error is not None):
            _stop_child_process(process)
        if release_after_run or (owns_claim and operation_error is not None):
            close_preserving_error(
                lambda: registry.release_reservation(receipt),
                operation_error,
                message="Reserved command and reservation release both failed.",
            )
    if return_code is None:
        raise RuntimeError("The reserved command ended without an exit status.")
    return ReservedCommandResult(
        return_code=return_code,
        retained_receipt_path=None if release_after_run else receipt,
    )


def resolve_configured_instances(
    config: BlueStacksHostConfig,
    display_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolves display names case-insensitively while rejecting unknown or repeated names."""

    configured = {instance.display_name.casefold(): instance.display_name for instance in config.instances}
    resolved: list[str] = []
    seen: set[str] = set()
    for name in display_names:
        key = name.strip().casefold()
        canonical = configured.get(key)
        if canonical is None:
            raise ConfigurationError(
                "Unknown BlueStacks display name for a reservation claim.",
                display_name=name.strip(),
            )
        if key in seen:
            raise ConfigurationError(
                "A reservation claim cannot repeat a configured display name.",
                display_name=canonical,
            )
        seen.add(key)
        resolved.append(canonical)
    return tuple(resolved)


def validate_shared_lease_root(lease_root: Path) -> None:
    """Rejects alternate roots that normal PNC admission does not consult."""

    if lease_root.resolve() != DEFAULT_INSTANCE_LEASE_ROOT.resolve():
        raise ValueError(
            "run-reserved requires the canonical process-wide BlueStacks lease root; "
            "normal task admission does not consult alternate roots."
        )


def _stop_child_process(process: subprocess.Popen[bytes]) -> None:
    """Stops the wrapped process tree before releasing its emulator reservation."""

    if os.name == "nt":
        _stop_windows_process_tree(process)
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    if not _wait_for_process_group_exit(process.pid, timeout_seconds=5):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                "Could not confirm the reserved command process tree stopped; "
                "the reservation remains active."
            ) from error
        if not _wait_for_process_group_exit(process.pid, timeout_seconds=5):
            raise RuntimeError(
                "Could not confirm the reserved command process tree stopped; "
                "the reservation remains active."
            )


def _stop_windows_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Uses Windows taskkill tree mode and requires successful termination."""

    result = subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(process.pid)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Could not confirm the reserved command process tree stopped; "
            "the reservation remains active."
        )
    process.wait(timeout=5)


def _wait_for_process_group_exit(process_group_id: int, *, timeout_seconds: float) -> bool:
    """Waits boundedly for every process in a POSIX process group to exit."""

    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return True
        except PermissionError as error:
            raise RuntimeError(
                "Could not confirm the reserved command process tree stopped; "
                "the reservation remains active."
            ) from error
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))
