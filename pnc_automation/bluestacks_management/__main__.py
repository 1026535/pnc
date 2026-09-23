"""Canonical command-line entry point for BlueStacks host coordination."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

from pnc_automation.core.config.host import (
    BlueStacksHostConfig,
    LiveAutomationRole,
    load_bluestacks_host_config,
)
from pnc_automation.bluestacks_management.fleet_restart import (
    BlueStacksFleetRestarter,
    current_maintenance_pre_stop_deadline,
    is_maintenance_window,
    TORONTO_MAINTENANCE_ZONE,
)
from pnc_automation.bluestacks_management.instance_lease import (
    DEFAULT_INSTANCE_LEASE_ROOT,
    InstanceLeaseRegistry,
)
from pnc_automation.bluestacks_management.instance_reservation import RESERVATION_RECEIPT_ENV
from pnc_automation.bluestacks_management.reservation_runner import (
    resolve_configured_instances,
    run_reserved_command,
    validate_shared_lease_root,
)
from pnc_automation.bluestacks_management.instance_memory_monitor import BlueStacksInstanceMemoryMonitor
from pnc_automation.bluestacks_management.instance_memory_monitor import MemoryMonitorDisposition
from pnc_automation.bluestacks_management.instance_shutdown import (
    BlueStacksStaleInstanceShutdownReconciler,
    StaleShutdownDisposition,
)
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import BlueStacksInstanceResolver
from pnc_automation.core.infra.diagnostics.logging_setup import configure_logging

_PER_INSTANCE_FAILURE_DISPOSITIONS = frozenset(
    {
        MemoryMonitorDisposition.RESTART_FAILED,
        MemoryMonitorDisposition.RECOVERY_BLOCKED,
        MemoryMonitorDisposition.RECOVERY_EXHAUSTED,
        StaleShutdownDisposition.BLOCKED,
        StaleShutdownDisposition.FAILED,
    }
)


def main(argv: list[str] | None = None) -> int:
    """Runs one explicit BlueStacks monitor or open-instance restart command."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Take one configured memory sample or watch continuously under host supervision.",
    )
    monitor_parser.add_argument("--config", default="config/accounts.yaml")
    monitor_parser.add_argument(
        "--watch",
        action="store_true",
        help="Continue sampling at the configured interval until the supervisor stops the process.",
    )

    restart_parser = subparsers.add_parser(
        "restart-open",
        help="Restart only configured BlueStacks instances open at the initial maintenance snapshot.",
    )
    restart_parser.add_argument("--config", default="config/accounts.yaml")
    restart_parser.add_argument("--lease-timeout-seconds", type=float, default=120.0)
    restart_parser.add_argument(
        "--include-read-only",
        action="store_true",
        help="Acknowledge the explicit 01:55 maintenance exception for an open read-only instance.",
    )
    restart_parser.add_argument(
        "--require-maintenance-window",
        action="store_true",
        help="Refuse delayed invocations outside the scheduled 01:55-02:00 Toronto window.",
    )

    claim_parser = subparsers.add_parser(
        "claim-reservation",
        help="Claim one agent-scoped long reservation over configured display names.",
    )
    claim_parser.add_argument(
        "--instance",
        action="append",
        dest="instances",
        required=True,
        metavar="DISPLAY_NAME",
        help="Configured display name; repeat for a declared multi-instance bundle.",
    )
    claim_parser.add_argument("--scope-id", required=True, help="Assigned reservation scope label.")
    claim_parser.add_argument("--label", default="agent", help="Safe owner label for status diagnostics.")
    claim_parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Bounded idle deadline; defaults to two hours.",
    )
    claim_parser.add_argument("--config", default="config/accounts.yaml")
    claim_parser.add_argument("--lease-root", type=Path, default=DEFAULT_INSTANCE_LEASE_ROOT)

    renew_parser = subparsers.add_parser(
        "renew-reservation",
        help="Renew the caller's live reservation idle deadline.",
    )
    renew_parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help=f"Private receipt path; defaults to ${RESERVATION_RECEIPT_ENV}.",
    )
    renew_parser.add_argument("--duration-seconds", type=float, default=None)
    renew_parser.add_argument("--lease-root", type=Path, default=DEFAULT_INSTANCE_LEASE_ROOT)

    release_parser = subparsers.add_parser(
        "release-reservation",
        help="Release the caller's whole declared reservation scope.",
    )
    release_parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help=f"Private receipt path; defaults to ${RESERVATION_RECEIPT_ENV}.",
    )
    release_parser.add_argument("--lease-root", type=Path, default=DEFAULT_INSTANCE_LEASE_ROOT)

    status_parser = subparsers.add_parser(
        "reservation-status",
        help="Print secret-free configured-instance reservation and task-lock status.",
    )
    status_parser.add_argument("--config", default="config/accounts.yaml")
    status_parser.add_argument("--lease-root", type=Path, default=DEFAULT_INSTANCE_LEASE_ROOT)

    run_parser = subparsers.add_parser(
        "run-reserved",
        help="Run an existing command with an automatically renewed BlueStacks reservation.",
        description=(
            "Claim a reservation for this command, or resume the receipt supplied by "
            f"--receipt / ${RESERVATION_RECEIPT_ENV}. The child inherits the receipt path; "
            "the reservation remains active after the child exits unless --release-on-exit is set."
        ),
    )
    run_parser.add_argument(
        "--instance",
        action="append",
        dest="instances",
        metavar="DISPLAY_NAME",
        help="Configured display name; repeat for a declared multi-instance bundle.",
    )
    run_parser.add_argument("--scope-id", help="Required when claiming a new reservation.")
    run_parser.add_argument("--label", default="agent", help="Safe owner label for status diagnostics.")
    run_parser.add_argument("--duration-seconds", type=float, default=None)
    run_parser.add_argument("--config", default="config/accounts.yaml")
    run_parser.add_argument(
        "--lease-root",
        type=Path,
        default=DEFAULT_INSTANCE_LEASE_ROOT,
        help="Must resolve to the canonical root used by normal task admission.",
    )
    run_parser.add_argument("--receipt", type=Path, default=None)
    run_parser.add_argument(
        "--release-on-exit",
        action="store_true",
        help="Release a new or resumed reservation when this command finishes; use only at terminal scope completion.",
    )
    run_parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="Existing script or command and its arguments, introduced by --.",
    )

    arguments = parser.parse_args(argv)
    if arguments.command == "monitor":
        return _run_monitor(arguments)
    if arguments.command == "restart-open":
        return _restart_open(arguments, parser=parser)
    if arguments.command == "claim-reservation":
        return _claim_reservation(arguments)
    if arguments.command == "renew-reservation":
        return _renew_reservation(arguments)
    if arguments.command == "release-reservation":
        return _release_reservation(arguments)
    if arguments.command == "run-reserved":
        return _run_reserved(arguments, parser=parser)
    return _reservation_status(arguments)


