"""Typed configuration models for stable emulator and account inputs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pnc_automation.artifact_naming import format_castle_artifact_directory
from pnc_automation.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class DefaultsConfig:
    """Shared timing and transport defaults applied across runs."""

    adb_path: str = "adb"
    screenshot_format: str = "png"
    stable_click_delay_ms: int = 300
    post_action_observe_delay_ms: int = 800


@dataclass(frozen=True, slots=True)
class BlueStacksInstanceConfig:
    """Binds one automation target to one ADB device and app package."""

    id: str
    device_id: str
    app_package: str


@dataclass(frozen=True, slots=True)
class SelectedCastleConfig:
    """Identifies the single castle managed for one account target."""

    kingdom: str
    castle_name: str
    castle_level: int | None = None

    @property
    def artifact_directory_name(self) -> str:
        """Returns the canonical artifact directory name for this castle."""

        return format_castle_artifact_directory(kingdom=self.kingdom, castle_name=self.castle_name)


class CredentialSource(StrEnum):
    """Identifies where login credentials were loaded from."""

    INLINE = "inline"
    ENVIRONMENT = "environment"


@dataclass(frozen=True, slots=True)
class ResolvedCredentials:
    """Holds resolved login secrets in memory after startup validation."""

    username: str
    password: str
    source: CredentialSource
    username_ref: str | None = None
    password_ref: str | None = None


class CastleRosterOrdering(StrEnum):
    """Describes whether a cached castle roster preserves trustworthy in-game ordering."""

    UNKNOWN = "unknown"
    FULL_SCAN = "full_scan"


@dataclass(frozen=True, slots=True)
class AccountConfig:
    """Represents one automation target bound to one emulator instance and one identified P&C login."""

    id: str
    instance_id: str
    pnc_account_id: str
    selected_castle: SelectedCastleConfig
    credentials: ResolvedCredentials | None = None

    @property
    def login_enabled(self) -> bool:
        """Returns whether this account can perform credential-based login."""

        return self.credentials is not None

    @property
    def artifact_directory_name(self) -> str:
        """Returns the canonical artifact directory name for this account's selected castle."""

        return self.selected_castle.artifact_directory_name


@dataclass(frozen=True, slots=True)
class PncAccountCastleRosterConfig:
    """Declares the discovered castle roster cache for one identified P&C username."""

    pnc_account_id: str
    castles: tuple[SelectedCastleConfig, ...]
    ordering: CastleRosterOrdering = CastleRosterOrdering.UNKNOWN

    @property
    def has_trusted_ordering(self) -> bool:
        """Returns whether the cached roster can drive directional off-screen scrolling."""

        return self.ordering == CastleRosterOrdering.FULL_SCAN


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Owns the canonical loaded configuration for one workspace."""

    config_path: Path
    castle_roster_path: Path
    artifact_root: Path
    defaults: DefaultsConfig
    instances: tuple[BlueStacksInstanceConfig, ...]
    accounts: tuple[AccountConfig, ...]
    castle_rosters: tuple[PncAccountCastleRosterConfig, ...] = ()

    def require_instance(self, instance_id: str) -> BlueStacksInstanceConfig:
        """Returns a known emulator instance or fails fast."""

        for instance in self.instances:
            if instance.id == instance_id:
                return instance
        raise ConfigurationError(f"Unknown instance id '{instance_id}'.", instance_id=instance_id)

    def require_account(self, account_id: str) -> AccountConfig:
        """Returns a known account target or fails fast."""

        for account in self.accounts:
            if account.id == account_id:
                return account
        raise ConfigurationError(f"Unknown account id '{account_id}'.", account_id=account_id)

    def find_castle_roster(self, pnc_account_id: str) -> PncAccountCastleRosterConfig | None:
        """Returns the cached castle roster for one P&C login when available."""

        for roster in self.castle_rosters:
            if roster.pnc_account_id == pnc_account_id:
                return roster
        return None
