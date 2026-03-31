"""Typed configuration models for stable emulator and account inputs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pnc_automation.app.runtime.observation_mode import ObservationMode
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.emulator.models import BlueStacksInstanceConfig
from pnc_automation.core.infra.storage.artifact_naming import format_account_artifact_directory

if TYPE_CHECKING:
    from pnc_automation.app.authoring.mail.models import MailScheduleCatalog


DEFAULT_BLUESTACKS_CONFIG_PATH = Path(r"C:\ProgramData\BlueStacks_nxt\bluestacks.conf")


@dataclass(frozen=True, slots=True)
class DefaultsConfig:
    """Shared timing and transport defaults applied across runs."""

    adb_path: str = "adb"
    bluestacks_config_path: Path = DEFAULT_BLUESTACKS_CONFIG_PATH
    screenshot_format: str = "png"
    stable_click_delay_ms: int = 300
    post_action_observe_delay_ms: int = 800
    chat_stable_click_delay_ms: int = 120
    chat_post_action_observe_delay_ms: int = 250


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Owns shared runtime policy toggles that are not tied to emulator timings."""

    observation_mode: ObservationMode = ObservationMode.DEBUG


@dataclass(frozen=True, slots=True)
class CastleIdentity:
    """Identifies one castle across authored targets, rosters, and observations."""

    kingdom: str
    castle_name: str
    castle_level: int | None = None


def castle_identity_key(castle: CastleIdentity) -> tuple[str, str]:
    """Returns the stable kingdom/name identity key shared across roster and observation code."""

    return (castle.kingdom, castle.castle_name)


@dataclass(frozen=True, slots=True)
class CastleTargetDefinition:
    """Binds one authored target alias to one canonical castle identity."""

    target_id: str
    castle: CastleIdentity


@dataclass(frozen=True, slots=True)
class AccountCastleTargetsConfig:
    """Owns the authored castle-target aliases available for one configured account id."""

    account_id: str
    targets: tuple[CastleTargetDefinition, ...]

    def require(self, target_id: str) -> CastleIdentity:
        """Returns the configured castle target for one alias or fails fast."""

        for target in self.targets:
            if target.target_id == target_id:
                return target.castle
        raise ConfigurationError(
            f"Account '{self.account_id}' does not define castle target '{target_id}'.",
            account_id=self.account_id,
            castle_ref=target_id,
        )

    def find(self, target_id: str) -> CastleIdentity | None:
        """Returns the configured castle target for one alias when it exists."""

        for target in self.targets:
            if target.target_id == target_id:
                return target.castle
        return None


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
    credentials: ResolvedCredentials | None = None

    @property
    def login_enabled(self) -> bool:
        """Returns whether this account can perform credential-based login."""

        return self.credentials is not None

    @property
    def artifact_directory_name(self) -> str:
        """Returns the canonical artifact directory name for this configured account target."""

        return format_account_artifact_directory(account_id=self.id)


@dataclass(frozen=True, slots=True)
class PncAccountCastleRosterConfig:
    """Declares the discovered castle roster cache for one identified P&C username."""

    pnc_account_id: str
    castles: tuple[CastleIdentity, ...]
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
    castle_targets_path: Path
    mail_definitions_path: Path
    mail_schedules_path: Path
    artifact_root: Path
    archive_root: Path
    defaults: DefaultsConfig
    runtime: RuntimeConfig
    instances: tuple[BlueStacksInstanceConfig, ...]
    accounts: tuple[AccountConfig, ...]
    castle_rosters: tuple[PncAccountCastleRosterConfig, ...] = ()
    castle_targets: tuple[AccountCastleTargetsConfig, ...] = ()
    mail_schedule_catalog: MailScheduleCatalog | None = None

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

    def find_castle_targets(self, account_id: str) -> AccountCastleTargetsConfig | None:
        """Returns the authored castle-target aliases for one configured account when available."""

        for targets in self.castle_targets:
            if targets.account_id == account_id:
                return targets
        return None

    def require_mail_schedule_catalog(self) -> MailScheduleCatalog:
        """Returns the loaded scheduled-mail catalog or fails fast when the feature is not configured."""

        if self.mail_schedule_catalog is not None:
            return self.mail_schedule_catalog
        raise ConfigurationError(
            "Scheduled mail is not configured for this workspace. Add both config/mail_definitions.yaml and config/mail_schedules.yaml before invoking run_mail_schedules.",
            mail_definitions_path=str(self.mail_definitions_path),
            mail_schedules_path=str(self.mail_schedules_path),
        )