def _run_monitor(arguments: argparse.Namespace) -> int:
    """Builds the role-filtered monitor and emits non-secret sample records."""

    try:
        logger = configure_logging(log_file_root=DEFAULT_INSTANCE_LEASE_ROOT / "state")
    except Exception as error:
        _report_cli_failure(None, error, default_phase="state")
        return 1

    def load_current_config() -> BlueStacksHostConfig:
        """Loads one freshly validated typed host authority snapshot."""

        return load_bluestacks_host_config(Path(arguments.config))

    try:
        config = load_current_config()
        if not config.memory_policy.enabled:
            _report_cli_failure(
                logger,
                None,
                default_phase="configuration",
                error_type="MemoryMonitorDisabled",
            )
            return 1
        resolver = BlueStacksInstanceResolver(config_path=config.metadata_path)
        monitor = BlueStacksInstanceMemoryMonitor(
            config_provider=load_current_config,
            resolver=resolver,
        )
        stale_shutdown_reconciler = BlueStacksStaleInstanceShutdownReconciler(
            config_provider=load_current_config,
            resolver=resolver,
        )
        while True:
            results = (
                *stale_shutdown_reconciler.reconcile_all(),
                *monitor.sample_once(),
            )
            print(json.dumps([asdict(result) for result in results], default=str), flush=True)
            failed_results = tuple(
                result for result in results if result.disposition in _PER_INSTANCE_FAILURE_DISPOSITIONS
            )
            for result in failed_results:
                logger.error(
                    "BlueStacks instance recovery failed.",
                    extra={
                        "display_name": result.display_name,
                        "disposition": result.disposition.value,
                        "failure_phase": result.failure_phase,
                    },
                )
            if not arguments.watch:
                return 1 if failed_results else 0
            time.sleep(monitor.policy.sample_interval_seconds)
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        _report_cli_failure(logger, error, default_phase="configuration")
        return 1


