"""Typed configuration loading and validation."""

from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.loader import load_app_config
from pnc_automation.config.models import (
    AccountConfig,
    AppConfig,
    BlueStacksInstanceConfig,
    CastleIdentity,
    CredentialSource,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
)

__all__ = [
    "AccountConfig",
    "AppConfig",
    "BlueStacksInstanceConfig",
    "CastleIdentity",
    "CastleRosterStore",
    "CredentialSource",
    "DefaultsConfig",
    "PncAccountCastleRosterConfig",
    "ResolvedCredentials",
    "load_app_config",
]
