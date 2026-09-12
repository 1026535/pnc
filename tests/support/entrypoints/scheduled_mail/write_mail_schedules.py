"""Synthetic write_mail_schedules fixture."""

from __future__ import annotations

from pathlib import Path
import textwrap



def _write_mail_schedules(root: Path) -> Path:
    """Writes one valid sample mail-schedules catalog."""

    schedules_path = root / "mail_schedules.yaml"
    schedules_path.write_text(
        textwrap.dedent(
            """
            rotation:
              cycle_days: 14
              start_utc: 2026-03-30T00:00:00Z
            mail_schedules:
              - id: mailschedule_1
                enabled: true
                day_indices: [0, 7]
                hour_utc: 5
                mail_ids:
                  - alliance_reset
                  - player_followup
              - id: mailschedule_2
                enabled: true
                day_indices: [7]
                hour_utc: 5
                mail_ids:
                  - player_followup
                  - alliance_reset
            """
        ).strip(),
        encoding="utf-8",
    )
    return schedules_path
