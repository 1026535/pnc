"""Synthetic write_accounts_config fixture."""

from __future__ import annotations

from pathlib import Path
import textwrap



def _write_accounts_config(root: Path) -> Path:
    """Writes one minimal valid accounts config in the requested directory."""

    config_path = root / "accounts.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            instances:
              - id: bs-main
                display_name: serious_stuff
                app_package: com.global.tmslg
            accounts:
              - id: account_a
                instance_id: bs-main
                pnc_account_id: inline_user
                username: inline_user
                password: inline_pass
            """
        ).strip(),
        encoding="utf-8",
    )
    return config_path
