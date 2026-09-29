"""Canonical ADB command execution."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pnc_automation.core.infra.adb.command_result import CommandResult
from pnc_automation.core.infra.diagnostics.performance import performance_span

_ADB_OPERATION_FAMILIES = frozenset(
    {
        "connect",
        "devices",
        "disconnect",
        "exec-out",
        "forward",
        "get-state",
        "install",
        "kill-server",
        "reverse",
        "shell",
        "start-server",
        "version",
        "wait-for-device",
    }
)


class CommandRunner(Protocol):
    """Executes one process invocation and returns raw command results."""

    def run(self, command: Sequence[str], *, timeout_seconds: float | None = None) -> CommandResult:
        """Executes the provided command."""


@dataclass(slots=True)
class SubprocessCommandRunner:
    """Default subprocess-backed command runner."""

    def run(self, command: Sequence[str], *, timeout_seconds: float | None = None) -> CommandResult:
        """Executes the command without invoking an intermediate shell."""

        started = time.perf_counter()
        completed = subprocess.run(
            list(command),
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        finished = time.perf_counter()
        return CommandResult(
            command=tuple(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=finished - started,
        )


@dataclass(slots=True)
class AdbClient:
    """Owns all raw ADB invocation mechanics for the platform."""

    adb_path: str = "adb"
    runner: CommandRunner = field(default_factory=SubprocessCommandRunner)

    def run_global(self, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Runs an ADB command that is not device-scoped."""

        with performance_span(
            "adb.command",
            attributes={"scope": "global", "family": _operation_family(arguments)},
        ) as measured:
            result = self.runner.run((self.adb_path, *arguments), timeout_seconds=timeout_seconds)
            if measured is not None:
                measured.set_attribute("returncode", result.returncode)
                measured.set_attribute("stdout_bytes", len(result.stdout))
                measured.set_attribute("stderr_bytes", len(result.stderr))
            return result

    def run_device(
        self,
        device_id: str,
        *arguments: str,
        timeout_seconds: float | None = 10,
    ) -> CommandResult:
        """Runs an ADB command scoped to one device target."""

        with performance_span(
            "adb.command",
            attributes={"scope": "device", "family": _operation_family(arguments)},
        ) as measured:
            result = self.runner.run(
                (self.adb_path, "-s", device_id, *arguments),
                timeout_seconds=timeout_seconds,
            )
            if measured is not None:
                measured.set_attribute("returncode", result.returncode)
                measured.set_attribute("stdout_bytes", len(result.stdout))
                measured.set_attribute("stderr_bytes", len(result.stderr))
            return result

    def shell(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Runs one `adb shell` command against the selected device."""

        return self.run_device(device_id, "shell", *arguments, timeout_seconds=timeout_seconds)

    def exec_out(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Runs one `adb exec-out` command against the selected device."""

        return self.run_device(device_id, "exec-out", *arguments, timeout_seconds=timeout_seconds)

    def connect(self, device_id: str, *, timeout_seconds: float | None = 10) -> CommandResult:
        """Attempts to connect to one ADB endpoint."""

        return self.run_global("connect", device_id, timeout_seconds=timeout_seconds)

    def get_state(self, device_id: str, *, timeout_seconds: float | None = 10) -> CommandResult:
        """Returns the ADB device state for one device target."""

        return self.run_device(device_id, "get-state", timeout_seconds=timeout_seconds)

    def list_devices(self, *, timeout_seconds: float | None = 10) -> CommandResult:
        """Lists known ADB devices."""

        return self.run_global("devices", timeout_seconds=timeout_seconds)


def _operation_family(arguments: Sequence[str]) -> str:
    """Returns only the low-cardinality ADB operation verb, never its arguments."""

    if not arguments:
        return "unspecified"
    operation = arguments[0]
    return operation if operation in _ADB_OPERATION_FAMILIES else "other"
