"""Synthetic FakeInstanceResolver fixture."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnc_automation.app.authoring.config.models import BlueStacksInstanceConfig
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance



@dataclass(slots=True)
class _FakeInstanceResolver:
    """Records whether the runner tried to resolve a configured emulator instance."""

    resolved_instance: BlueStacksInstance
    requested_configs: list[BlueStacksInstanceConfig] = field(default_factory=list)

    def resolve(self, config: BlueStacksInstanceConfig, *, allow_launch: bool = True) -> BlueStacksInstance:
        """Records one resolve request and returns the seeded runtime instance."""

        del allow_launch
        self.requested_configs.append(config)
        return self.resolved_instance
