"""Shared runtime observation-persistence modes."""

from __future__ import annotations

from enum import StrEnum


class ObservationMode(StrEnum):
    """Controls whether routine observations favor diagnostic evidence or low churn."""

    DEBUG = "debug"
    LIGHT = "light"
