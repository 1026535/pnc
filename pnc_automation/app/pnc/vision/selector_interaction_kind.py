"""Shared selector interaction kinds used by the catalog and runtime registry."""

from enum import StrEnum


class SelectorInteractionKind(StrEnum):
    """Describes whether a selector is navigational, actionable, non-interactive, or still unclassified."""

    UNKNOWN = "unknown"
    NAVIGATION = "navigation"
    ACTION = "action"
    LABEL = "label"
