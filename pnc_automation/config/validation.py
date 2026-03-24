"""Validation helpers for loaded application configuration."""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path

from pnc_automation.config.models import (
    AccountCastleTargetsConfig,
    AccountConfig,
    AppConfig,
    PncAccountCastleRosterConfig,
    castle_identity_key,
)
from pnc_automation.errors import ConfigurationError


def validate_app_config(config: AppConfig) -> AppConfig:
    """Validates the loaded configuration and returns it when consistent."""

    _validate_unique_ids("instance", (instance.id for instance in config.instances))
    _validate_unique_ids("account", (account.id for account in config.accounts))
    _validate_unique_runtime_targets(config.accounts)
    _validate_unique_account_artifact_directories(config.accounts)

    instance_ids = {instance.id for instance in config.instances}
    for account in config.accounts:
        _validate_account(account, instance_ids)

    _validate_shared_pnc_credentials(config.accounts)
    _validate_castle_rosters(config)
    _validate_castle_targets(config)
    _validate_artifact_root(config)
    _validate_archive_root(config)
    _validate_distinct_output_roots(config)
    return config


def _validate_unique_ids(label: str, values: Iterable[str]) -> None:
    """Ensures identifiers are unique within one configuration section."""

    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ConfigurationError(f"Duplicate {label} id '{value}' found.", label=label, value=value)
        seen.add(value)


def _validate_account(account: AccountConfig, instance_ids: set[str]) -> None:
    """Validates one account binding and its login identity contract."""

    if account.instance_id not in instance_ids:
        raise ConfigurationError(
            f"Account '{account.id}' references unknown instance '{account.instance_id}'.",
            account_id=account.id,
            instance_id=account.instance_id,
        )
    if account.pnc_account_id.strip() == "":
        raise ConfigurationError(
            f"Account '{account.id}' has an empty P&C account identifier.",
            account_id=account.id,
        )
    if account.login_enabled:
        credentials = account.credentials
        if credentials is None or credentials.username.strip() == "" or credentials.password.strip() == "":
            raise ConfigurationError(
                f"Account '{account.id}' is missing resolved login credentials.",
                account_id=account.id,
            )
        if account.pnc_account_id != credentials.username:
            raise ConfigurationError(
                f"Account '{account.id}' must use pnc_account_id equal to the P&C username.",
                account_id=account.id,
                pnc_account_id=account.pnc_account_id,
                username=credentials.username,
            )


def _validate_unique_runtime_targets(accounts: tuple[AccountConfig, ...]) -> None:
    """Ensures one BlueStacks/P&C login pair maps to only one configured account target."""

    seen: dict[tuple[str, str], str] = {}
    for account in accounts:
        target_key = (account.instance_id, account.pnc_account_id)
        if target_key in seen:
            raise ConfigurationError(
                "Each (instance_id, pnc_account_id) pair may define only one configured account target.",
                instance_id=account.instance_id,
                pnc_account_id=account.pnc_account_id,
                first_account_id=seen[target_key],
                duplicate_account_id=account.id,
            )
        seen[target_key] = account.id


def _validate_unique_account_artifact_directories(accounts: tuple[AccountConfig, ...]) -> None:
    """Ensures normalized per-account artifact directories cannot collide at runtime."""

    seen: dict[str, str] = {}
    for account in accounts:
        artifact_directory = account.artifact_directory_name
        if artifact_directory in seen:
            raise ConfigurationError(
                "Accounts must not collide after artifact-directory normalization.",
                artifact_directory=artifact_directory,
                first_account_id=seen[artifact_directory],
                duplicate_account_id=account.id,
            )
        seen[artifact_directory] = account.id


