"""Command-line entry point for the automation platform."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Sequence

from pnc_automation.automation.runner import StepRunResult
from pnc_automation.automation.task import TaskId
from pnc_automation.automation.observation_mode import ObservationMode
from pnc_automation.app import build_application_runner
from pnc_automation.config.models import CastleIdentity
from pnc_automation.config.yaml_helpers import build_castle_identity
from pnc_automation.pnc.building_priority_input import resolve_building_priority_values


def main(argv: Sequence[str] | None = None) -> int:
    """Parses CLI arguments, runs automation, and prints a summary."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] not in {"run", "login", "build", "open-building"}:
        arguments.insert(0, "run")

    parser = argparse.ArgumentParser(description="Run Puzzles & Conquest automation.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute one automation script.")
    _add_common_arguments(run_parser)
    run_parser.add_argument("--script", required=True, help="Path to the run script YAML file.")

    login_parser = subparsers.add_parser("login", help="Prepare one account session and optionally align a castle.")
    _add_common_arguments(login_parser)
    _add_castle_arguments(login_parser)

    build_parser = subparsers.add_parser(
        "build",
        help="Run one direct building-upgrade step using the current session or an explicit castle target.",
    )
    _add_common_arguments(build_parser)
    _add_castle_arguments(build_parser)
    _add_building_upgrade_arguments(build_parser)

    open_building_parser = subparsers.add_parser(
        "open-building",
        help="Open one exact home-city building screen using the current session or an explicit castle target.",
    )
    _add_common_arguments(open_building_parser)
    _add_castle_arguments(open_building_parser)
    _add_open_building_arguments(open_building_parser)

    parsed = parser.parse_args(arguments)
    application = build_application_runner(
        Path(parsed.config),
        verbose=parsed.verbose,
        observation_mode=None if parsed.observation_mode is None else ObservationMode(parsed.observation_mode),
    )
    if parsed.command == "run":
        result = application.run(account_id=parsed.account, script_path=parsed.script)
        print(_serialize_run_result(result))
        return 0
    if parsed.command == "login":
        result = application.prepare_account_session(
            account_id=parsed.account,
            castle=_parse_optional_castle(parser, parsed),
        )
        print(_serialize_run_result(result))
        return 0
    if parsed.command == "open-building":
        castle = _parse_optional_castle(parser, parsed)
        if castle is not None:
            application.prepare_account_session(account_id=parsed.account, castle=castle)
        step_result = application.run_task(
            account_id=parsed.account,
            task_id=TaskId.OPEN_BUILDING,
            params={"building": parsed.building},
        )
        print(_serialize_step_result(account_id=parsed.account, step_result=step_result))
        return 0
    castle = _parse_optional_castle(parser, parsed)
    if castle is not None:
        application.prepare_account_session(account_id=parsed.account, castle=castle)
    priority = resolve_building_priority_values(priority=parsed.priority, priority_file=parsed.priority_file)
    step_result = application.run_task(
        account_id=parsed.account,
        task_id=TaskId.BUILDING_UPGRADE,
        params={
            "priority": priority,
            "allow_speedups": parsed.allow_speedups,
        },
    )
    print(_serialize_step_result(account_id=parsed.account, step_result=step_result))
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


def _add_building_upgrade_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds the direct building-upgrade input flags shared by CLI task entry points."""

    priority_group = parser.add_mutually_exclusive_group()
    priority_group.add_argument(
        "--priority",
        nargs="+",
        help="Ordered building ids to try, such as institute warehouse.",
    )
    priority_group.add_argument(
        "--priority-file",
        help="Path to one newline-delimited building-priority file.",
    )
    parser.add_argument(
        "--allow-speedups",
        action="store_true",
        help="Allow the building-upgrade task to use supported speedups.",
    )


def _add_open_building_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds the exact requested building id used by the direct open-building entry point."""

    parser.add_argument(
        "--building",
        required=True,
        help="Exact home-city building id to open, such as infantry_barracks or sanctum.",
    )


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


def _serialize_step_result(*, account_id: str, step_result: StepRunResult) -> str:
    """Serializes one direct task result using a stable task-oriented CLI JSON shape."""

    return json.dumps(
        {
            "account_id": account_id,
            "task_id": step_result.task_id.value,
            "status": step_result.status.value,
            "attempts": step_result.attempts,
            "message": step_result.message,
            "requested_castle": None if step_result.requested_castle is None else asdict(step_result.requested_castle),
        },
        default=str,
    )


if __name__ == "__main__":
    raise SystemExit(main())
