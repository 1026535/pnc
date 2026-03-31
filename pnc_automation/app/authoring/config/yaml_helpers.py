"""Shared YAML parsing helpers for typed runtime configuration models."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Protocol

from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.core.errors import ConfigurationError

_KINGDOM_ID_PATTERN = re.compile(r"^K\d{1,4}$")


class ErrorBuilder(Protocol):
    """Builds one fail-fast typed exception for invalid authored content."""

    def __call__(self, message: str, **details: Any) -> Exception:
        """Returns one exception instance carrying structured validation details."""


def require_mapping(
    value: Any,
    *,
    context: str,
    error_builder: ErrorBuilder = ConfigurationError,
) -> Mapping[str, Any]:
    """Returns one authored mapping or raises the provided validation error."""

    if not isinstance(value, Mapping):
        raise error_builder(f"Expected {context} to be a mapping.", context=context)
    return value


def require_list(
    value: Any,
    *,
    context: str,
    error_builder: ErrorBuilder = ConfigurationError,
) -> list[Any]:
    """Returns one authored list or raises the provided validation error."""

    if not isinstance(value, list):
        raise error_builder(f"Expected {context} to be a list.", context=context)
    return value


def require_string(
    value: Any,
    *,
    context: str,
    error_builder: ErrorBuilder = ConfigurationError,
) -> str:
    """Returns one non-empty authored string or raises the provided validation error."""

    if not isinstance(value, str) or value.strip() == "":
        raise error_builder(f"Expected {context} to be a non-empty string.", context=context)
    return value


def require_int(
    value: Any,
    *,
    context: str,
    error_builder: ErrorBuilder = ConfigurationError,
) -> int:
    """Returns one authored integer or raises the provided validation error."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise error_builder(f"Expected {context} to be an integer.", context=context)
    return value


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
