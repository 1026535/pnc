"""Effect classes shared by workflow and reviewed navigation boundaries."""

from __future__ import annotations

from enum import StrEnum


class WorkflowEffect(StrEnum):
    """Declares the bounded effect class permitted by the core runner."""

    READ_ONLY = "read_only"
    NONSPENDING_STATE_CHANGE = "nonspending_state_change"
    RESOURCE_CHANGING = "resource_changing"
