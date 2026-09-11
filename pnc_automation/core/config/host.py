"""Neutral typed BlueStacks host configuration and shared field parsers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from pnc_automation.core.config.yaml_helpers import require_int, require_list, require_mapping, require_string
from pnc_automation.core.errors import ConfigurationError

DEFAULT_BLUESTACKS_CONFIG_PATH = Path(r"C:\ProgramData\BlueStacks_nxt\bluestacks.conf")
_DEFAULT_MEMORY_RESTART_ROLES = (
    "smoke_test",
    "live_testing",
    "daily_canary",
)


class LiveAutomationRole(StrEnum):
    """Names explicitly permitted live uses without changing roster ownership."""

    SMOKE_TEST = "smoke_test"
    LIVE_TESTING = "live_testing"
    DAILY_CANARY = "daily_canary"
    READ_ONLY = "read_only"


@dataclass(frozen=True, slots=True)
class BlueStacksCapabilities:
    """Runtime capabilities derived from configured live roles."""

    allow_instance_launch: bool
    allow_app_launch: bool
    allow_input: bool

    @classmethod
    def unrestricted(cls) -> "BlueStacksCapabilities":
        """Builds the compatibility capability used by direct infrastructure tests."""

        return cls(allow_instance_launch=True, allow_app_launch=True, allow_input=True)


def validate_live_roles(roles: list[LiveAutomationRole] | tuple[LiveAutomationRole, ...] | set[LiveAutomationRole] | frozenset[LiveAutomationRole], *, account_id: str) -> frozenset[LiveAutomationRole]:
    """Rejects contradictory read-only and active automation role combinations."""

    normalized = frozenset(roles)
    active_roles = normalized - {LiveAutomationRole.READ_ONLY}
    if LiveAutomationRole.READ_ONLY in normalized and active_roles:
        raise ConfigurationError(
            f"Account '{account_id}' cannot combine read_only with an active automation role.",
            account_id=account_id,
            live_roles=tuple(sorted(role.value for role in normalized)),
        )
    return normalized


def capabilities_for_roles(roles: list[LiveAutomationRole] | tuple[LiveAutomationRole, ...] | set[LiveAutomationRole] | frozenset[LiveAutomationRole]) -> BlueStacksCapabilities:
    """Derives one host/session capability policy from live roles."""

    normalized = frozenset(roles)
    if LiveAutomationRole.READ_ONLY in normalized:
        return BlueStacksCapabilities(False, False, False)
    active_roles = normalized.intersection(
        {
            LiveAutomationRole.SMOKE_TEST,
            LiveAutomationRole.LIVE_TESTING,
            LiveAutomationRole.DAILY_CANARY,
        }
    )
    allowed = bool(active_roles)
    return BlueStacksCapabilities(allowed, allowed, allowed)


def require_live_role(
    roles: list[LiveAutomationRole] | tuple[LiveAutomationRole, ...] | set[LiveAutomationRole] | frozenset[LiveAutomationRole],
    required_role: LiveAutomationRole,
    *,
    account_id: str,
) -> None:
    """Fails closed when a configured account is not eligible for a workflow."""

    if required_role not in frozenset(roles):
        raise PermissionError(
            f"Account '{account_id}' is not authorized for live role '{required_role.value}'. "
            "Its castle inventory remains configured but must not be used by this workflow."
        )


def is_memory_restart_eligible(
    roles: list[LiveAutomationRole] | tuple[LiveAutomationRole, ...] | set[LiveAutomationRole] | frozenset[LiveAutomationRole],
    restart_roles: list[LiveAutomationRole] | tuple[LiveAutomationRole, ...] | set[LiveAutomationRole] | frozenset[LiveAutomationRole],
) -> bool:
    """Returns whether host RAM recovery may restart an account's instance."""

    normalized = frozenset(roles)
    return (
        LiveAutomationRole.READ_ONLY not in normalized
        and bool(normalized.intersection(restart_roles))
        and capabilities_for_roles(normalized).allow_instance_launch
    )


