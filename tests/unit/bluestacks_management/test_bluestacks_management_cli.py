"""Offline contract tests for canonical BlueStacks host-management commands."""

from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from pnc_automation.bluestacks_management.__main__ import _run_monitor, main
from pnc_automation.core.config.host import BlueStacksHostConfig, BlueStacksMemoryPolicy
from pnc_automation.bluestacks_management.instance_memory_monitor import (
    MemoryMonitorDisposition,
    MemoryMonitorResult,
)
from pnc_automation.bluestacks_management.instance_shutdown import (
    StaleShutdownDisposition,
    StaleShutdownResult,
)


class BlueStacksManagementCliTests(unittest.TestCase):
    """Keeps host coordination commands in the package-level entry point."""

    def test_monitor_subcommand_routes_watch_and_config(self) -> None:
        """Routes the canonical monitor invocation without constructing host services in the parser test."""

        with patch("pnc_automation.bluestacks_management.__main__._run_monitor", return_value=0) as run_monitor:
            self.assertEqual(main(["monitor", "--config", "custom.yaml", "--watch"]), 0)

        arguments = run_monitor.call_args.args[0]
        self.assertIsInstance(arguments, Namespace)
        self.assertEqual(arguments.config, "custom.yaml")
        self.assertTrue(arguments.watch)

    def test_restart_open_subcommand_routes_options(self) -> None:
        """Routes the open-only maintenance command and its explicit read-only acknowledgement."""

        with patch("pnc_automation.bluestacks_management.__main__._restart_open", return_value=0) as restart_open:
            self.assertEqual(
                main([
                    "restart-open",
                    "--config",
                    "custom.yaml",
                    "--lease-timeout-seconds",
                    "17",
                    "--include-read-only",
                ]),
                0,
            )

        arguments = restart_open.call_args.args[0]
        self.assertEqual(arguments.config, "custom.yaml")
        self.assertEqual(arguments.lease_timeout_seconds, 17)
        self.assertTrue(arguments.include_read_only)
        self.assertFalse(arguments.require_maintenance_window)

    def test_delayed_scheduled_restart_is_rejected_outside_window(self) -> None:
        """The scheduler-only gate refuses a delayed invocation at or after 02:00."""

        with patch(
            "pnc_automation.bluestacks_management.__main__.is_maintenance_window",
            return_value=False,
        ):
            with self.assertRaises(SystemExit) as raised:
                main(["restart-open", "--require-maintenance-window"])

        self.assertEqual(raised.exception.code, 2)

    def test_manual_restart_remains_usable_without_window_gate(self) -> None:
        """The manual command keeps its existing outside-window behavior."""

        with patch("pnc_automation.bluestacks_management.__main__._restart_open", return_value=0) as restart_open:
            self.assertEqual(main(["restart-open"]), 0)
        self.assertFalse(restart_open.call_args.args[0].require_maintenance_window)

    def test_one_shot_exits_nonzero_after_per_instance_recovery_failure(self) -> None:
        """A one-shot sample reports a per-instance recovery failure to its caller."""

        config = BlueStacksHostConfig(
            config_path=Path("accounts.yaml"),
            metadata_path=Path("bluestacks.conf"),
            instances=(),
            accounts=(),
            memory_policy=BlueStacksMemoryPolicy(enabled=True, restart_roles=frozenset()),
        )
        result = MemoryMonitorResult(
            display_name="testing",
            working_set_mb=4096,
            consecutive_over_limit_samples=1,
            disposition=MemoryMonitorDisposition.RESTART_FAILED,
            failure_phase="launch",
        )
        monitor = SimpleNamespace(sample_once=lambda: (result,))
        with (
            patch(
                "pnc_automation.bluestacks_management.__main__.configure_logging",
                return_value=SimpleNamespace(error=lambda *args, **kwargs: None),
            ),
            patch("pnc_automation.bluestacks_management.__main__.load_bluestacks_host_config", return_value=config),
            patch("pnc_automation.bluestacks_management.__main__.BlueStacksInstanceResolver"),
            patch("pnc_automation.bluestacks_management.__main__.BlueStacksInstanceMemoryMonitor", return_value=monitor),
            patch(
                "pnc_automation.bluestacks_management.__main__.BlueStacksStaleInstanceShutdownReconciler",
                return_value=SimpleNamespace(reconcile_all=lambda: ()),
            ),
        ):
            self.assertEqual(_run_monitor(Namespace(config="config/accounts.yaml", watch=False)), 1)

    def test_watch_continues_after_per_instance_failure(self) -> None:
        """One failed recovery is logged while the watch continues sampling peers."""

        config = BlueStacksHostConfig(
            config_path=Path("accounts.yaml"),
            metadata_path=Path("bluestacks.conf"),
            instances=(),
            accounts=(),
            memory_policy=BlueStacksMemoryPolicy(enabled=True, restart_roles=frozenset()),
        )
        failed = MemoryMonitorResult(
            display_name="testing",
            working_set_mb=4096,
            consecutive_over_limit_samples=1,
            disposition=MemoryMonitorDisposition.RESTART_FAILED,
            failure_phase="launch",
        )
        healthy = MemoryMonitorResult(
            display_name="main",
            working_set_mb=100,
            consecutive_over_limit_samples=0,
            disposition=MemoryMonitorDisposition.HEALTHY,
        )
        monitor = SimpleNamespace(
            sample_once=unittest.mock.Mock(side_effect=[(failed,), (healthy,)]),
            policy=BlueStacksMemoryPolicy(enabled=True, sample_interval_seconds=1),
        )
        with (
            patch(
                "pnc_automation.bluestacks_management.__main__.configure_logging",
                return_value=SimpleNamespace(error=lambda *args, **kwargs: None),
            ),
            patch("pnc_automation.bluestacks_management.__main__.load_bluestacks_host_config", return_value=config),
            patch("pnc_automation.bluestacks_management.__main__.BlueStacksInstanceResolver"),
            patch("pnc_automation.bluestacks_management.__main__.BlueStacksInstanceMemoryMonitor", return_value=monitor),
            patch(
                "pnc_automation.bluestacks_management.__main__.time.sleep",
                side_effect=[None, KeyboardInterrupt],
            ),
        ):
            self.assertEqual(_run_monitor(Namespace(config="config/accounts.yaml", watch=True)), 0)

        self.assertEqual(monitor.sample_once.call_count, 2)

    def test_monitor_reconciles_abandoned_phase_cleanup_before_memory_sampling(self) -> None:
        """Runs durable stale-instance cleanup from the existing supervised host loop."""

        config = BlueStacksHostConfig(
            config_path=Path("accounts.yaml"),
            metadata_path=Path("bluestacks.conf"),
            instances=(),
            accounts=(),
            memory_policy=BlueStacksMemoryPolicy(enabled=True, restart_roles=frozenset()),
        )
        stale_result = StaleShutdownResult(
            display_name="testing",
            disposition=StaleShutdownDisposition.CLOSED,
        )
        reconciler = SimpleNamespace(reconcile_all=Mock(return_value=(stale_result,)))
        monitor = SimpleNamespace(sample_once=Mock(return_value=()))
        stdout = StringIO()
        with (
            patch(
                "pnc_automation.bluestacks_management.__main__.configure_logging",
                return_value=SimpleNamespace(error=lambda *args, **kwargs: None),
            ),
            patch("pnc_automation.bluestacks_management.__main__.load_bluestacks_host_config", return_value=config),
            patch("pnc_automation.bluestacks_management.__main__.BlueStacksInstanceResolver"),
            patch("pnc_automation.bluestacks_management.__main__.BlueStacksInstanceMemoryMonitor", return_value=monitor),
            patch(
                "pnc_automation.bluestacks_management.__main__.BlueStacksStaleInstanceShutdownReconciler",
                return_value=SimpleNamespace(reconcile_all=lambda: ()),
            ),
            patch(
                "pnc_automation.bluestacks_management.__main__.BlueStacksStaleInstanceShutdownReconciler",
                return_value=reconciler,
            ),
            redirect_stdout(stdout),
        ):
            self.assertEqual(_run_monitor(Namespace(config="config/accounts.yaml", watch=False)), 0)

        reconciler.reconcile_all.assert_called_once_with()
        monitor.sample_once.assert_called_once_with()
        self.assertIn("stale_shutdown_closed", stdout.getvalue())

    def test_malformed_monitor_config_is_reported_without_exception_text(self) -> None:
        """The host CLI returns a sanitized error instead of echoing malformed YAML details."""

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "accounts.yaml"
            config_path.write_text(
                "accounts: false\ncredentials: cli-secret-sentinel\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            stderr = StringIO()
            with (
                patch(
                    "pnc_automation.bluestacks_management.__main__.configure_logging",
                    return_value=Mock(spec=["error"]),
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                result = _run_monitor(Namespace(config=str(config_path), watch=False))

        self.assertEqual(result, 1)
        self.assertNotIn("cli-secret-sentinel", stdout.getvalue() + stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertIn('"failure_phase": "configuration"', stderr.getvalue())

    def test_legacy_tool_paths_are_thin_compatibility_shims(self) -> None:
        """Keeps existing operator commands forwarding to the package module."""

        monitor = Path("tools/run_bluestacks_memory_monitor.py").read_text(encoding="utf-8")
        restart = Path("tools/restart_bluestacks_instances.py").read_text(encoding="utf-8")
        self.assertIn('"monitor", *(sys.argv[1:] if argv is None else argv)', monitor)
        self.assertIn('"restart-open", *(sys.argv[1:] if argv is None else argv)', restart)
        self.assertNotIn("BlueStacksInstanceResolver", monitor)
        self.assertNotIn("BlueStacksFleetRestarter", restart)


if __name__ == "__main__":
    unittest.main()
