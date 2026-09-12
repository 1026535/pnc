"""Synthetic FakeAdbClient fixture."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnc_automation.core.infra.adb.command_result import CommandResult

from tests.support.entrypoints.scheduled_mail.command_result import _command_result


@dataclass(slots=True)
class _FakeAdbClient:
    """Records whether the runner tried to connect to a live emulator."""

    connect_calls: list[str] = field(default_factory=list)

    def connect(self, device_id: str) -> CommandResult:
        """Records one connect call and returns success."""

        self.connect_calls.append(device_id)
        return _command_result(returncode=0, stdout_text="connected")

    def get_state(self, device_id: str) -> CommandResult:
        """Returns a ready device state for completeness when a session is used."""

        return _command_result(returncode=0, stdout_text="device")

    def shell(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Returns a non-empty shell response for completeness when a session is used."""

        del device_id, arguments, timeout_seconds
        return _command_result(returncode=0, stdout_text="BlueStacks")
