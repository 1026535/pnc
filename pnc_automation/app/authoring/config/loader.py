"""Loads YAML configuration into typed automation models."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    AccountCastleTargetsConfig,
    AppConfig,
    BlueStacksInstanceConfig,
    CastleRosterOrdering,
    CastleTargetDefinition,
    CredentialSource,
    DEFAULT_BLUESTACKS_CONFIG_PATH,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
    RuntimeConfig,
)
from pnc_automation.app.runtime.observation_mode import ObservationMode
from pnc_automation.app.authoring.config.validation import validate_app_config
from pnc_automation.app.authoring.config.yaml_helpers import (
    load_castle_identity,
    require_int,
    require_list,
    require_mapping,
    require_string,
)
from pnc_automation.core.errors import ConfigurationError


def load_app_config(
    path: str | Path,
    env: Mapping[str, str] | None = None,
    castle_roster_path: str | Path | None = None,
    castle_targets_path: str | Path | None = None,
    mail_definitions_path: str | Path | None = None,
    mail_schedules_path: str | Path | None = None,
) -> AppConfig:
    """Loads and validates the canonical application configuration file."""

    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise ConfigurationError(f"Configuration file '{config_path}' does not exist.", path=str(config_path))

    with config_path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}

    raw = require_mapping(raw_data, context="config root")
    environment = env if env is not None else os.environ
    workspace_root = _resolve_workspace_root(config_path)

    defaults = _load_defaults(raw.get("defaults"), workspace_root=workspace_root)
    artifact_root = _load_artifact_root(raw.get("artifacts"), workspace_root)
    archive_root = _load_archive_root(raw.get("archives"), workspace_root)
    runtime = _load_runtime(raw.get("runtime"))
    instances = _load_instances(raw.get("instances"))
    accounts = _load_accounts(raw.get("accounts"), environment)
    resolved_castle_roster_path = _resolve_castle_roster_path(config_path, castle_roster_path)
    resolved_castle_targets_path = _resolve_castle_targets_path(config_path, castle_targets_path)
    resolved_mail_definitions_path = _resolve_mail_definitions_path(config_path, mail_definitions_path)
    resolved_mail_schedules_path = _resolve_mail_schedules_path(config_path, mail_schedules_path)
    rosters = _load_castle_rosters(resolved_castle_roster_path)
    castle_targets = _load_account_castle_targets(resolved_castle_targets_path)

    return validate_app_config(
        AppConfig(
            config_path=config_path,
            castle_roster_path=resolved_castle_roster_path,
            castle_targets_path=resolved_castle_targets_path,
            mail_definitions_path=resolved_mail_definitions_path,
            mail_schedules_path=resolved_mail_schedules_path,
            artifact_root=artifact_root,
            archive_root=archive_root,
            defaults=defaults,
            runtime=runtime,
            instances=instances,
            accounts=accounts,
            castle_rosters=rosters,
            castle_targets=castle_targets,
        )
    )


def _load_defaults(raw_defaults: Any, *, workspace_root: Path) -> DefaultsConfig:
    """Loads the defaults section with sensible v1 fallbacks."""

    raw = require_mapping(raw_defaults or {}, context="defaults")
    return DefaultsConfig(
        adb_path=require_string(raw.get("adb_path", "adb"), context="defaults.adb_path"),
        bluestacks_config_path=_load_bluestacks_config_path(
            raw.get("bluestacks_config_path", str(DEFAULT_BLUESTACKS_CONFIG_PATH)),
            workspace_root=workspace_root,
        ),
        screenshot_format=require_string(raw.get("screenshot_format", "png"), context="defaults.screenshot_format"),
        stable_click_delay_ms=require_int(
            raw.get("stable_click_delay_ms", 300),
            context="defaults.stable_click_delay_ms",
        ),
        post_action_observe_delay_ms=require_int(
            raw.get("post_action_observe_delay_ms", 800),
            context="defaults.post_action_observe_delay_ms",
        ),
        chat_stable_click_delay_ms=require_int(
            raw.get("chat_stable_click_delay_ms", 120),
            context="defaults.chat_stable_click_delay_ms",
        ),
        chat_post_action_observe_delay_ms=require_int(
            raw.get("chat_post_action_observe_delay_ms", 250),
            context="defaults.chat_post_action_observe_delay_ms",
        ),
        world_map_movement_stable_click_delay_ms=require_int(
            raw.get("world_map_movement_stable_click_delay_ms", raw.get("stable_click_delay_ms", 300)),
            context="defaults.world_map_movement_stable_click_delay_ms",
        ),
        world_map_movement_post_action_observe_delay_ms=require_int(
            raw.get("world_map_movement_post_action_observe_delay_ms", raw.get("post_action_observe_delay_ms", 800)),
            context="defaults.world_map_movement_post_action_observe_delay_ms",
        ),
    )


def _resolve_workspace_root(config_path: Path) -> Path:
    """Returns the workspace root used for repo-owned relative paths.

    The canonical repository layout stores runtime configs under ``config/`` at the
    workspace root. Relative artifact paths must therefore resolve from the parent of
    that directory instead of nesting under ``config/``. Standalone configs outside a
    ``config`` directory continue to resolve relative paths from their own directory.
    """

    config_dir = config_path.parent
    if config_dir.name == "config":
        return config_dir.parent
    return config_dir


def _load_artifact_root(raw_artifacts: Any, workspace_root: Path) -> Path:
    """Loads and resolves the artifact root relative to the workspace root."""

    raw = require_mapping(raw_artifacts or {}, context="artifacts")
    artifact_root = require_string(raw.get("root", "artifacts"), context="artifacts.root")
    return (workspace_root / artifact_root).resolve()


def _load_archive_root(raw_archives: Any, workspace_root: Path) -> Path:
    """Loads and resolves the durable archive root relative to the workspace root."""

    raw = require_mapping(raw_archives or {}, context="archives")
    archive_root = require_string(raw.get("root", "archives"), context="archives.root")
    return (workspace_root / archive_root).resolve()


def _load_runtime(raw_runtime: Any) -> RuntimeConfig:
    """Loads shared runtime policy toggles."""

    raw = require_mapping(raw_runtime or {}, context="runtime")
    observation_mode = require_string(
        raw.get("observation_mode", ObservationMode.DEBUG.value),
        context="runtime.observation_mode",
    )
    try:
        return RuntimeConfig(observation_mode=ObservationMode(observation_mode))
    except ValueError as error:
        raise ConfigurationError(
            f"Expected runtime.observation_mode to be one of {[mode.value for mode in ObservationMode]}.",
            context="runtime.observation_mode",
            observation_mode=observation_mode,
        ) from error


def _load_bluestacks_config_path(raw_path: Any, *, workspace_root: Path) -> Path:
    """Loads the canonical BlueStacks host-metadata path used for runtime port resolution."""

    path = Path(require_string(raw_path, context="defaults.bluestacks_config_path"))
    if path.is_absolute():
        return path
    return (workspace_root / path).resolve()


def _load_instances(raw_instances: Any) -> tuple[BlueStacksInstanceConfig, ...]:
    """Loads the configured BlueStacks bindings."""

    items = require_list(raw_instances or [], context="instances")
    instances: list[BlueStacksInstanceConfig] = []
    for index, item in enumerate(items):
        raw = require_mapping(item, context=f"instances[{index}]")
        _reject_legacy_instance_device_id(raw, index=index)
        instances.append(
            BlueStacksInstanceConfig(
                id=require_string(raw.get("id"), context=f"instances[{index}].id"),
                display_name=require_string(raw.get("display_name"), context=f"instances[{index}].display_name"),
                app_package=require_string(raw.get("app_package"), context=f"instances[{index}].app_package"),
            )
        )
    return tuple(instances)


def _reject_legacy_instance_device_id(raw_instance: Mapping[str, Any], *, index: int) -> None:
    """Rejects the removed authored ADB endpoint field instead of silently accepting stale ports."""

    if "device_id" not in raw_instance:
        return
    raise ConfigurationError(
        "accounts.yaml no longer supports instances[].device_id; configure the stable BlueStacks display_name and let runtime port discovery resolve the live ADB endpoint.",
        context=f"instances[{index}].device_id",
    )


def _load_accounts(raw_accounts: Any, env: Mapping[str, str]) -> tuple[AccountConfig, ...]:
    """Loads account targets and resolves their configured credentials."""

    items = require_list(raw_accounts or [], context="accounts")
    accounts: list[AccountConfig] = []
    for index, item in enumerate(items):
        raw = require_mapping(item, context=f"accounts[{index}]")
        _reject_legacy_selected_castle(raw, index=index)
        credentials = _load_credentials(raw, env, index=index)
        accounts.append(
            AccountConfig(
                id=require_string(raw.get("id"), context=f"accounts[{index}].id"),
                instance_id=require_string(raw.get("instance_id"), context=f"accounts[{index}].instance_id"),
                pnc_account_id=require_string(raw.get("pnc_account_id"), context=f"accounts[{index}].pnc_account_id"),
                credentials=credentials,
            )
        )
    return tuple(accounts)


def _reject_legacy_selected_castle(raw_account: Mapping[str, Any], *, index: int) -> None:
    """Rejects the removed account-level castle field instead of silently ignoring it."""

    if "selected_castle" not in raw_account:
        return
    raise ConfigurationError(
        "accounts.yaml no longer supports account-level 'selected_castle'; move authored castle aliases into castle_targets.yaml and reference them from scripts with 'castle_ref'.",
        context=f"accounts[{index}].selected_castle",
    )


def _resolve_castle_roster_path(config_path: Path, castle_roster_path: str | Path | None) -> Path:
    """Resolves the optional sibling castle-roster configuration path."""

    if castle_roster_path is None:
        return (config_path.parent / "castles.yaml").resolve()
    return Path(castle_roster_path).resolve()


def _resolve_castle_targets_path(config_path: Path, castle_targets_path: str | Path | None) -> Path:
    """Resolves the optional sibling castle-target configuration path."""

    if castle_targets_path is None:
        return (config_path.parent / "castle_targets.yaml").resolve()
    return Path(castle_targets_path).resolve()


def _resolve_mail_definitions_path(config_path: Path, mail_definitions_path: str | Path | None) -> Path:
    """Resolves the optional sibling mail-definition configuration path."""

    if mail_definitions_path is None:
        return (config_path.parent / "mail_definitions.yaml").resolve()
    return Path(mail_definitions_path).resolve()


def _resolve_mail_schedules_path(config_path: Path, mail_schedules_path: str | Path | None) -> Path:
    """Resolves the optional sibling mail-schedule configuration path."""

    if mail_schedules_path is None:
        return (config_path.parent / "mail_schedules.yaml").resolve()
    return Path(mail_schedules_path).resolve()


def _load_castle_rosters(path: Path) -> tuple[PncAccountCastleRosterConfig, ...]:
    """Loads the optional castle-roster file keyed by P&C account id."""

    if not path.is_file():
        return ()
    with path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}
    raw = require_mapping(raw_data, context="castle roster root")
    items = require_list(raw.get("pnc_accounts") or [], context="pnc_accounts")

    rosters: list[PncAccountCastleRosterConfig] = []
    for index, item in enumerate(items):
        roster = require_mapping(item, context=f"pnc_accounts[{index}]")
        raw_castles = require_list(roster.get("castles") or [], context=f"pnc_accounts[{index}].castles")
        castles = tuple(
            load_castle_identity(
                raw_castle,
                context=f"pnc_accounts[{index}].castles[{castle_index}]",
            )
            for castle_index, raw_castle in enumerate(raw_castles)
        )
        rosters.append(
            PncAccountCastleRosterConfig(
                pnc_account_id=require_string(
                    roster.get("pnc_account_id"),
                    context=f"pnc_accounts[{index}].pnc_account_id",
                ),
                castles=castles,
                ordering=_load_castle_roster_ordering(
                    roster.get("ordering"),
                    context=f"pnc_accounts[{index}].ordering",
                ),
            )
        )
    return tuple(rosters)


def _load_account_castle_targets(path: Path) -> tuple[AccountCastleTargetsConfig, ...]:
    """Loads the optional authored castle-target file keyed by configured account id."""

    if not path.is_file():
        return ()
    with path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}
    raw = require_mapping(raw_data, context="castle target root")
    items = require_list(raw.get("accounts") or [], context="accounts")

    account_targets: list[AccountCastleTargetsConfig] = []
    for index, item in enumerate(items):
        account = require_mapping(item, context=f"accounts[{index}]")
        raw_targets_value = account.get("castle_targets")
        raw_targets = require_mapping(
            {} if raw_targets_value is None else raw_targets_value,
            context=f"accounts[{index}].castle_targets",
        )
        targets = tuple(
            CastleTargetDefinition(
                target_id=require_string(target_id, context=f"accounts[{index}].castle_targets key"),
                castle=load_castle_identity(
                    raw_castle,
                    context=f"accounts[{index}].castle_targets.{target_id}",
                ),
            )
            for target_id, raw_castle in raw_targets.items()
        )
        account_targets.append(
            AccountCastleTargetsConfig(
                account_id=require_string(account.get("account_id"), context=f"accounts[{index}].account_id"),
                targets=targets,
            )
        )
    return tuple(account_targets)


def _load_castle_roster_ordering(value: Any, *, context: str) -> CastleRosterOrdering:
    """Loads the explicit roster-ordering metadata used by directional castle scrolling."""

    if value is None:
        return CastleRosterOrdering.UNKNOWN
    raw_value = require_string(value, context=context)
    try:
        return CastleRosterOrdering(raw_value)
    except ValueError as error:
        raise ConfigurationError(
            f"Expected {context} to be one of {[ordering.value for ordering in CastleRosterOrdering]}.",
            context=context,
            ordering=raw_value,
        ) from error


def _load_credentials(raw_account: Mapping[str, Any], env: Mapping[str, str], *, index: int) -> ResolvedCredentials | None:
    """Resolves login credentials from either inline config or environment references."""

    inline_username = raw_account.get("username")
    inline_password = raw_account.get("password")
    username_env = raw_account.get("username_env")
    password_env = raw_account.get("password_env")

    has_inline_credentials = inline_username is not None or inline_password is not None
    has_environment_credentials = username_env is not None or password_env is not None

    if not has_inline_credentials and not has_environment_credentials:
        return None
    if has_inline_credentials and has_environment_credentials:
        raise ConfigurationError(
            f"Account at index {index} must use either inline credentials or environment-variable credentials, not both.",
            account_index=index,
        )
    if has_inline_credentials:
        return _load_inline_credentials(inline_username, inline_password, index=index)
    return _load_environment_credentials(username_env, password_env, env, index=index)


def _load_inline_credentials(username: Any, password: Any, *, index: int) -> ResolvedCredentials:
    """Loads credentials embedded directly in the repository config file."""

    if username is None or password is None:
        raise ConfigurationError(
            f"Account at index {index} must define both username and password or neither.",
            account_index=index,
        )
    return ResolvedCredentials(
        username=require_string(username, context=f"accounts[{index}].username"),
        password=require_string(password, context=f"accounts[{index}].password"),
        source=CredentialSource.INLINE,
    )


def _load_environment_credentials(
    username_env: Any,
    password_env: Any,
    env: Mapping[str, str],
    *,
    index: int,
) -> ResolvedCredentials:
    """Loads credentials from referenced environment variables."""

    if username_env is None or password_env is None:
        raise ConfigurationError(
            f"Account at index {index} must define both username_env and password_env or neither.",
            account_index=index,
        )

    username_key = require_string(username_env, context=f"accounts[{index}].username_env")
    password_key = require_string(password_env, context=f"accounts[{index}].password_env")
    if username_key not in env:
        raise ConfigurationError(
            f"Missing required environment variable '{username_key}'.",
            account_index=index,
            environment_variable=username_key,
        )
    if password_key not in env:
        raise ConfigurationError(
            f"Missing required environment variable '{password_key}'.",
            account_index=index,
            environment_variable=password_key,
        )

    return ResolvedCredentials(
        username=require_string(env[username_key], context=username_key),
        password=require_string(env[password_key], context=password_key),
        source=CredentialSource.ENVIRONMENT,
        username_ref=username_key,
        password_ref=password_key,
    )
