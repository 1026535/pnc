"""Compatibility exports for host policy types owned by neutral core config."""

from pnc_automation.core.config.host import (
    BlueStacksCapabilities,
    BlueStacksMemoryPolicy,
    LiveAutomationRole,
    capabilities_for_roles,
    is_memory_restart_eligible,
    require_live_role,
    validate_live_roles,
)

__all__ = [
    "BlueStacksCapabilities",
    "BlueStacksMemoryPolicy",
    "LiveAutomationRole",
    "capabilities_for_roles",
    "is_memory_restart_eligible",
    "require_live_role",
    "validate_live_roles",
]