def _validate_shared_pnc_credentials(accounts: tuple[AccountConfig, ...]) -> None:
    """Ensures one identified P&C login resolves to one canonical credential set."""

    seen: dict[str, tuple[str | None, str | None]] = {}
    for account in accounts:
        credentials = account.credentials
        current = None if credentials is None else (credentials.username, credentials.password)
        if account.pnc_account_id not in seen:
            seen[account.pnc_account_id] = current
            continue
        if seen[account.pnc_account_id] != current:
            raise ConfigurationError(
                "Accounts sharing the same pnc_account_id must use the same resolved credentials.",
                pnc_account_id=account.pnc_account_id,
                account_id=account.id,
            )


def _validate_castle_rosters(config: AppConfig) -> None:
    """Validates the optional castle-roster cache for internal consistency only."""

    if not config.castle_rosters:
        return
    _validate_unique_ids("pnc account roster", (roster.pnc_account_id for roster in config.castle_rosters))
    for roster in config.castle_rosters:
        _validate_roster_entries(roster)


def _validate_castle_targets(config: AppConfig) -> None:
    """Validates the optional authored castle-target file for internal consistency."""

    if not config.castle_targets:
        return
    _validate_unique_ids("account castle target", (targets.account_id for targets in config.castle_targets))
    account_ids = {account.id for account in config.accounts}
    for targets in config.castle_targets:
        _validate_account_castle_targets(targets, account_ids)


def _validate_account_castle_targets(targets: AccountCastleTargetsConfig, account_ids: set[str]) -> None:
    """Ensures authored castle targets reference a real account and use unique aliases."""

    if targets.account_id not in account_ids:
        raise ConfigurationError(
            f"Castle-target config references unknown account '{targets.account_id}'.",
            account_id=targets.account_id,
        )
    if not targets.targets:
        raise ConfigurationError(
            f"Castle-target config for account '{targets.account_id}' must define at least one alias.",
            account_id=targets.account_id,
        )
    seen: set[str] = set()
    for target in targets.targets:
        if target.target_id in seen:
            raise ConfigurationError(
                f"Account '{targets.account_id}' contains a duplicate castle target alias.",
                account_id=targets.account_id,
                castle_ref=target.target_id,
            )
        seen.add(target.target_id)


def _validate_roster_entries(roster: PncAccountCastleRosterConfig) -> None:
    """Ensures one roster does not define the same castle identity twice."""

    seen: set[tuple[str, str]] = set()
    for castle in roster.castles:
        castle_key = castle_identity_key(castle)
        if castle_key in seen:
            raise ConfigurationError(
                f"P&C account roster '{roster.pnc_account_id}' contains a duplicate castle entry.",
                pnc_account_id=roster.pnc_account_id,
                kingdom=castle.kingdom,
                castle_name=castle.castle_name,
            )
        seen.add(castle_key)


def _validate_artifact_root(config: AppConfig) -> None:
    """Ensures the artifact root exists and is writable before a run starts."""

    config.artifact_root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(dir=config.artifact_root, delete=True):
            return
    except OSError as error:
        raise ConfigurationError(
            f"Artifact root '{config.artifact_root}' is not writable.",
            artifact_root=str(config.artifact_root),
        ) from error


def _validate_archive_root(config: AppConfig) -> None:
    """Ensures the archive root exists and is writable before a run starts."""

    config.archive_root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(dir=config.archive_root, delete=True):
            return
    except OSError as error:
        raise ConfigurationError(
            f"Archive root '{config.archive_root}' is not writable.",
            archive_root=str(config.archive_root),
        ) from error


def _validate_distinct_output_roots(config: AppConfig) -> None:
    """Rejects configurations that collapse durable archives into runtime artifacts."""

    if _paths_overlap(config.artifact_root, config.archive_root):
        raise ConfigurationError(
            "artifact_root and archive_root must resolve to separate non-overlapping directories.",
            artifact_root=str(config.artifact_root),
            archive_root=str(config.archive_root),
        )


def _paths_overlap(first: Path, second: Path) -> bool:
    """Returns whether two resolved paths are equal or nested inside one another."""

    return _path_contains(first, second) or _path_contains(second, first)


def _path_contains(parent: Path, child: Path) -> bool:
    """Returns whether one resolved path is the same as or an ancestor of another."""

    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True
