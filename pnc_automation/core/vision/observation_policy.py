"""PNC-neutral observation detail policy shared by capture consumers."""

from __future__ import annotations

from enum import StrEnum


class ObservationMode(StrEnum):
    """Controls how much observation detail the runtime captures per step."""

    DEBUG = "debug"
    LIGHT = "light"
