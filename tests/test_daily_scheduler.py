"""Offline contract tests for the disabled Windows daily scheduler boundary."""

from __future__ import annotations

import unittest
from pathlib import Path


class DailySchedulerTests(unittest.TestCase):
    """Locks the wrapper and registration script's safety-sensitive settings."""

    def test_wrapper_uses_lock_timezone_acknowledgements_and_exit_propagation(self) -> None:
        """Requires one process mutex and invocation-time authority forwarding."""

        script = Path("tools/run_daily_maintenance.ps1").read_text(encoding="utf-8")
        for required in (
            "Local\\PNC-Daily-Castle-Maintenance",
            ".WaitOne(0)",
            '"Eastern Standard Time"',
            '"daily-maintenance"',
            '"--acknowledgement"',
            "exit $LASTEXITCODE",
        ):
            self.assertIn(required, script)

    def test_registration_is_local_0200_no_catchup_no_wake_no_overlap_and_disabled(self) -> None:
        """Requires the reviewed disabled Task Scheduler policy without a UTC offset."""

        script = Path("tools/register_daily_maintenance_task.ps1").read_text(encoding="utf-8")
        for required in (
            '"Eastern Standard Time"',
            '-At "02:00"',
            "-StartWhenAvailable:$false",
            "-WakeToRun:$false",
            "-MultipleInstances IgnoreNew",
            "-LogonType Password",
            "Disable-ScheduledTask",
            "-WorkingDirectory $repositoryRoot",
        ):
            self.assertIn(required, script)
        self.assertNotIn("+00:00", script)
        self.assertNotIn("-05:00", script)
        self.assertNotIn("-04:00", script)

    def test_memory_monitor_wrapper_is_supervised_non_overlapping_and_watch_mode(self) -> None:
        """Requires the host wrapper to keep one continuous monitor process per machine."""

        script = Path("tools/run_bluestacks_memory_monitor.ps1").read_text(encoding="utf-8")
        for required in (
            "Local\\PNC-BlueStacks-Memory-Monitor",
            ".WaitOne(0)",
            "pnc_automation.bluestacks_management monitor",
            "--watch",
            "exit $LASTEXITCODE",
        ):
            self.assertIn(required, script)
        self.assertNotIn("PASSWORD", script.upper())
        self.assertNotIn("TOKEN", script.upper())

    def test_memory_monitor_registration_restarts_failures_without_overlap(self) -> None:
        """Requires the explicit registration contract to supervise, not start, the monitor."""

        script = Path("tools/register_bluestacks_memory_monitor_task.ps1").read_text(encoding="utf-8")
        for required in (
            "New-ScheduledTaskTrigger -AtLogOn",
            '"pythonw.exe"',
            '-Execute $windowlessPython',
            'pnc_automation.bluestacks_management monitor --config $quotedConfig --watch',
            "-StartWhenAvailable:$false",
            "-WakeToRun:$false",
            "-MultipleInstances IgnoreNew",
            "-RestartCount 3",
            "-RestartInterval (New-TimeSpan -Minutes 1)",
            "-ExecutionTimeLimit ([TimeSpan]::Zero)",
            "Register-ScheduledTask",
            "-LogonType Interactive",
        ):
            self.assertIn(required, script)
        self.assertNotIn("New-ScheduledTaskTrigger -AtStartup", script)
        self.assertNotIn('-Execute "powershell.exe"', script)
        self.assertNotIn("-File $quotedWrapper", script)
        self.assertNotIn("Start-ScheduledTask", script)
        self.assertNotIn("PASSWORD", script.upper())
        self.assertNotIn("TOKEN", script.upper())


if __name__ == "__main__":
    unittest.main()
