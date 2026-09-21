"""Shared match-3 battle component contract and its M0 unavailable implementation."""

from pnc_automation.app.automation.match3.component import (
    Match3Component,
    Match3Session,
    Match3UnavailableError,
    UnavailableMatch3Component,
    require_match3_available,
)

__all__ = [
    "Match3Component",
    "Match3Session",
    "Match3UnavailableError",
    "UnavailableMatch3Component",
    "require_match3_available",
]
