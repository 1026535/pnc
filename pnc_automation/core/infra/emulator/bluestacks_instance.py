"""Runtime BlueStacks instance metadata."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.core.infra.emulator.models import BlueStacksInstanceConfig


@dataclass(frozen=True, slots=True)
class BlueStacksInstance:
    """Represents the runtime target for one BlueStacks-backed Android session."""

    id: str
    display_name: str
    device_id: str
    app_package: str
    host_instance_key: str | None = None
    process_id: int | None = None
    started_by_resolver: bool = False

    @classmethod
    def from_config(
        cls,
        config: BlueStacksInstanceConfig,
        *,
        device_id: str,
        host_instance_key: str | None = None,
        process_id: int | None = None,
        started_by_resolver: bool = False,
    ) -> "BlueStacksInstance":
        """Builds a runtime instance target from validated config plus the resolved live ADB endpoint."""

        return cls(
            id=config.id,
            display_name=config.display_name,
            device_id=device_id,
            app_package=config.app_package,
            host_instance_key=host_instance_key,
            process_id=process_id,
            started_by_resolver=started_by_resolver,
        )
