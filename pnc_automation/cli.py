"""Command-line entry point for the automation platform."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from pnc_automation.app import build_application_runner


def main() -> int:
    """Parses CLI arguments, runs automation, and prints a summary."""

    parser = argparse.ArgumentParser(description="Run Puzzles & Conquest automation.")
    parser.add_argument("--config", default="config/accounts.yaml", help="Path to the account configuration file.")
    parser.add_argument("--account", required=True, help="Configured account id to run.")
    parser.add_argument("--script", required=True, help="Path to the run script YAML file.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose structured logging.")
    arguments = parser.parse_args()

    application = build_application_runner(Path(arguments.config), verbose=arguments.verbose)
    result = application.run(account_id=arguments.account, script_path=arguments.script)
    print(
        json.dumps(
            {
                "account_id": result.account_id,
                "script_name": result.script_name,
                "steps": [asdict(step) for step in result.steps],
                "started_at": result.started_at.isoformat(),
                "finished_at": result.finished_at.isoformat(),
            },
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
