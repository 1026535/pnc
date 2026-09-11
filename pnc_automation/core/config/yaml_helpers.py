"""Generic YAML shape validators shared by application and host config loaders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pnc_automation.core.errors import ConfigurationError


class ErrorBuilder(Protocol):
    """Builds one typed configuration error without exposing raw input."""

    def __call__(self, message: str, **details: Any) -> Exception:
        """Returns one exception instance carrying safe structured details."""


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