@dataclass(frozen=True, slots=True)
class BlueStacksMemoryPolicy:
    """Controls conservative automatic recovery from sustained emulator memory growth."""

    enabled: bool = False
    max_working_set_mb: int = 3072
    consecutive_over_limit_samples: int = 3
    sample_interval_seconds: int = 60
    restart_cooldown_seconds: int = 1800
    restart_roles: frozenset[LiveAutomationRole] = frozenset(
        {
            LiveAutomationRole.SMOKE_TEST,
            LiveAutomationRole.LIVE_TESTING,
            LiveAutomationRole.DAILY_CANARY,
        }
    )

    def __post_init__(self) -> None:
        """Rejects unsafe or nonsensical monitor settings."""

        positive_fields = {
            "max_working_set_mb": self.max_working_set_mb,
            "consecutive_over_limit_samples": self.consecutive_over_limit_samples,
            "sample_interval_seconds": self.sample_interval_seconds,
            "restart_cooldown_seconds": self.restart_cooldown_seconds,
        }
        for field_name, value in positive_fields.items():
            if isinstance(value, bool) or value <= 0:
                raise ConfigurationError(
                    f"runtime.bluestacks_memory.{field_name} must be positive.",
                    field=field_name,
                )


@dataclass(frozen=True, slots=True)
class BlueStacksInstanceBinding:
    """Binds a stable host instance id to its BlueStacks display name."""

    id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class AccountBinding:
    """Carries only host-relevant account identity, instance, and roles."""

    id: str
    instance_id: str
    live_roles: frozenset[LiveAutomationRole]


@dataclass(frozen=True, slots=True)
class BlueStacksHostConfig:
    """Owns the host-management subset of the application YAML contract."""

    config_path: Path
    metadata_path: Path
    instances: tuple[BlueStacksInstanceBinding, ...]
    accounts: tuple[AccountBinding, ...]
    memory_policy: BlueStacksMemoryPolicy

    def require_instance(self, instance_id: str) -> BlueStacksInstanceBinding:
        """Returns a configured host instance binding."""

        for instance in self.instances:
            if instance.id == instance_id:
                return instance
        raise ConfigurationError(f"Unknown instance id '{instance_id}'.", instance_id=instance_id)

    def require_account(self, account_id: str) -> AccountBinding:
        """Returns a configured host account binding."""

        for account in self.accounts:
            if account.id == account_id:
                return account
        raise ConfigurationError(f"Unknown account id '{account_id}'.", account_id=account_id)

    def roles_by_instance(self) -> dict[str, frozenset[LiveAutomationRole]]:
        """Aggregates account roles for host-level restart eligibility."""

        roles: dict[str, set[LiveAutomationRole]] = {}
        for account in self.accounts:
            roles.setdefault(account.instance_id, set()).update(account.live_roles)
        return {instance_id: frozenset(values) for instance_id, values in roles.items()}


def load_bluestacks_host_config(path: str | Path, *, env: Mapping[str, str] | None = None) -> BlueStacksHostConfig:
    """Loads only host-owned fields from accounts YAML without resolving credentials or app files."""

    del env
    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise ConfigurationError(f"Configuration file '{config_path}' does not exist.", path=str(config_path))
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            loaded_data = yaml.safe_load(handle)
            raw_data = {} if loaded_data is None else loaded_data
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError("Host configuration could not be read.", path=str(config_path)) from error
    raw = require_mapping(raw_data, context="config root", error_builder=ConfigurationError)
    workspace_root = _resolve_workspace_root(config_path)
    defaults_value = raw.get("defaults")
    runtime_value = raw.get("runtime")
    instances_value = raw.get("instances")
    accounts_value = raw.get("accounts")
    defaults = require_mapping(
        {} if defaults_value is None else defaults_value,
        context="defaults",
        error_builder=ConfigurationError,
    )
    runtime = require_mapping(
        {} if runtime_value is None else runtime_value,
        context="runtime",
        error_builder=ConfigurationError,
    )
    instances = _load_host_instances([] if instances_value is None else instances_value)
    accounts = _load_host_accounts([] if accounts_value is None else accounts_value)
    _validate_host_bindings(instances, accounts)
    return BlueStacksHostConfig(
        config_path=config_path,
        metadata_path=parse_bluestacks_metadata_path(
            defaults.get("bluestacks_config_path", str(DEFAULT_BLUESTACKS_CONFIG_PATH)),
            workspace_root=workspace_root,
            context="defaults.bluestacks_config_path",
        ),
        instances=instances,
        accounts=accounts,
        memory_policy=parse_memory_policy(runtime.get("bluestacks_memory"), context="runtime.bluestacks_memory"),
    )


