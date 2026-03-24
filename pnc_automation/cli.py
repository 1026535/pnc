"""Command-line entry point for the automation platform."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Sequence

from pnc_automation.automation.observation_mode import ObservationMode
from pnc_automation.app import build_application_runner
from pnc_automation.config.models import CastleIdentity
from pnc_automation.config.yaml_helpers import build_castle_identity


def main(argv: Sequence[str] | None = None) -> int:
    """Parses CLI arguments, runs automation, and prints a summary."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] not in {"run", "login"}:
        arguments.insert(0, "run")

    parser = argparse.ArgumentParser(description="Run Puzzles & Conquest automation.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute one automation script.")
    _add_common_arguments(run_parser)
    run_parser.add_argument("--script", required=True, help="Path to the run script YAML file.")

    login_parser = subparsers.add_parser("login", help="Prepare one account session and optionally align a castle.")
    _add_common_arguments(login_parser)
    _add_castle_arguments(login_parser)

    parsed = parser.parse_args(arguments)
    application = build_application_runner(
        Path(parsed.config),
        verbose=parsed.verbose,
        observation_mode=None if parsed.observation_mode is None else ObservationMode(parsed.observation_mode),
    )
    if parsed.command == "run":
        result = application.run(account_id=parsed.account, script_path=parsed.script)
    else:
        result = application.prepare_account_session(
            account_id=parsed.account,
            castle=_parse_optional_castle(parser, parsed),
        )
    print(_serialize_run_result(result))
    return 0


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds config, account, and logging flags shared by all commands."""

    parser.add_argument("--config", default="config/accounts.yaml", help="Path to the account configuration file.")
    parser.add_argument("--account", required=True, help="Configured account id to run.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose structured logging.")
    parser.add_argument(
        "--observation-mode",
        choices=[mode.value for mode in ObservationMode],
        help="Override the configured runtime observation mode for this one invocation.",
    )


def _add_castle_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds the optional explicit castle-target flags used by session preparation."""

    parser.add_argument("--kingdom", help="Canonical kingdom identifier such as K230.")
    parser.add_argument("--castle-name", help="Exact castle name to align before exiting.")
    parser.add_argument("--castle-level", type=int, help="Optional expected castle level.")


def _parse_optional_castle(parser: argparse.ArgumentParser, parsed: argparse.Namespace) -> CastleIdentity | None:
    """Builds one optional CLI castle target or reports invalid flag combinations."""

    if parsed.kingdom is None and parsed.castle_name is None and parsed.castle_level is None:
        return None
    if parsed.kingdom is None or parsed.castle_name is None:
        parser.error("Explicit castle targeting requires both --kingdom and --castle-name.")
    try:
        return build_castle_identity(
            kingdom=parsed.kingdom,
            castle_name=parsed.castle_name,
            castle_level=parsed.castle_level,
            context="cli castle",
        )
    except Exception as error:
        parser.error(str(error))
        raise AssertionError("argparse.parser.error does not return")


def _serialize_run_result(result: object) -> str:
    """Serializes one run summary using the same JSON shape across CLI commands."""

    return json.dumps(
        {
            "account_id": result.account_id,
            "script_name": result.script_name,
            "steps": [asdict(step) for step in result.steps],
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
        },
        default=str,
    )


if __name__ == "__main__":
    raise SystemExit(main())
