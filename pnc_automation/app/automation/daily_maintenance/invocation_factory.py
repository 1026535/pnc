"""Shared invocation/date/reset identity for Daily maintenance and Workshop runs.

One canonical factory supplies the local maintenance date and the
midnight-UTC game-reset identity every authorized invocation shares. The
Workshop invocation id generated here is created once after scope validation
and unresolved-intent lookup, persisted before mutation, and reused by every
connected adapter; it is never a user-entered completion flag.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceConfig
from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


def build_daily_run_boundary(
    daily_config: DailyMaintenanceConfig,
    *,
    now: datetime | None = None,
) -> DailyRunBoundary:
    """Return the shared local-date and midnight-UTC reset boundary for one invocation."""

    if now is None:
        now = datetime.now(ZoneInfo(daily_config.maintenance_timezone))
    maintenance_date = now.date()
    reset_date = now.astimezone(ZoneInfo("UTC")).date()
    return DailyRunBoundary(
        maintenance_date=maintenance_date,
        game_reset_id=f"pnc-reset-{reset_date.isoformat()}-{daily_config.game_reset_hour_utc:02d}",
    )


def generate_workshop_invocation_id(
    *,
    account_id: str,
    castle: CastleIdentity,
    game_reset_id: str,
) -> str:
    """Generate one unique durable identity for an authorized Workshop run.

    A resumed operation retains its invocation; a new healthy invocation gets a
    fresh id even on the same day, so operation identity never depends on frame
    fingerprints or maintenance dates.
    """

    return sanitize_artifact_segment(
        f"pet-workshop-run-{game_reset_id}-{account_id}-"
        f"{castle.kingdom}_{castle.castle_name}-{uuid4().hex[:12]}"
    )
