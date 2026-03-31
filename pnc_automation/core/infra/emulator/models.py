"""Core emulator configuration models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlueStacksInstanceConfig:
    """Binds one emulator target to one stable BlueStacks display name and app package."""

    id: str
    display_name: str
    app_package: str

