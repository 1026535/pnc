"""Per-step task context shared with concrete task implementations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pnc_automation.capture.mail_archive_store import MailArchiveStore
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.models import AccountConfig, CastleIdentity, DefaultsConfig, PncAccountCastleRosterConfig
from pnc_automation.errors import TaskVerificationError
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner


@dataclass(frozen=True, slots=True)
class TaskContext:
    """Bundles stable runtime dependencies for one task execution."""

    account: AccountConfig
    castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None]
    defaults: DefaultsConfig
    step: object
    params: Any
    flows: ScreenFlowPlanner
    logger: logging.LoggerAdapter
    target_castle: CastleIdentity | None = None
    castle_roster_store: CastleRosterStore | None = None
    mail_archive_store: MailArchiveStore | None = None
    runtime_state: dict[str, Any] = field(default_factory=dict)

    @property
    def castle_roster(self) -> PncAccountCastleRosterConfig | None:
        """Returns the freshest cached castle roster for the configured account when available."""

        return self.castle_roster_provider()

    def require_target_castle(self) -> CastleIdentity:
        """Returns the explicit step-level castle target or fails fast when none was provided."""

        if self.target_castle is not None:
            return self.target_castle
        raise TaskVerificationError(
            f"Task '{getattr(self.step, 'task', '<unknown>')}' requires an explicit castle target.",
            account_id=self.account.id,
            task_id=getattr(self.step, "task", None),
        )

    def require_castle_roster_store(self) -> CastleRosterStore:
        """Returns the writable castle-roster store or fails fast when it is unavailable."""

        if self.castle_roster_store is not None:
            return self.castle_roster_store
        raise TaskVerificationError(
            "This task requires a writable castle roster store.",
            account_id=self.account.id,
            task_id=getattr(self.step, "task", None),
        )

    def require_mail_archive_store(self) -> MailArchiveStore:
        """Returns the writable mail-archive store or fails fast when it is unavailable."""

        if self.mail_archive_store is not None:
            return self.mail_archive_store
        raise TaskVerificationError(
            "This task requires a writable mail archive store.",
            account_id=self.account.id,
            task_id=getattr(self.step, "task", None),
        )