def parse_bluestacks_metadata_path(value: Any, *, workspace_root: Path, context: str = "defaults.bluestacks_config_path") -> Path:
    """Parses the canonical host metadata path relative to the config workspace."""

    path = Path(require_string(value, context=context, error_builder=ConfigurationError))
    return path if path.is_absolute() else (workspace_root / path).resolve()


def parse_instance_binding(value: Any, *, context: str) -> BlueStacksInstanceBinding:
    """Parses the host-owned id/display portion of an instance mapping."""

    raw = require_mapping(value, context=context, error_builder=ConfigurationError)
    return BlueStacksInstanceBinding(
        id=require_string(raw.get("id"), context=f"{context}.id", error_builder=ConfigurationError).strip(),
        display_name=require_string(
            raw.get("display_name"),
            context=f"{context}.display_name",
            error_builder=ConfigurationError,
        ).strip(),
    )


def parse_account_binding(value: Any, *, context: str) -> AccountBinding:
    """Parses the host-owned account id, instance reference, and roles."""

    raw = require_mapping(value, context=context, error_builder=ConfigurationError)
    account_id = require_string(raw.get("id"), context=f"{context}.id", error_builder=ConfigurationError).strip()
    instance_id = require_string(
        raw.get("instance_id"),
        context=f"{context}.instance_id",
        error_builder=ConfigurationError,
    ).strip()
    return AccountBinding(
        id=account_id,
        instance_id=instance_id,
        live_roles=parse_live_roles(
            [] if raw.get("live_roles") is None else raw.get("live_roles"),
            context=f"{context}.live_roles",
            account_id=account_id,
        ),
    )


def parse_live_roles(value: Any, *, context: str, account_id: str) -> frozenset[LiveAutomationRole]:
    """Parses and validates one account's explicit live role list."""

    raw_roles = require_list(value, context=context, error_builder=ConfigurationError)
    roles: list[LiveAutomationRole] = []
    for index, raw_role in enumerate(raw_roles):
        role_text = require_string(raw_role, context=f"{context}[{index}]", error_builder=ConfigurationError).strip()
        try:
            role = LiveAutomationRole(role_text)
        except ValueError as error:
            raise ConfigurationError(
                f"Unsupported live role '{role_text}'.",
                context=f"{context}[{index}]",
            ) from error
        if role in roles:
            raise ConfigurationError(
                f"Duplicate live role '{role_text}'.",
                context=context,
            )
        roles.append(role)
    return validate_live_roles(roles, account_id=account_id)


def parse_memory_policy(value: Any, *, context: str = "runtime.bluestacks_memory") -> BlueStacksMemoryPolicy:
    """Parses one host memory policy with canonical defaults and role handling."""

    raw = require_mapping(
        {} if value is None else value,
        context=context,
        error_builder=ConfigurationError,
    )
    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigurationError(f"Expected {context}.enabled to be a boolean.", context=f"{context}.enabled")
    raw_roles = raw.get("restart_roles", list(_DEFAULT_MEMORY_RESTART_ROLES))
    return BlueStacksMemoryPolicy(
        enabled=enabled,
        max_working_set_mb=require_int(
            raw.get("max_working_set_mb", 3072),
            context=f"{context}.max_working_set_mb",
            error_builder=ConfigurationError,
        ),
        consecutive_over_limit_samples=require_int(
            raw.get("consecutive_over_limit_samples", 3),
            context=f"{context}.consecutive_over_limit_samples",
            error_builder=ConfigurationError,
        ),
        sample_interval_seconds=require_int(
            raw.get("sample_interval_seconds", 60),
            context=f"{context}.sample_interval_seconds",
            error_builder=ConfigurationError,
        ),
        restart_cooldown_seconds=require_int(
            raw.get("restart_cooldown_seconds", 1800),
            context=f"{context}.restart_cooldown_seconds",
            error_builder=ConfigurationError,
        ),
        restart_roles=_parse_restart_roles(raw_roles, context=f"{context}.restart_roles"),
    )


