"""Synthetic write_mail_definitions fixture."""

from __future__ import annotations

from pathlib import Path
import textwrap



def _write_mail_definitions(root: Path) -> Path:
    """Writes one valid sample mail-definitions catalog."""

    definitions_path = root / "mail_definitions.yaml"
    definitions_path.write_text(
        textwrap.dedent(
            """
            mails:
              - id: alliance_reset
                castle_ref: main
                recipient_kind: alliance
                subject: Alliance Reset Reminder
                body: |
                  Reset is today.
                  Please donate.
              - id: player_followup
                recipient_kind: player
                player_name: SomePlayer
                subject: Follow-up
                body: |
                  Hi,
                  Checking in.
            """
        ).strip(),
        encoding="utf-8",
    )
    return definitions_path
