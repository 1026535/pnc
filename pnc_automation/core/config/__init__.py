"""Reusable typed configuration helpers and host configuration models."""

from pnc_automation.core.config.host import (
    DEFAULT_BLUESTACKS_CONFIG_PATH,
    AccountBinding,
    BlueStacksCapabilities,
    BlueStacksHostConfig,
    BlueStacksInstanceBinding,
    BlueStacksMemoryPolicy,
    LiveAutomationRole,
    capabilities_for_roles,
    load_bluestacks_host_config,
    parse_account_binding,
    parse_bluestacks_metadata_path,
    parse_instance_binding,
    parse_memory_policy,
    parse_live_roles,
    require_live_role,
    validate_live_roles,
)

__all__ = [
    "AccountBinding",
    "BlueStacksCapabilities",
    "BlueStacksHostConfig",
    "BlueStacksInstanceBinding",
    "BlueStacksMemoryPolicy",
    "DEFAULT_BLUESTACKS_CONFIG_PATH",
    "LiveAutomationRole",
    "capabilities_for_roles",
    "load_bluestacks_host_config",
    "parse_account_binding",
    "parse_bluestacks_metadata_path",
    "parse_instance_binding",
    "parse_memory_policy",
    "parse_live_roles",
    "require_live_role",
    "validate_live_roles",
]
