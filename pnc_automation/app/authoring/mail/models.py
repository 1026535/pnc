"""Typed authored scheduled-mail models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pnc_automation.app.pnc.domain.mail import SendMailParams


@dataclass(frozen=True, slots=True)
class AuthoredMailDefinition:
    """Defines one reusable authored mail payload keyed by id."""

    id: str
    castle_ref: str | None
    params: SendMailParams


@dataclass(frozen=True, slots=True)
class AuthoredMailSchedule:
    """Defines one reusable authored schedule that references ordered mail ids."""

    id: str
    enabled: bool
    day_indices: tuple[int, ...]
    hour_utc: int
    mail_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MailScheduleCatalog:
    """Bundles the validated authored mail definitions and schedules for one workspace."""

    start_utc: datetime
    definitions: tuple[AuthoredMailDefinition, ...]
    schedules: tuple[AuthoredMailSchedule, ...]