def _restart_open(arguments: argparse.Namespace, *, parser: argparse.ArgumentParser) -> int:
    """Restarts the configured open snapshot while preserving the read-only exception gate."""

    try:
        logger = configure_logging(log_file_root=DEFAULT_INSTANCE_LEASE_ROOT / "state")
    except Exception as error:
        _report_cli_failure(None, error, default_phase="state")
        return 1
    try:
        captured_now = datetime.now(tz=TORONTO_MAINTENANCE_ZONE)
        if arguments.require_maintenance_window and not is_maintenance_window(captured_now):
            parser.error("restart-open is only permitted during the 01:55-02:00 America/Toronto maintenance window")
        config = load_bluestacks_host_config(Path(arguments.config))
        has_read_only = any(LiveAutomationRole.READ_ONLY in account.live_roles for account in config.accounts)
        if has_read_only and not arguments.include_read_only:
            parser.error("--include-read-only is required because the configured fleet contains a read-only instance")
        result = BlueStacksFleetRestarter(
            resolver=BlueStacksInstanceResolver(config_path=config.metadata_path),
        ).restart_running(
            tuple(instance.display_name for instance in config.instances),
            lease_timeout_seconds=arguments.lease_timeout_seconds,
            pre_stop_deadline=current_maintenance_pre_stop_deadline(captured_now),
        )
        print(json.dumps(asdict(result), indent=2, default=str))
        return 0 if result.succeeded else 1
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        _report_cli_failure(logger, error, default_phase="configuration")
        return 1


