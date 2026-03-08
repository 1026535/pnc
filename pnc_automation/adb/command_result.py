"""Represents one executed ADB command."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captures the raw output and timing of one process invocation."""

    command: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes
    duration_seconds: float

    @property
    def stdout_text(self) -> str:
        """Returns stdout decoded for logging and parsing."""

        return self.stdout.decode("utf-8", errors="replace")

    @property
    def stderr_text(self) -> str:
        """Returns stderr decoded for logging and parsing."""

        return self.stderr.decode("utf-8", errors="replace")

    @property
    def succeeded(self) -> bool:
        """Returns whether the command returned a zero exit code."""

        return self.returncode == 0
