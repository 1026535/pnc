"""Runtime BlueStacks instance metadata."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.config.models import BlueStacksInstanceConfig


@dataclass(frozen=True, slots=True)
class BlueStacksInstance:
    """Represents the runtime target for one BlueStacks-backed Android session."""

    id: str
    device_id: str
    app_package: str

    @classmethod
    def from_config(cls, config: BlueStacksInstanceConfig) -> "BlueStacksInstance":
        """Builds a runtime instance target from validated config."""

        return cls(id=config.id, device_id=config.device_id, app_package=config.app_package)
