"""Offline contract tests for canonical BlueStacks host-management commands."""

from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from pnc_automation.bluestacks_management.__main__ import _run_monitor, main
from pnc_automation.bluestacks_management.instance_reservation import RESERVATION_RECEIPT_ENV
from pnc_automation.core.config.host import (
    BlueStacksHostConfig,
    BlueStacksInstanceBinding,
    BlueStacksMemoryPolicy,
)
from pnc_automation.bluestacks_management.instance_memory_monitor import (
    MemoryMonitorDisposition,
    MemoryMonitorResult,
)
from pnc_automation.bluestacks_management.instance_shutdown import (
    StaleShutdownDisposition,
    StaleShutdownResult,
)


def _host_config(*display_names: str) -> BlueStacksHostConfig:
    """Builds a synthetic configured inventory for CLI claim/status tests."""

    return BlueStacksHostConfig(
        config_path=Path("accounts.yaml"),
        metadata_path=Path("bluestacks.conf"),
        instances=tuple(
            BlueStacksInstanceBinding(id=name.casefold().replace(" ", "-"), display_name=name)
            for name in display_names
        ),
        accounts=(),
        memory_policy=BlueStacksMemoryPolicy(enabled=True, restart_roles=frozenset()),
    )


def _patch_host_config(*display_names: str):
    """Patches the CLI's host-config loader to the synthetic inventory."""

    return patch(
        "pnc_automation.bluestacks_management.__main__.load_bluestacks_host_config",
        return_value=_host_config(*display_names),
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

    def test_reservation_subcommands_route_arguments(self) -> None:
        """Routes every reservation operation with its parsed arguments."""

        with patch(
            "pnc_automation.bluestacks_management.__main__._claim_reservation", return_value=0
        ) as claim:
            self.assertEqual(
                main(
                    [
                        "claim-reservation",
                        "--instance",
                        "Instance A",
                        "--instance",
                        "Instance B",
                        "--scope-id",
                        "scope-1",
                        "--label",
                        "agent-x",
                        "--duration-seconds",
                        "300",
                        "--config",
                        "custom.yaml",
                        "--lease-root",
                        "leases",
                    ]
                ),
                0,
            )
        arguments = claim.call_args.args[0]
        self.assertEqual(arguments.instances, ["Instance A", "Instance B"])
        self.assertEqual(arguments.scope_id, "scope-1")
        self.assertEqual(arguments.duration_seconds, 300.0)
        self.assertEqual(arguments.config, "custom.yaml")
        self.assertEqual(arguments.lease_root, Path("leases"))

        with patch(
            "pnc_automation.bluestacks_management.__main__._renew_reservation", return_value=0
        ) as renew:
            self.assertEqual(main(["renew-reservation", "--receipt", "r.json"]), 0)
        self.assertEqual(renew.call_args.args[0].receipt, Path("r.json"))

        with patch(
            "pnc_automation.bluestacks_management.__main__._release_reservation", return_value=0
        ) as release:
            self.assertEqual(main(["release-reservation", "--receipt", "r.json"]), 0)
        self.assertEqual(release.call_args.args[0].receipt, Path("r.json"))

        with patch(
            "pnc_automation.bluestacks_management.__main__._reservation_status", return_value=0
        ) as status:
            self.assertEqual(main(["reservation-status", "--config", "custom.yaml"]), 0)
        self.assertEqual(status.call_args.args[0].config, "custom.yaml")

    def test_claim_renew_release_lifecycle_is_secret_free(self) -> None:
        """Claim, renew, and release emit safe output that never contains capability material."""

        with tempfile.TemporaryDirectory() as directory:
            lease_root = Path(directory)
            stdout = StringIO()
            with _patch_host_config("Instance A"), redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        [
                            "claim-reservation",
                            "--instance",
                            "Instance A",
                            "--scope-id",
                            "scope-1",
                            "--label",
                            "agent-x",
                            "--lease-root",
                            str(lease_root),
                        ]
                    ),
                    0,
                )
            claimed = json.loads(stdout.getvalue())
            receipt_path = Path(claimed["receipt_path"])
            capability = json.loads(receipt_path.read_bytes())["capability"]
            self.assertNotIn(capability, stdout.getvalue())
            self.assertNotIn("capability_digest", stdout.getvalue())

            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        [
                            "renew-reservation",
                            "--receipt",
                            str(receipt_path),
                            "--duration-seconds",
                            "120",
                            "--lease-root",
                            str(lease_root),
                        ]
                    ),
                    0,
                )
            self.assertTrue(json.loads(stdout.getvalue())["renewed"])
            self.assertNotIn(capability, stdout.getvalue())

            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        [
                            "release-reservation",
                            "--receipt",
                            str(receipt_path),
                            "--lease-root",
                            str(lease_root),
                        ]
                    ),
                    0,
                )
            self.assertTrue(json.loads(stdout.getvalue())["released"])

    def test_renew_and_release_accept_env_receipt(self) -> None:
        """The canonical environment carrier supplies the receipt path without a flag."""

        with tempfile.TemporaryDirectory() as directory:
            lease_root = Path(directory)
            with _patch_host_config("Instance A"), redirect_stdout(StringIO()):
                self.assertEqual(
                    main(
                        [
                            "claim-reservation",
                            "--instance",
                            "Instance A",
                            "--scope-id",
                            "scope-env",
                            "--lease-root",
                            str(lease_root),
                        ]
                    ),
                    0,
                )
            receipts = list((lease_root / "long-reservation-receipts").glob("*.json"))
            self.assertEqual(len(receipts), 1)
            with (
                patch.dict("os.environ", {RESERVATION_RECEIPT_ENV: str(receipts[0])}),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(main(["release-reservation", "--lease-root", str(lease_root)]), 0)

    def test_release_without_receipt_fails_without_exception_text(self) -> None:
        """A missing receipt carrier reports a sanitized failure instead of raising."""

        stderr = StringIO()
        with (
            patch.dict("os.environ", {}, clear=True),
            redirect_stderr(stderr),
        ):
            self.assertEqual(
                main(["release-reservation", "--lease-root", tempfile.gettempdir()]),
                1,
            )
        self.assertIn('"error_type": "ReservationReceiptRequired"', stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_reservation_status_lists_configured_inventory_without_adb(self) -> None:
        """Status prints every configured instance state without constructing the resolver."""

        config = BlueStacksHostConfig(
            config_path=Path("accounts.yaml"),
            metadata_path=Path("bluestacks.conf"),
            instances=(
                BlueStacksInstanceBinding(id="one", display_name="Instance A"),
                BlueStacksInstanceBinding(id="two", display_name="Instance B"),
            ),
            accounts=(),
            memory_policy=BlueStacksMemoryPolicy(enabled=True, restart_roles=frozenset()),
        )
        stdout = StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "pnc_automation.bluestacks_management.__main__.load_bluestacks_host_config",
                return_value=config,
            ),
            patch(
                "pnc_automation.bluestacks_management.__main__.BlueStacksInstanceResolver",
                side_effect=AssertionError("resolver must not be constructed"),
            ),
            redirect_stdout(stdout),
        ):
            self.assertEqual(
                main(
                    [
                        "reservation-status",
                        "--config",
                        "accounts.yaml",
                        "--lease-root",
                        directory,
                    ]
                ),
                0,
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            [(entry["display_name"], entry["reservation_state"], entry["task_lock_state"]) for entry in payload["instances"]],
            [("Instance A", "none", "idle"), ("Instance B", "none", "idle")],
        )
        self.assertTrue(all(entry["claimable"] for entry in payload["instances"]))

    def test_reservation_status_surfaces_active_claim_without_secrets(self) -> None:
        """Status after a claim reports scope diagnostics but never capability material."""

        with tempfile.TemporaryDirectory() as directory:
            lease_root = Path(directory)
            with _patch_host_config("Instance A"), redirect_stdout(StringIO()):
                main(
                    [
                        "claim-reservation",
                        "--instance",
                        "Instance A",
                        "--scope-id",
                        "scope-1",
                        "--label",
                        "agent-x",
                        "--lease-root",
                        str(lease_root),
                    ]
                )
            receipt = next((lease_root / "long-reservation-receipts").glob("*.json"))
            capability = json.loads(receipt.read_bytes())["capability"]

            config = BlueStacksHostConfig(
                config_path=Path("accounts.yaml"),
                metadata_path=Path("bluestacks.conf"),
                instances=(BlueStacksInstanceBinding(id="one", display_name="Instance A"),),
                accounts=(),
                memory_policy=BlueStacksMemoryPolicy(enabled=True, restart_roles=frozenset()),
            )
            stdout = StringIO()
            with (
                patch(
                    "pnc_automation.bluestacks_management.__main__.load_bluestacks_host_config",
                    return_value=config,
                ),
                redirect_stdout(stdout),
            ):
                self.assertEqual(
                    main(
                        [
                            "reservation-status",
                            "--config",
                            "accounts.yaml",
                            "--lease-root",
                            str(lease_root),
                        ]
                    ),
                    0,
                )
            entry = json.loads(stdout.getvalue())["instances"][0]
            self.assertEqual(entry["reservation_state"], "active")
            self.assertEqual(entry["scope_id"], "scope-1")
            self.assertEqual(entry["owner_label"], "agent-x")
            self.assertFalse(entry["claimable"])
            self.assertNotIn(capability, stdout.getvalue())
            self.assertNotIn("capability", stdout.getvalue())

    def test_claim_rejects_unconfigured_display_name_without_authority(self) -> None:
        """An unknown --instance writes no receipt and no reservation record."""

        with tempfile.TemporaryDirectory() as directory:
            lease_root = Path(directory)
            stderr = StringIO()
            with _patch_host_config("Instance A"), redirect_stderr(stderr):
                self.assertEqual(
                    main(
                        [
                            "claim-reservation",
                            "--instance",
                            "Not Configured",
                            "--scope-id",
                            "scope-1",
                            "--lease-root",
                            str(lease_root),
                        ]
                    ),
                    1,
                )
            self.assertIn('"error_type": "ConfigurationError"', stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            receipts_dir = lease_root / "long-reservation-receipts"
            self.assertFalse(receipts_dir.exists() and any(receipts_dir.iterdir()))
            snapshot = lease_root / "long-reservations.json"
            self.assertFalse(snapshot.exists())

    def test_claim_accepts_configured_bundle_with_canonical_names(self) -> None:
        """A configured bundle claims all-or-none under canonical display names."""

        with tempfile.TemporaryDirectory() as directory:
            lease_root = Path(directory)
            stdout = StringIO()
            with _patch_host_config("Instance A", "Instance B"), redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        [
                            "claim-reservation",
                            "--instance",
                            "instance a",
                            "--instance",
                            "Instance B",
                            "--scope-id",
                            "scope-1",
                            "--lease-root",
                            str(lease_root),
                        ]
                    ),
                    0,
                )
            claimed = json.loads(stdout.getvalue())
            self.assertEqual(claimed["instances"], ["Instance A", "Instance B"])

            stderr = StringIO()
            with _patch_host_config("Instance A"), redirect_stderr(stderr):
                self.assertEqual(
                    main(
                        [
                            "claim-reservation",
                            "--instance",
                            "Instance A",
                            "--instance",
                            "instance A",
                            "--scope-id",
                            "scope-dup",
                            "--lease-root",
                            str(lease_root),
                        ]
                    ),
                    1,
                )
            self.assertIn('"error_type": "ConfigurationError"', stderr.getvalue())

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
