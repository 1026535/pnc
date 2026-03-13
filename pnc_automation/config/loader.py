"""Loads YAML configuration into typed automation models."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from pnc_automation.config.models import (
    AccountConfig,
    AppConfig,
    BlueStacksInstanceConfig,
    CastleRosterOrdering,
    CredentialSource,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
    SelectedCastleConfig,
)
from pnc_automation.config.validation import validate_app_config
from pnc_automation.errors import ConfigurationError


def load_app_config(
    path: str | Path,
    env: Mapping[str, str] | None = None,
    castle_roster_path: str | Path | None = None,
) -> AppConfig:
    """Loads and validates the canonical application configuration file."""

    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise ConfigurationError(f"Configuration file '{config_path}' does not exist.", path=str(config_path))

    with config_path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}

    raw = _require_mapping(raw_data, context="config root")
    environment = env if env is not None else os.environ
    workspace_root = _resolve_workspace_root(config_path)

    defaults = _load_defaults(raw.get("defaults"))
    artifact_root = _load_artifact_root(raw.get("artifacts"), workspace_root)
    instances = _load_instances(raw.get("instances"))
    accounts = _load_accounts(raw.get("accounts"), environment)
    resolved_castle_roster_path = _resolve_castle_roster_path(config_path, castle_roster_path)
    rosters = _load_castle_rosters(resolved_castle_roster_path)

    return validate_app_config(
        AppConfig(
            config_path=config_path,
            castle_roster_path=resolved_castle_roster_path,
            artifact_root=artifact_root,
            defaults=defaults,
            instances=instances,
            accounts=accounts,
            castle_rosters=rosters,
        )
    )


def _load_defaults(raw_defaults: Any) -> DefaultsConfig:
    """Loads the defaults section with sensible v1 fallbacks."""

    raw = _require_mapping(raw_defaults or {}, context="defaults")
    return DefaultsConfig(
        adb_path=_require_string(raw.get("adb_path", "adb"), context="defaults.adb_path"),
        screenshot_format=_require_string(raw.get("screenshot_format", "png"), context="defaults.screenshot_format"),
        stable_click_delay_ms=_require_int(
            raw.get("stable_click_delay_ms", 300),
            context="defaults.stable_click_delay_ms",
        ),
        post_action_observe_delay_ms=_require_int(
            raw.get("post_action_observe_delay_ms", 800),
            context="defaults.post_action_observe_delay_ms",
        ),
        chat_stable_click_delay_ms=_require_int(
            raw.get("chat_stable_click_delay_ms", 120),
            context="defaults.chat_stable_click_delay_ms",
        ),
        chat_post_action_observe_delay_ms=_require_int(
            raw.get("chat_post_action_observe_delay_ms", 250),
            context="defaults.chat_post_action_observe_delay_ms",
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

    raw = _require_mapping(raw_artifacts or {}, context="artifacts")
    artifact_root = _require_string(raw.get("root", "artifacts"), context="artifacts.root")
    return (workspace_root / artifact_root).resolve()


def _load_instances(raw_instances: Any) -> tuple[BlueStacksInstanceConfig, ...]:
    """Loads the configured BlueStacks bindings."""

    items = _require_list(raw_instances or [], context="instances")
    instances: list[BlueStacksInstanceConfig] = []
    for index, item in enumerate(items):
        raw = _require_mapping(item, context=f"instances[{index}]")
        instances.append(
            BlueStacksInstanceConfig(
                id=_require_string(raw.get("id"), context=f"instances[{index}].id"),
                device_id=_require_string(raw.get("device_id"), context=f"instances[{index}].device_id"),
                app_package=_require_string(raw.get("app_package"), context=f"instances[{index}].app_package"),
            )
        )
    return tuple(instances)


def _load_accounts(raw_accounts: Any, env: Mapping[str, str]) -> tuple[AccountConfig, ...]:
    """Loads account targets and resolves their configured credentials."""

    items = _require_list(raw_accounts or [], context="accounts")
    accounts: list[AccountConfig] = []
    for index, item in enumerate(items):
        raw = _require_mapping(item, context=f"accounts[{index}]")
        selected_castle = _load_selected_castle(raw.get("selected_castle"), index=index)
        credentials = _load_credentials(raw, env, index=index)
        accounts.append(
            AccountConfig(
                id=_require_string(raw.get("id"), context=f"accounts[{index}].id"),
                instance_id=_require_string(raw.get("instance_id"), context=f"accounts[{index}].instance_id"),
                pnc_account_id=_require_string(raw.get("pnc_account_id"), context=f"accounts[{index}].pnc_account_id"),
                selected_castle=selected_castle,
                credentials=credentials,
            )
        )
    return tuple(accounts)


def _resolve_castle_roster_path(config_path: Path, castle_roster_path: str | Path | None) -> Path:
    """Resolves the optional sibling castle-roster configuration path."""

    if castle_roster_path is None:
        return (config_path.parent / "castles.yaml").resolve()
    return Path(castle_roster_path).resolve()


def _load_castle_rosters(path: Path) -> tuple[PncAccountCastleRosterConfig, ...]:
    """Loads the optional castle-roster file keyed by P&C account id."""

    if not path.is_file():
        return ()
    with path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}
    raw = _require_mapping(raw_data, context="castle roster root")
    items = _require_list(raw.get("pnc_accounts") or [], context="pnc_accounts")

    rosters: list[PncAccountCastleRosterConfig] = []
    for index, item in enumerate(items):
        roster = _require_mapping(item, context=f"pnc_accounts[{index}]")
        raw_castles = _require_list(roster.get("castles") or [], context=f"pnc_accounts[{index}].castles")
        castles = tuple(_load_castle_entry(raw_castle, context=f"pnc_accounts[{index}].castles[{castle_index}]") for castle_index, raw_castle in enumerate(raw_castles))
        rosters.append(
            PncAccountCastleRosterConfig(
                pnc_account_id=_require_string(roster.get("pnc_account_id"), context=f"pnc_accounts[{index}].pnc_account_id"),
                castles=castles,
                ordering=_load_castle_roster_ordering(
                    roster.get("ordering"),
                    context=f"pnc_accounts[{index}].ordering",
                ),
            )
        )
    return tuple(rosters)


def _load_selected_castle(raw_castle: Any, *, index: int) -> SelectedCastleConfig:
    """Loads the single selected castle contract for one account target."""

    return _load_castle_entry(raw_castle, context=f"accounts[{index}].selected_castle")


def _load_castle_entry(raw_castle: Any, *, context: str) -> SelectedCastleConfig:
    """Loads one castle identity entry shared by runtime targets and account rosters."""

    raw = _require_mapping(raw_castle, context=context)
    level_value = raw.get("castle_level")
    return SelectedCastleConfig(
        kingdom=_require_kingdom_identifier(raw.get("kingdom"), context=f"{context}.kingdom"),
        castle_name=_require_string(raw.get("castle_name"), context=f"{context}.castle_name"),
        castle_level=None if level_value is None else _require_int(level_value, context=f"{context}.castle_level"),
    )


def _load_castle_roster_ordering(value: Any, *, context: str) -> CastleRosterOrdering:
    """Loads the explicit roster-ordering metadata used by directional castle scrolling."""

    if value is None:
        return CastleRosterOrdering.UNKNOWN
    raw_value = _require_string(value, context=context)
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
        username=_require_string(username, context=f"accounts[{index}].username"),
        password=_require_string(password, context=f"accounts[{index}].password"),
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

    username_key = _require_string(username_env, context=f"accounts[{index}].username_env")
    password_key = _require_string(password_env, context=f"accounts[{index}].password_env")
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
        username=_require_string(env[username_key], context=username_key),
        password=_require_string(env[password_key], context=password_key),
        source=CredentialSource.ENVIRONMENT,
        username_ref=username_key,
        password_ref=password_key,
    )


def _require_mapping(value: Any, *, context: str) -> dict[str, Any]:
    """Ensures a YAML node is a mapping with string keys."""

    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected {context} to be a mapping.", context=context)
    invalid_keys = [key for key in value if not isinstance(key, str)]
    if invalid_keys:
        raise ConfigurationError(f"Expected {context} keys to be strings.", context=context)
    return dict(value)


def _require_list(value: Any, *, context: str) -> list[Any]:
    """Ensures a YAML node is a list."""

    if not isinstance(value, list):
        raise ConfigurationError(f"Expected {context} to be a list.", context=context)
    return list(value)


def _require_string(value: Any, *, context: str) -> str:
    """Ensures a YAML scalar is a non-empty string."""

    if not isinstance(value, str) or value.strip() == "":
        raise ConfigurationError(f"Expected {context} to be a non-empty string.", context=context)
    return value


def _require_kingdom_identifier(value: Any, *, context: str) -> str:
    """Ensures one kingdom identifier uses the canonical ``K###``-style format."""

    kingdom = _require_string(value, context=context)
    if re.fullmatch(r"K\d{2,4}", kingdom) is None:
        raise ConfigurationError(
            f"Expected {context} to use canonical kingdom format 'K###'.",
            context=context,
            kingdom=kingdom,
        )
    return kingdom


def _require_int(value: Any, *, context: str) -> int:
    """Ensures a YAML scalar is an integer."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"Expected {context} to be an integer.", context=context)
    return value
