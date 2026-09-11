"""BlueStacks working-set monitor tests."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pnc_automation.app.authoring.config.loader import load_app_config
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksInstanceResolver,
    BlueStacksRunningInstance,
)
from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry
from pnc_automation.bluestacks_management.instance_memory_monitor import (
    BlueStacksInstanceMemoryMonitor,
    MemoryMonitorDisposition,
)
from pnc_automation.bluestacks_management.recovery_state import RecoveryStateStore
from pnc_automation.bluestacks_management.recovery_state import InstanceRecoveryRecord
from pnc_automation.core.config.host import load_bluestacks_host_config
from pnc_automation.core.errors import ConfigurationError


@dataclass
class _MutableRunningSource:
    running: tuple[BlueStacksRunningInstance, ...]

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        return self.running


@dataclass
class _FakeStopper:
    source: _MutableRunningSource
    stopped: list[int]

    def stop_process(self, process_id: int) -> None:
        self.stopped.append(process_id)
        self.source.running = tuple(item for item in self.source.running if item.process_id != process_id)


@dataclass
class _FakeLauncher:
    source: _MutableRunningSource
    launched: list[str]
    launch_attempts: list[str] = field(default_factory=list)
    failures_before_success: int = 0
    on_attempt: Callable[[str, int], None] | None = None

    def launch_instance(self, instance_key: str) -> None:
        self.launch_attempts.append(instance_key)
        if self.on_attempt is not None:
            self.on_attempt(instance_key, len(self.launch_attempts))
        if len(self.launch_attempts) <= self.failures_before_success:
            raise RuntimeError("deterministic launch failure")
        self.launched.append(instance_key)
        self.source.running = (
            BlueStacksRunningInstance(
                process_id=202,
                instance_key=instance_key,
                command_line=f'HD-Player.exe --instance "{instance_key}"',
                working_set_bytes=100 * 1024 * 1024,
            ),
        )


class _FailingRecoveryStore:
    """Fails the intent commit so the monitor must not request a destructive stop."""

    def load_all(self) -> tuple[InstanceRecoveryRecord, ...]:
        return ()

    def load_cooldown(self, display_name: str) -> float | None:
        del display_name
        return None

    def save(self, record: InstanceRecoveryRecord) -> None:
        del record
        raise ConfigurationError("state write sentinel", failure_phase="state_write")


class BlueStacksInstanceMemoryMonitorTests(unittest.TestCase):
    """Validates sustained-pressure, lease, and role safety gates."""

    def test_restarts_only_after_consecutive_over_limit_samples(self) -> None:
        """A temporary spike is observed while sustained pressure triggers one restart."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            stopper = _FakeStopper(source=source, stopped=[])
            launcher = _FakeLauncher(source=source, launched=[])
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=stopper,
                launcher=launcher,
            )

            first = monitor.sample_once()[0]
            second = monitor.sample_once()[0]
            third = monitor.sample_once()[0]

            self.assertEqual(first.disposition, MemoryMonitorDisposition.OVER_LIMIT)
            self.assertEqual(second.consecutive_over_limit_samples, 2)
            self.assertEqual(third.disposition, MemoryMonitorDisposition.RESTARTED)
            self.assertEqual(stopper.stopped, [101])
            self.assertEqual(launcher.launched, ["Nougat32"])

    def test_skips_busy_instance_and_retries_later(self) -> None:
        """The monitor never restarts an instance owned by another cooperating process."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lease_root = root / "leases"
            owner = InstanceLeaseRegistry(root=lease_root)
            owner.acquire(display_name="testing", timeout_seconds=0)
            source = _MutableRunningSource((_running(4096),))
            stopper = _FakeStopper(source=source, stopped=[])
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=stopper,
                launcher=_FakeLauncher(source=source, launched=[]),
                lease_root=lease_root,
                samples=1,
            )
            try:
                result = monitor.sample_once()[0]
            finally:
                owner.release_all()

            self.assertEqual(result.disposition, MemoryMonitorDisposition.BUSY)
            self.assertEqual(stopper.stopped, [])

    def test_never_monitors_read_only_instance(self) -> None:
        """The user's interactive main instance is excluded even above the threshold."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(8192),))
            stopper = _FakeStopper(source=source, stopped=[])
            monitor = self._build_monitor(
                root=root,
                role="read_only",
                source=source,
                stopper=stopper,
                launcher=_FakeLauncher(source=source, launched=[]),
                samples=1,
            )

            self.assertEqual(monitor.sample_once(), ())
            self.assertEqual(stopper.stopped, [])

    def test_retries_relaunch_after_first_launch_failure(self) -> None:
        """Recovers a stopped instance when a bounded relaunch retry succeeds."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            stopper = _FakeStopper(source=source, stopped=[])
            launcher = _FakeLauncher(source=source, launched=[], failures_before_success=1)
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=stopper,
                launcher=launcher,
                samples=1,
                restart_launch_attempts=2,
            )

            result = monitor.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RESTARTED)
            self.assertEqual(launcher.launch_attempts, ["Nougat32", "Nougat32"])
            self.assertEqual(launcher.launched, ["Nougat32"])

    def test_bounded_relaunch_retries_report_failure_and_not_health(self) -> None:
        """Leaves a stopped instance explicitly failed after this pass's retry bound."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            stopper = _FakeStopper(source=source, stopped=[])
            launcher = _FakeLauncher(source=source, launched=[], failures_before_success=3)
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=stopper,
                launcher=launcher,
                samples=1,
                restart_launch_attempts=2,
            )

            result = monitor.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RESTART_FAILED)
            self.assertEqual(result.failure_phase, "launch")
            self.assertEqual(launcher.launch_attempts, ["Nougat32", "Nougat32"])
            self.assertEqual(source.running, ())

    def test_reconstructed_monitor_resumes_persisted_launch_count(self) -> None:
        """A fresh monitor continues a failed recovery from its durable attempt count."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            stopper = _FakeStopper(source=source, stopped=[])
            first_launcher = _FakeLauncher(source=source, launched=[], failures_before_success=1)
            first = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=stopper,
                launcher=first_launcher,
                samples=1,
                restart_launch_attempts=1,
            )

            first_result = first.sample_once()[0]
            self.assertEqual(first_result.disposition, MemoryMonitorDisposition.RESTART_FAILED)
            persisted = first.recovery_store.load_all()
            self.assertEqual(persisted[0].launch_attempts, 1)

            # The retry timestamp represents the required inter-pass delay. Move
            # the fixture past it without weakening the production store.
            first.recovery_store.save(persisted[0].with_failure(phase="launch", next_retry_at=0.0))
            second_launcher = _FakeLauncher(source=source, launched=[], failures_before_success=1)
            second = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=second_launcher,
                samples=1,
                restart_launch_attempts=1,
            )

            second_result = second.sample_once()[0]

            self.assertEqual(second_result.disposition, MemoryMonitorDisposition.RESTART_FAILED)
            self.assertEqual(second_launcher.launch_attempts, ["Nougat32"])
            self.assertEqual(second.recovery_store.load_all()[0].launch_attempts, 2)

    def test_pending_recovery_reconciles_external_launch_without_duplicate_launch(self) -> None:
        """A new process identity for the recorded instance completes recovery without relaunching."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource(
                (
                    BlueStacksRunningInstance(
                        process_id=202,
                        instance_key="Nougat32",
                        command_line='HD-Player.exe --instance "Nougat32"',
                        working_set_bytes=100 * 1024 * 1024,
                    ),
                )
            )
            stopper = _FakeStopper(source=source, stopped=[])
            launcher = _FakeLauncher(source=source, launched=[])
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=stopper,
                launcher=launcher,
                samples=1,
            )
            monitor.recovery_store.save(
                InstanceRecoveryRecord(
                    display_name="testing",
                    instance_key="Nougat32",
                    metadata_path=str((root / "bluestacks.conf").resolve()),
                    original_pid=101,
                    stop_intent=True,
                    stop_confirmed=True,
                    launch_attempts=1,
                    failure_phase="launch",
                    next_retry_at=0.0,
                )
            )

            result = monitor.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RECOVERY_COMPLETED)
            self.assertEqual(launcher.launch_attempts, [])
            self.assertEqual(monitor.recovery_store.load_all(), ())

    def test_persisted_launch_budget_stays_exhausted_after_restart(self) -> None:
        """A persisted nine-attempt budget cannot reset when the monitor process is reconstructed."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource(())
            launcher = _FakeLauncher(source=source, launched=[])
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=launcher,
                samples=1,
            )
            monitor.recovery_store.save(
                InstanceRecoveryRecord(
                    display_name="testing",
                    instance_key="Nougat32",
                    metadata_path=str((root / "bluestacks.conf").resolve()),
                    original_pid=101,
                    stop_intent=True,
                    stop_confirmed=True,
                    launch_attempts=9,
                    failure_phase="launch",
                    next_retry_at=0.0,
                )
            )

            result = monitor.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RECOVERY_EXHAUSTED)
            self.assertEqual(result.failure_phase, "launch_budget_exhausted")
            self.assertEqual(launcher.launch_attempts, [])
            self.assertEqual(monitor.recovery_store.load_all()[0].launch_attempts, 9)

    def test_read_only_reload_blocks_pending_recovery_before_launch(self) -> None:
        """A freshly revoked role blocks a pending recovery without mutating the host."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource(())
            launcher = _FakeLauncher(source=source, launched=[])
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=launcher,
                samples=1,
            )
            monitor.recovery_store.save(
                InstanceRecoveryRecord(
                    display_name="testing",
                    instance_key="Nougat32",
                    metadata_path=str((root / "bluestacks.conf").resolve()),
                    original_pid=101,
                    stop_intent=True,
                    stop_confirmed=True,
                    launch_attempts=1,
                    failure_phase="launch",
                    next_retry_at=0.0,
                )
            )
            config_path = root / "accounts.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace(
                    "live_roles: [smoke_test]", "live_roles: [read_only]"
                ),
                encoding="utf-8",
            )

            result = monitor.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RECOVERY_BLOCKED)
            self.assertEqual(result.failure_phase, "role_revoked")
            self.assertEqual(launcher.launch_attempts, [])

    def test_cooldown_survives_monitor_reconstruction(self) -> None:
        """A persisted successful-recovery cooldown still gates a fresh monitor process."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            store = RecoveryStateStore(root / "state")
            store.save_cooldown("testing", 1000.0)
            first = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=_FakeLauncher(source=source, launched=[]),
                samples=1,
            )
            first.wall_time = lambda: 1001.0
            second = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=_FakeLauncher(source=source, launched=[]),
                samples=1,
            )
            second.wall_time = lambda: 1001.0

            result = second.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.COOLDOWN)
            self.assertEqual(second.recovery_store.load_cooldown("testing"), 1000.0)

    def test_existing_pending_intent_prevents_a_second_new_stop(self) -> None:
        """A pending record is reconciled instead of starting a competing fresh recovery."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            stopper = _FakeStopper(source=source, stopped=[])
            launcher = _FakeLauncher(source=source, launched=[])
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=stopper,
                launcher=launcher,
                samples=1,
            )
            monitor.recovery_store.save(
                InstanceRecoveryRecord(
                    display_name="testing",
                    instance_key="Nougat32",
                    metadata_path=str((root / "bluestacks.conf").resolve()),
                    original_pid=101,
                    stop_intent=True,
                    stop_confirmed=False,
                )
            )

            results = monitor.sample_once()

            self.assertEqual(results[0].disposition, MemoryMonitorDisposition.RESTART_FAILED)
            self.assertEqual(results[0].failure_phase, "stop_wait")
            self.assertEqual(stopper.stopped, [])

    def test_role_change_before_second_launch_blocks_persisted_recovery(self) -> None:
        """A role revocation between bounded launch passes prevents the next mutation."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            first_launcher = _FakeLauncher(source=source, launched=[], failures_before_success=1)
            first = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=first_launcher,
                samples=1,
                restart_launch_attempts=1,
            )
            self.assertEqual(first.sample_once()[0].disposition, MemoryMonitorDisposition.RESTART_FAILED)
            config_path = root / "accounts.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace(
                    "live_roles: [smoke_test]", "live_roles: [read_only]"
                ),
                encoding="utf-8",
            )
            second_launcher = _FakeLauncher(source=source, launched=[])
            second = self._build_monitor(
                root=root,
                role="read_only",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=second_launcher,
                samples=1,
            )

            result = second.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RECOVERY_BLOCKED)
            self.assertEqual(result.failure_phase, "role_revoked")
            self.assertEqual(second_launcher.launch_attempts, [])

    def test_metadata_change_before_second_launch_blocks_old_intent(self) -> None:
        """Changing the configured metadata identity cannot redirect a pending recovery."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacement_metadata = root / "replacement.conf"
            replacement_metadata.write_text(
                'bst.instance.Nougat32.display_name="testing"\n'
                'bst.instance.Nougat32.status.adb_port="5555"\n',
                encoding="utf-8",
            )
            source = _MutableRunningSource((_running(4096),))
            first = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=_FakeLauncher(source=source, launched=[], failures_before_success=1),
                samples=1,
                restart_launch_attempts=1,
            )
            self.assertEqual(first.sample_once()[0].disposition, MemoryMonitorDisposition.RESTART_FAILED)
            config_path = root / "accounts.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace(
                    str((root / "bluestacks.conf").as_posix()),
                    str(replacement_metadata.as_posix()),
                ),
                encoding="utf-8",
            )
            second_launcher = _FakeLauncher(source=source, launched=[])
            second = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=second_launcher,
                samples=1,
            )
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace(
                    str((root / "bluestacks.conf").as_posix()),
                    str(replacement_metadata.as_posix()),
                ),
                encoding="utf-8",
            )

            result = second.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RECOVERY_BLOCKED)
            self.assertEqual(result.failure_phase, "identity_changed")
            self.assertEqual(second_launcher.launch_attempts, [])

    def test_unconfirmed_stop_intent_with_missing_original_resumes_launch(self) -> None:
        """A crash after stop but before confirmation resumes from persisted intent."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource(())
            launcher = _FakeLauncher(source=source, launched=[])
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=launcher,
                samples=1,
            )
            monitor.recovery_store.save(
                InstanceRecoveryRecord(
                    display_name="testing",
                    instance_key="Nougat32",
                    metadata_path=str((root / "bluestacks.conf").resolve()),
                    original_pid=101,
                    stop_intent=True,
                    stop_confirmed=False,
                )
            )

            result = monitor.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RECOVERY_COMPLETED)
            self.assertEqual(launcher.launch_attempts, ["Nougat32"])

    def test_role_change_during_retry_blocks_second_launch_in_same_pass(self) -> None:
        """A role revocation observed after a failed launch blocks the next attempt immediately."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            config_path = root / "accounts.yaml"

            def revoke_role(_instance_key: str, _attempt: int) -> None:
                config_path.write_text(
                    config_path.read_text(encoding="utf-8").replace(
                        "live_roles: [smoke_test]", "live_roles: [read_only]"
                    ),
                    encoding="utf-8",
                )

            launcher = _FakeLauncher(
                source=source,
                launched=[],
                failures_before_success=1,
                on_attempt=revoke_role,
            )
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=launcher,
                samples=1,
            )

            result = monitor.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RECOVERY_BLOCKED)
            self.assertEqual(result.failure_phase, "role_revoked")
            self.assertEqual(launcher.launch_attempts, ["Nougat32"])

    def test_metadata_change_during_retry_blocks_second_launch_in_same_pass(self) -> None:
        """A metadata identity change observed after a failed launch blocks a redirected retry."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            config_path = root / "accounts.yaml"
            replacement_metadata = root / "replacement.conf"
            replacement_metadata.write_text(
                'bst.instance.Pie64.display_name="testing"\n'
                'bst.instance.Pie64.status.adb_port="5556"\n',
                encoding="utf-8",
            )

            def redirect_metadata(_instance_key: str, _attempt: int) -> None:
                config_path.write_text(
                    config_path.read_text(encoding="utf-8").replace(
                        str((root / "bluestacks.conf").as_posix()),
                        str(replacement_metadata.as_posix()),
                    ),
                    encoding="utf-8",
                )

            launcher = _FakeLauncher(
                source=source,
                launched=[],
                failures_before_success=1,
                on_attempt=redirect_metadata,
            )
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=launcher,
                samples=1,
            )

            result = monitor.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RECOVERY_BLOCKED)
            self.assertEqual(result.failure_phase, "identity_changed")
            self.assertEqual(launcher.launch_attempts, ["Nougat32"])

    def test_late_started_process_after_launch_error_completes_without_duplicate_launch(self) -> None:
        """A launcher that starts then raises is reconciled as an external late launch."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))

            def late_start(_instance_key: str, _attempt: int) -> None:
                source.running = (
                    BlueStacksRunningInstance(
                        process_id=202,
                        instance_key="Nougat32",
                        command_line='HD-Player.exe --instance "Nougat32"',
                        working_set_bytes=100 * 1024 * 1024,
                    ),
                )

            launcher = _FakeLauncher(
                source=source,
                launched=[],
                failures_before_success=1,
                on_attempt=late_start,
            )
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=_FakeStopper(source=source, stopped=[]),
                launcher=launcher,
                samples=1,
            )

            result = monitor.sample_once()[0]

            self.assertEqual(result.disposition, MemoryMonitorDisposition.RESTARTED)
            self.assertEqual(launcher.launch_attempts, ["Nougat32"])

    def test_state_write_failure_prevents_stop_intent_mutation(self) -> None:
        """A failed durable intent write fails closed before the stopper is called."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableRunningSource((_running(4096),))
            stopper = _FakeStopper(source=source, stopped=[])
            monitor = self._build_monitor(
                root=root,
                role="smoke_test",
                source=source,
                stopper=stopper,
                launcher=_FakeLauncher(source=source, launched=[]),
                samples=1,
                recovery_store=_FailingRecoveryStore(),
            )

            with self.assertRaises(ConfigurationError):
                monitor.sample_once()

            self.assertEqual(stopper.stopped, [])

    def _build_monitor(
        self,
        *,
        root: Path,
        role: str,
        source: _MutableRunningSource,
        stopper: _FakeStopper,
        launcher: _FakeLauncher,
        lease_root: Path | None = None,
        samples: int = 3,
        restart_launch_attempts: int = 3,
        recovery_store: object | None = None,
    ) -> BlueStacksInstanceMemoryMonitor:
        config_path = root / "accounts.yaml"
        host_config_path = root / "bluestacks.conf"
        host_config_path.write_text(
            'bst.instance.Nougat32.display_name="testing"\n'
            'bst.instance.Nougat32.status.adb_port="5555"\n',
            encoding="utf-8",
        )
        config_path.write_text(
            textwrap.dedent(
                f"""
                runtime:
                  bluestacks_memory:
                    enabled: true
                    max_working_set_mb: 3072
                    consecutive_over_limit_samples: {samples}
                    sample_interval_seconds: 60
                    restart_cooldown_seconds: 1800
                defaults:
                  bluestacks_config_path: {host_config_path.as_posix()}
                instances:
                  - id: bs-test
                    display_name: testing
                    app_package: com.global.tmslg
                accounts:
                  - id: test-account
                    instance_id: bs-test
                    pnc_account_id: test-user
                    live_roles: [{role}]
                """
            ).strip(),
            encoding="utf-8",
        )
        config = load_app_config(config_path)
        resolver = BlueStacksInstanceResolver(
            config_path=host_config_path,
            running_instance_source=source,
            instance_launcher=launcher,
        )
        resolved_lease_root = lease_root or root / "leases"
        return BlueStacksInstanceMemoryMonitor(
            config_provider=lambda: load_bluestacks_host_config(config_path),
            resolver=resolver,
            lease_registry_factory=lambda: InstanceLeaseRegistry(root=resolved_lease_root),
            process_stopper=stopper,
            restart_poll_interval_seconds=0,
            restart_launch_attempts=restart_launch_attempts,
            recovery_store=recovery_store or RecoveryStateStore(root / "state"),
        )


def _running(working_set_mb: int) -> BlueStacksRunningInstance:
    return BlueStacksRunningInstance(
        process_id=101,
        instance_key="Nougat32",
        command_line='HD-Player.exe --instance "Nougat32"',
        working_set_bytes=working_set_mb * 1024 * 1024,
    )


if __name__ == "__main__":
    unittest.main()
