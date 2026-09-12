"""Synthetic command_result fixture."""

from __future__ import annotations

from pnc_automation.core.infra.adb.command_result import CommandResult



def _command_result(*, returncode: int, stdout_text: str = "", stderr_text: str = "") -> CommandResult:
    """Builds one deterministic raw ADB command result for runtime wiring tests."""

    return CommandResult(
        command=("adb",),
        returncode=returncode,
        stdout=stdout_text.encode("utf-8"),
        stderr=stderr_text.encode("utf-8"),
        duration_seconds=0.01,
    )
