"""Command-line entry point for the automation platform."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Sequence

from pnc_automation.app.automation.engine.runner import StepRunResult
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.runtime.observation_mode import ObservationMode
from pnc_automation.app import build_application_runner
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.authoring.config.yaml_helpers import build_castle_identity
from pnc_automation.app.pnc.domain.building_priority_input import resolve_building_priority_values
from pnc_automation.app.pnc.domain.mail import parse_send_mail_params, route_requires_player_name
from pnc_automation.app.pnc.enums.mail import PlayerProfileRouteKind


def main(argv: Sequence[str] | None = None) -> int:
    """Parses CLI arguments, runs automation, and prints a summary."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] not in {
        "run", "login", "build", "construct", "open-building", "send-mail", "run-mail-schedules"
    }:
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

    construct_parser = subparsers.add_parser(
        "construct",
        help="Construct one exact building from its canonical empty-slot family.",
    )
    _add_common_arguments(construct_parser)
    _add_castle_arguments(construct_parser)
    _add_building_construction_arguments(construct_parser)

    open_building_parser = subparsers.add_parser(
        "open-building",
        help="Open one exact home-city building screen using the current session or an explicit castle target.",
    )
    _add_common_arguments(open_building_parser)
    _add_castle_arguments(open_building_parser)
    _add_open_building_arguments(open_building_parser)

    send_mail_parser = subparsers.add_parser(
        "send-mail",
        help="Run one direct canonical send_mail task from flat string CLI parameters.",
    )
    _add_common_arguments(send_mail_parser)
    _add_castle_arguments(send_mail_parser)
    _add_send_mail_arguments(send_mail_parser)

    run_mail_schedules_parser = subparsers.add_parser(
        "run-mail-schedules",
        help="Resolve and execute any authored mail schedules due for the current UTC hour.",
    )
    _add_common_arguments(run_mail_schedules_parser)
    _add_run_mail_schedules_arguments(run_mail_schedules_parser)

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
    if parsed.command == "construct":
        castle = _parse_optional_castle(parser, parsed)
        if castle is not None:
            application.prepare_account_session(account_id=parsed.account, castle=castle)
        step_result = application.run_task(
            account_id=parsed.account,
            task_id=TaskId.BUILDING_CONSTRUCT,
            params={"building": parsed.building},
        )
        print(_serialize_step_result(account_id=parsed.account, step_result=step_result))
        return 0
    if parsed.command == "send-mail":
        castle = _parse_optional_castle(parser, parsed)
        if castle is not None:
            application.prepare_account_session(account_id=parsed.account, castle=castle)
        step_result = application.run_task(
            account_id=parsed.account,
            task_id=TaskId.SEND_MAIL,
            params=_build_send_mail_cli_params(parser, parsed),
        )
        print(_serialize_step_result(account_id=parsed.account, step_result=step_result))
        return 0
    if parsed.command == "run-mail-schedules":
        result = application.run_mail_schedules(
            account_id=parsed.account,
            schedule_ids=parsed.schedule_id,
            scheduled_for_utc=_parse_optional_scheduled_for_utc(parser, parsed.scheduled_for_utc),
        )
        print(_serialize_run_result(result))
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


def _add_building_construction_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds the exact constructable building id used by the direct command."""

    parser.add_argument(
        "--building",
        required=True,
        help="Exact constructable building id, such as farm, institute, or alliance_hall.",
    )


def _add_send_mail_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds the flat string CLI arguments for direct canonical mail sending."""

    parser.add_argument(
        "--recipient-kind",
        required=True,
        choices=["alliance", "player"],
        help="Send to the alliance mailbox or one player recipient.",
    )
    parser.add_argument("--subject", required=True, help="Mail subject text.")
    parser.add_argument("--body", required=True, help="Mail body text.")
    recipient_group = parser.add_mutually_exclusive_group()
    recipient_group.add_argument("--player-name", help="Exact player name for direct typed targeting.")
    recipient_group.add_argument(
        "--profile-route-kind",
        choices=[kind.value for kind in PlayerProfileRouteKind],
        help="Supported route used to reach a remote player profile before composing.",
    )
    parser.add_argument(
        "--profile-route-player-name",
        help="Player name attached to the selected profile route when that route requires one.",
    )


def _add_run_mail_schedules_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds the direct scheduled-mail execution arguments."""

    parser.add_argument(
        "--schedule-id",
        action="append",
        default=None,
        help="Optional authored schedule id to include; may be repeated to preserve a specific schedule order.",
    )
    parser.add_argument(
        "--scheduled-for-utc",
        help="Optional ISO-8601 UTC timestamp used for deterministic replay or debugging.",
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


def _build_send_mail_cli_params(parser: argparse.ArgumentParser, parsed: argparse.Namespace) -> dict[str, object]:
    """Builds one canonical send_mail task payload from the flat direct CLI flags."""

    params: dict[str, object] = {
        "recipient_kind": parsed.recipient_kind,
        "subject": parsed.subject,
        "body": parsed.body,
    }
    if parsed.player_name is not None:
        params["player_name"] = parsed.player_name
    if parsed.profile_route_player_name is not None and parsed.profile_route_kind is None:
        parser.error("--profile-route-player-name requires --profile-route-kind.")
    if parsed.profile_route_kind is not None:
        route_kind = PlayerProfileRouteKind(parsed.profile_route_kind)
        profile_route: dict[str, object] = {"kind": route_kind.value}
        if parsed.profile_route_player_name is not None:
            profile_route["player_name"] = parsed.profile_route_player_name
        if route_requires_player_name(route_kind) and "player_name" not in profile_route:
            parser.error(f"--profile-route-kind {route_kind.value} requires --profile-route-player-name.")
        if not route_requires_player_name(route_kind) and "player_name" in profile_route:
            parser.error(f"--profile-route-kind {route_kind.value} does not accept --profile-route-player-name.")
        params["profile_route"] = profile_route
    try:
        parse_send_mail_params(task_label="cli send-mail", params=params)
    except Exception as error:
        parser.error(str(error))
        raise AssertionError("argparse.parser.error does not return")
    return params


def _parse_optional_scheduled_for_utc(parser: argparse.ArgumentParser, raw_value: str | None) -> datetime | None:
    """Parses one optional scheduled-mail replay timestamp from the CLI."""

    if raw_value is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        parser.error("--scheduled-for-utc must be an ISO-8601 UTC timestamp such as 2026-03-31T05:00:00Z.")
        raise AssertionError("argparse.parser.error does not return")
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        parser.error("--scheduled-for-utc must use UTC, for example 2026-03-31T05:00:00Z.")
        raise AssertionError("argparse.parser.error does not return")
    return parsed


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