def _claim_reservation(arguments: argparse.Namespace) -> int:
    """Claims one long reservation and prints only its safe public fields."""

    try:
        config = load_bluestacks_host_config(Path(arguments.config))
        instances = resolve_configured_instances(config, tuple(arguments.instances))
    except Exception as error:
        _report_cli_failure(None, error, default_phase="configuration")
        return 1
    registry = InstanceLeaseRegistry(root=arguments.lease_root)
    try:
        claim = registry.claim_reservation(
            instances,
            scope_id=arguments.scope_id,
            owner_label=arguments.label,
            duration_seconds=arguments.duration_seconds,
        )
    except Exception as error:
        _report_cli_failure(None, error, default_phase="state")
        return 1
    print(
        json.dumps(
            {
                "claimed": True,
                "scope_id": claim.reservation.scope_id,
                "owner_label": claim.reservation.owner_label,
                "instances": list(claim.reservation.instances),
                "expires_at": claim.reservation.expires_at,
                "receipt_path": str(claim.receipt_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_reserved(arguments: argparse.Namespace, *, parser: argparse.ArgumentParser) -> int:
    """Runs an existing script under a claim or resumes the carried receipt."""

    command = list(arguments.script_args)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("run-reserved requires a command after --")
    try:
        validate_shared_lease_root(arguments.lease_root)
    except ValueError as error:
        parser.error(str(error))
    try:
        result = run_reserved_command(
            command,
            instances=tuple(arguments.instances) if arguments.instances else None,
            scope_id=arguments.scope_id,
            owner_label=arguments.label,
            config_path=arguments.config,
            lease_root=arguments.lease_root,
            duration_seconds=arguments.duration_seconds,
            receipt_path=arguments.receipt,
            release_on_exit=arguments.release_on_exit,
        )
        if result.retained_receipt_path is not None:
            print(
                json.dumps(
                    {
                        "reservation_retained": True,
                        "receipt_path": str(result.retained_receipt_path),
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
                flush=True,
            )
        return result.return_code
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        _report_cli_failure(None, error, default_phase="state")
        return 1


def _renew_reservation(arguments: argparse.Namespace) -> int:
    """Renews the caller's live reservation and prints its new expiry."""

    receipt = _receipt_argument(arguments)
    if receipt is None:
        _report_cli_failure(
            None,
            None,
            default_phase="state",
            error_type="ReservationReceiptRequired",
        )
        return 1
    registry = InstanceLeaseRegistry(root=arguments.lease_root)
    try:
        record = registry.renew_reservation(receipt, duration_seconds=arguments.duration_seconds)
    except Exception as error:
        _report_cli_failure(None, error, default_phase="state")
        return 1
    print(
        json.dumps(
            {
                "renewed": True,
                "scope_id": record.scope_id,
                "expires_at": record.expires_at,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _release_reservation(arguments: argparse.Namespace) -> int:
    """Releases the caller's whole scope; repeated release is harmless."""

    receipt = _receipt_argument(arguments)
    if receipt is None:
        _report_cli_failure(
            None,
            None,
            default_phase="state",
            error_type="ReservationReceiptRequired",
        )
        return 1
    registry = InstanceLeaseRegistry(root=arguments.lease_root)
    try:
        record = registry.release_reservation(receipt)
    except Exception as error:
        _report_cli_failure(None, error, default_phase="state")
        return 1
    print(
        json.dumps(
            {
                "released": record is not None,
                "scope_id": record.scope_id if record is not None else None,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _reservation_status(arguments: argparse.Namespace) -> int:
    """Prints configured inventory with reservation and task-lock state; never runs ADB."""

    try:
        config = load_bluestacks_host_config(Path(arguments.config))
        statuses = InstanceLeaseRegistry(root=arguments.lease_root).reservation_status(
            tuple(instance.display_name for instance in config.instances)
        )
    except Exception as error:
        _report_cli_failure(None, error, default_phase="configuration")
        return 1
    print(
        json.dumps(
            {"instances": [asdict(status) for status in statuses]},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _receipt_argument(arguments: argparse.Namespace) -> Path | None:
    """Resolves the private receipt path from the flag or canonical env carrier."""

    if arguments.receipt is not None:
        return arguments.receipt
    raw_path = os.environ.get(RESERVATION_RECEIPT_ENV)
    return Path(raw_path) if raw_path else None


def _report_cli_failure(
    logger: logging.Logger | None,
    error: Exception | None,
    *,
    default_phase: str,
    error_type: str | None = None,
) -> None:
    """Reports a host-command failure without serializing exception text or config values."""

    phase = _safe_failure_phase(error, default_phase)
    safe_type = error_type or (type(error).__name__ if error is not None else "HostCommandError")
    payload = {
        "error": "BlueStacks host command failed.",
        "failure_phase": phase,
        "error_type": safe_type,
    }
    if logger is not None:
        try:
            logger.error("BlueStacks host command failed.", extra=payload)
        except Exception:
            pass
    print(json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)


def _safe_failure_phase(error: Exception | None, default_phase: str) -> str:
    """Extracts only an allow-listed failure phase from typed exception details."""

    details = getattr(error, "details", {}) if error is not None else {}
    candidate = details.get("failure_phase") if isinstance(details, dict) else None
    allowed = {
        "configuration",
        "config",
        "config_reload",
        "discovery",
        "state",
        "state_write",
        "host",
        "recovery",
        "stop",
        "stop_wait",
        "stop_revalidation",
        "launch",
        "launch_wait",
        "launch_revalidation",
        "role_revoked",
        "identity_changed",
        "policy_disabled",
    }
    return candidate if isinstance(candidate, str) and candidate in allowed else default_phase


if __name__ == "__main__":
    raise SystemExit(main())
