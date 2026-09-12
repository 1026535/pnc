"""Shared YAML parsing helpers for typed runtime configuration models."""

from __future__ import annotations

import re
from typing import Any

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.config.yaml_helpers import (
    ErrorBuilder,
    require_int,
    require_list,
    require_mapping,
    require_string,
)

_KINGDOM_ID_PATTERN = re.compile(r"^K\d{1,4}$")


__all__ = [
    "ErrorBuilder",
    "build_castle_identity",
    "load_castle_identity",
    "require_int",
    "require_kingdom_identifier",
    "require_list",
    "require_mapping",
    "require_string",
]


def require_kingdom_identifier(
    value: Any,
    *,
    context: str,
    error_builder: ErrorBuilder = ConfigurationError,
) -> str:
    """Returns one canonical authored kingdom identifier in `K###` form."""

    kingdom = require_string(value, context=context, error_builder=error_builder)
    if not _KINGDOM_ID_PATTERN.fullmatch(kingdom):
        raise error_builder(
            f"Expected {context} to use canonical kingdom form like 'K230'.",
            context=context,
            value=kingdom,
        )
    return kingdom


def build_castle_identity(
    *,
    kingdom: Any,
    castle_name: Any,
    castle_level: Any = None,
    context: str,
    error_builder: ErrorBuilder = ConfigurationError,
) -> CastleIdentity:
    """Builds one authored castle identity from individually validated fields."""

    return CastleIdentity(
        kingdom=require_kingdom_identifier(
            kingdom,
            context=f"{context}.kingdom",
            error_builder=error_builder,
        ),
        castle_name=require_string(
            castle_name,
            context=f"{context}.castle_name",
            error_builder=error_builder,
        ),
        castle_level=(
            None
            if castle_level is None
            else require_int(
                castle_level,
                context=f"{context}.castle_level",
                error_builder=error_builder,
            )
        ),
    )


def load_castle_identity(
    value: Any,
    *,
    context: str,
    error_builder: ErrorBuilder = ConfigurationError,
) -> CastleIdentity:
    """Loads one castle mapping into the canonical shared castle identity model."""

    raw = require_mapping(value, context=context, error_builder=error_builder)
    return build_castle_identity(
        kingdom=raw.get("kingdom"),
        castle_name=raw.get("castle_name"),
        castle_level=raw.get("castle_level"),
        context=context,
        error_builder=error_builder,
    )
