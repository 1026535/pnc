"""Offline timeout contracts for bounded BlueStacks host subprocess controls."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from pnc_automation.bluestacks_management.instance_memory_monitor import (
    PowerShellBlueStacksProcessStopper,
)
from pnc_automation.bluestacks_management.process_control import run_powershell
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    PowerShellBlueStacksRunningInstanceSource,
)


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


if __name__ == "__main__":
    unittest.main()
