"""Offline timeout contracts for bounded BlueStacks host subprocess controls."""

from __future__ import annotations

import subprocess
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from pnc_automation.bluestacks_management.instance_memory_monitor import (
    PowerShellBlueStacksProcessStopper,
)
from pnc_automation.bluestacks_management.instance_shutdown import PowerShellBlueStacksInstanceCloser
from pnc_automation.bluestacks_management.process_control import run_powershell, wait_for_instance_state
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksRunningInstance,
    PowerShellBlueStacksRunningInstanceSource,
)


@dataclass(slots=True)
class _SequencedRunningSource:
    """Returns the running-process snapshots needed for shutdown revalidation."""

    snapshots: tuple[tuple[BlueStacksRunningInstance, ...], ...]
    calls: int = 0

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        """Returns the next process snapshot, repeating the last one."""

        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        return self.snapshots[index]


@dataclass(slots=True)
class _RecordingStopper:
    """Records the process id selected for shutdown."""

    process_ids: list[int] = field(default_factory=list)

    def stop_process(self, process_id: int) -> None:
        """Records one exact stop request."""

        self.process_ids.append(process_id)


@dataclass(slots=True)
class _TransientDiscoveryFailureSource:
    """Fails one process snapshot while a target process is disappearing."""

    calls: int = 0

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        """Returns a complete stopped snapshot after one transient CIM failure."""

        self.calls += 1
        if self.calls == 1:
            raise ConfigurationError(
                "BlueStacks process enumeration returned a process without a command line.",
                failure_phase="discovery",
            )
        return ()


class BlueStacksProcessControlTests(unittest.TestCase):
    """Ensures host discovery and stop calls cannot block bounded state machines forever."""

    @patch(
        "pnc_automation.core.infra.emulator.bluestacks_instance_resolver.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="powershell", timeout=15),
    )
    def test_discovery_timeout_is_typed_without_captured_process_output(self, _run) -> None:
        """Discovery timeout exposes only its phase and configured bound."""

        with self.assertRaises(ConfigurationError) as raised:
            PowerShellBlueStacksRunningInstanceSource(timeout_seconds=15).list_running_instances()

        self.assertEqual(raised.exception.details["failure_phase"], "discovery")
        self.assertEqual(raised.exception.details["timeout_seconds"], 15)
        self.assertEqual(_run.call_args.kwargs["timeout"], 15)
        self.assertNotIn("stdout", raised.exception.details)
        self.assertNotIn("stderr", raised.exception.details)

    @patch(
        "pnc_automation.bluestacks_management.process_control.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="powershell", timeout=35),
    )
    def test_stop_timeout_is_typed_without_captured_process_output(self, _run) -> None:
        """Graceful-stop timeout exposes only its phase and configured bound."""

        with self.assertRaises(ConfigurationError) as raised:
            PowerShellBlueStacksProcessStopper(timeout_seconds=35).stop_process(123)

        self.assertEqual(raised.exception.details["failure_phase"], "stop")
        self.assertEqual(raised.exception.details["timeout_seconds"], 35)
        self.assertEqual(_run.call_args.kwargs["timeout"], 35)
        self.assertNotIn("stdout", raised.exception.details)
        self.assertNotIn("stderr", raised.exception.details)

    @patch(
        "pnc_automation.bluestacks_management.process_control.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="powershell", timeout=15),
    )
    def test_shared_powershell_timeout_does_not_expose_exception_text(self, _run) -> None:
        """The shared control helper sanitizes a timeout before callers serialize it."""

        with self.assertRaises(ConfigurationError) as raised:
            run_powershell(
                powershell_path="powershell",
                script="Write-Output secret-sentinel",
                timeout_seconds=15,
                failure_message="host operation failed",
                failure_phase="discovery",
            )

        self.assertNotIn("secret-sentinel", str(raised.exception))
        self.assertEqual(raised.exception.details["failure_phase"], "discovery")

    def test_state_wait_retries_a_transient_incomplete_process_snapshot(self) -> None:
        """Confirms stop after a process exits during CIM property materialization."""

        source = _TransientDiscoveryFailureSource()
        delays: list[float] = []

        wait_for_instance_state(
            source=source,
            instance_key="Nougat32",
            running=False,
            attempts=2,
            interval_seconds=0.25,
            sleep=delays.append,
        )

        self.assertEqual(source.calls, 2)
        self.assertEqual(delays, [0.25])

    def test_instance_closer_revalidates_process_identity_and_confirms_exit(self) -> None:
        """Stops only the process captured by the connected session and waits for its disappearance."""

        source = _SequencedRunningSource(
            snapshots=(
                (
                    BlueStacksRunningInstance(
                        process_id=101,
                        instance_key="Nougat32",
                        command_line="HD-Player.exe --instance Nougat32",
                    ),
                ),
                (),
            )
        )
        stopper = _RecordingStopper()
        closer = PowerShellBlueStacksInstanceCloser(
            running_instance_source=source,
            process_stopper=stopper,
            poll_interval_seconds=0,
            sleep=lambda _: None,
        )

        closer.close_instance(
            BlueStacksInstance(
                id="bs-main",
                display_name="serious_stuff",
                device_id="127.0.0.1:5555",
                app_package="com.global.tmslg",
                host_instance_key="Nougat32",
                process_id=101,
                started_by_resolver=True,
            )
        )

        self.assertEqual(stopper.process_ids, [101])
        self.assertEqual(source.calls, 2)

    def test_instance_closer_withholds_stop_when_identity_changed(self) -> None:
        """Fails closed instead of stopping a replacement process with the same instance key."""

        source = _SequencedRunningSource(
            snapshots=(
                (
                    BlueStacksRunningInstance(
                        process_id=202,
                        instance_key="Nougat32",
                        command_line="HD-Player.exe --instance Nougat32",
                    ),
                ),
            )
        )
        stopper = _RecordingStopper()
        closer = PowerShellBlueStacksInstanceCloser(
            running_instance_source=source,
            process_stopper=stopper,
            poll_interval_seconds=0,
            sleep=lambda _: None,
        )

        with self.assertRaisesRegex(ConfigurationError, "identity changed"):
            closer.close_instance(
                BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5555",
                    app_package="com.global.tmslg",
                    host_instance_key="Nougat32",
                    process_id=101,
                    started_by_resolver=True,
                )
            )

        self.assertEqual(stopper.process_ids, [])


if __name__ == "__main__":
    unittest.main()
