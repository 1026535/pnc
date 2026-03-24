"""Typed configuration loading and validation."""

from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.loader import load_app_config
from pnc_automation.config.models import (
    AccountConfig,
    AccountCastleTargetsConfig,
    AppConfig,
    BlueStacksInstanceConfig,
    CastleIdentity,
    CastleTargetDefinition,
    CredentialSource,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
)

__all__ = [
    "AccountConfig",
    "AccountCastleTargetsConfig",
    "AppConfig",
    "BlueStacksInstanceConfig",
    "CastleIdentity",
    "CastleRosterStore",
    "CastleTargetDefinition",
    "CredentialSource",
    "DefaultsConfig",
    "PncAccountCastleRosterConfig",
    "ResolvedCredentials",
    "load_app_config",
]