def _parse_restart_roles(value: Any, *, context: str) -> frozenset[LiveAutomationRole]:
    """Parses the configured host-recovery role allow-list."""

    raw_roles = require_list(value, context=context, error_builder=ConfigurationError)
    roles: list[LiveAutomationRole] = []
    for index, raw_role in enumerate(raw_roles):
        role_text = require_string(raw_role, context=f"{context}[{index}]", error_builder=ConfigurationError).strip()
        try:
            role = LiveAutomationRole(role_text)
        except ValueError as error:
            raise ConfigurationError(
                f"Unsupported BlueStacks memory restart role '{role_text}'.",
                context=f"{context}[{index}]",
            ) from error
        if role in roles:
            raise ConfigurationError(f"Duplicate BlueStacks memory restart role '{role_text}'.", context=context)
        roles.append(role)
    return frozenset(roles)


def _load_host_instances(value: Any) -> tuple[BlueStacksInstanceBinding, ...]:
    """Loads host instance bindings without touching app package settings."""

    items = require_list(value, context="instances", error_builder=ConfigurationError)
    return tuple(parse_instance_binding(item, context=f"instances[{index}]") for index, item in enumerate(items))


def _load_host_accounts(value: Any) -> tuple[AccountBinding, ...]:
    """Loads host account bindings without resolving credentials or P&C ids."""

    items = require_list(value, context="accounts", error_builder=ConfigurationError)
    return tuple(parse_account_binding(item, context=f"accounts[{index}]") for index, item in enumerate(items))


def _validate_host_bindings(
    instances: tuple[BlueStacksInstanceBinding, ...],
    accounts: tuple[AccountBinding, ...],
) -> None:
    """Validates host ids, account references, display uniqueness, and role combinations."""

    _validate_unique("instance", (instance.id for instance in instances))
    _validate_unique("account", (account.id for account in accounts))
    seen_display_names: dict[str, str] = {}
    for instance in instances:
        normalized = instance.display_name.casefold()
        if normalized in seen_display_names:
            raise ConfigurationError(
                "Each configured BlueStacks display_name may map to only one instance id.",
                display_name=instance.display_name,
                first_instance_id=seen_display_names[normalized],
                duplicate_instance_id=instance.id,
            )
        seen_display_names[normalized] = instance.id
    instance_ids = {instance.id for instance in instances}
    for account in accounts:
        if account.instance_id not in instance_ids:
            raise ConfigurationError(
                f"Account '{account.id}' references unknown instance '{account.instance_id}'.",
                account_id=account.id,
                instance_id=account.instance_id,
            )
    roles_by_instance: dict[str, set[LiveAutomationRole]] = {}
    for account in accounts:
        roles_by_instance.setdefault(account.instance_id, set()).update(account.live_roles)
    for instance_id, roles in roles_by_instance.items():
        active_roles = roles - {LiveAutomationRole.READ_ONLY}
        if LiveAutomationRole.READ_ONLY in roles and active_roles:
            raise ConfigurationError(
                "Accounts sharing one BlueStacks instance cannot combine read_only with active automation roles.",
                instance_id=instance_id,
                live_roles=tuple(sorted(role.value for role in roles)),
            )


def _validate_unique(label: str, values: Any) -> None:
    """Rejects duplicate host identifiers without echoing unrelated YAML."""

    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ConfigurationError(f"Duplicate {label} id '{value}' found.", label=label, value=value)
        seen.add(value)


def _resolve_workspace_root(config_path: Path) -> Path:
    """Returns the repository-style workspace root for relative host paths."""

    return config_path.parent.parent if config_path.parent.name == "config" else config_path.parent
