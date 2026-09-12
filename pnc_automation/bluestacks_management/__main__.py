"""Canonical command-line entry point for BlueStacks host coordination."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
import logging
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
from pnc_automation.bluestacks_management.instance_lease import DEFAULT_INSTANCE_LEASE_ROOT
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

    arguments = parser.parse_args(argv)
    if arguments.command == "monitor":
        return _run_monitor(arguments)
    return _restart_open(arguments, parser=parser)


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
