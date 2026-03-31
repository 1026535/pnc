"""Application-wide observation policy modes."""

from __future__ import annotations

from enum import StrEnum


class ObservationMode(StrEnum):
    """Controls how much observation detail the runtime captures per step."""

    DEBUG = "debug"
    LIGHT = "light"

