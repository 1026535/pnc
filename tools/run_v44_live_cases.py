"""Runs or inspects released V44 Home-city live-validation cases.

Subcommands:

- ``run`` — executes the selected frozen cases of one released assignment.
- ``validate`` — offline-checks a saved v3 result against its assignment.
- ``inspect-v2`` — describes a historical v2 evidence file without trusting it.
- ``example-assignment`` — writes an assignment template with blanks to fill.

Usage (PowerShell)::

    py tools/run_v44_live_cases.py example-assignment --output .local-data/v44/assignment.json
    py tools/run_v44_live_cases.py run --assignment .local-data/v44/assignment.json ^
        --annotation-dir .local-data/v44/annotation
    py tools/run_v44_live_cases.py validate --assignment .local-data/v44/assignment.json ^
        --result .local-data/v44/<run_id>/live_evidence.json
    py tools/run_v44_live_cases.py inspect-v2 --result .local-data/live030/evidence.json

Only the released assignment authorizes a run; this script connects only after
preflight proves the bound candidate, clean tree, entry hash, target, and
reservation state.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from tools._script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from tools.live_validation.annotation import AnnotationExchange
from tools.live_validation.binding import (
    AssignmentBinding,
    AssignmentBindingError,
    load_assignment_binding,
)
from tools.live_validation.cases import CASE_REGISTRY
from tools.live_validation.runner import (
    LiveCaseRunner,
    LiveConnection,
    PreflightRefusal,
    RunnerDeps,
    git_source_probe,
)
from tools.live_validation.v2 import inspect_report, inspect_v2_evidence
from tools.live_validation.validate import validate_live_evidence


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Released V44 live-validation case runner and offline inspector."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Execute the selected cases of one assignment.")
    run.add_argument("--assignment", type=Path, required=True, help="Released assignment JSON.")
    run.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Authoring config path; defaults to the assignment's config_path or config/accounts.yaml.",
    )
    run.add_argument(
        "--annotation-dir",
        type=Path,
        default=None,
        help="Directory for the tester-annotation exchange; required for control cases.",
    )
    run.add_argument(
        "--annotation-timeout",
        type=float,
        default=300.0,
        help="Seconds to await one annotation response before blocking the case.",
    )

    validate = subparsers.add_parser("validate", help="Offline-validate one saved result.")
    validate.add_argument("--assignment", type=Path, required=True)
    validate.add_argument("--result", type=Path, required=True)
    validate.add_argument(
        "--no-files", action="store_true", help="Skip on-disk artifact hashing."
    )

    inspect = subparsers.add_parser(
        "inspect-v2", help="Describe a historical v2 evidence file."
    )
    inspect.add_argument("--result", type=Path, required=True)

    example = subparsers.add_parser(
        "example-assignment", help="Write an assignment JSON template."
    )
    example.add_argument("--output", type=Path, required=True)
    return parser


def _real_connection(
    *, binding: AssignmentBinding, run_dir: Path, observer, config_path: Path
) -> LiveConnection:
    """Reserves the account and connects through the canonical runner path."""

    from pnc_automation.app.entrypoints.app import build_application_runner
    from pnc_automation.app.automation.engine.core_runtime import build_core_runtime
    from pnc_automation.core.config.host import LiveAutomationRole
    from pnc_automation.core.infra.emulator.session import (
        BlueStacksSessionCleanupPolicy,
    )

    runner = build_application_runner(config_path)
    script_runner = runner.script_runner
    try:
        account = script_runner.config.require_account(binding.target_account_id)
    except Exception as error:
        raise PreflightRefusal((str(error),)) from error
    if account.instance_id != binding.target_instance_id:
        raise PreflightRefusal((
            f"account '{account.id}' resolves instance '{account.instance_id}', "
            f"not the bound '{binding.target_instance_id}'.",
        ))
    try:
        account.require_live_role(LiveAutomationRole.LIVE_TESTING)
    except Exception as error:
        raise PreflightRefusal((str(error),)) from error

    instance = script_runner.config.require_instance(account.instance_id)
    statuses = script_runner.instance_lease_registry.reservation_status(
        (instance.display_name,)
    )
    status = statuses[0]
    if status.reservation_state == "active":
        raise PreflightRefusal((
            f"instance '{instance.display_name}' holds an active reservation; defer to it.",
        ))

    bundle = script_runner.reserve_accounts((account.id,))
    try:
        core = build_core_runtime(
            script_runner,
            account,
            artifact_directory=f"v44_live_{binding.run_id}",
            required_role=LiveAutomationRole.LIVE_TESTING,
            session_cleanup_policy=BlueStacksSessionCleanupPolicy.keep_warm(),
            input_dispatch_observer=observer,
        )
    except Exception:
        bundle.close()
        raise
    return LiveConnection(bundle=bundle, core=core, account=account)


def _command_run(args: argparse.Namespace) -> int:
    binding = load_assignment_binding(args.assignment)
    config_path = args.config or binding.config_path
    if config_path is None:
        raise PreflightRefusal((
            "no config path: pass --config or set config_path in the assignment.",
        ))
    annotation_factory = (
        None
        if args.annotation_dir is None
        else lambda directory: AnnotationExchange(
            args.annotation_dir, timeout_seconds=args.annotation_timeout
        )
    )
    deps = RunnerDeps(
        probe_source=git_source_probe,
        connect=lambda *, binding, run_dir, observer: _real_connection(
            binding=binding, run_dir=run_dir, observer=observer, config_path=config_path
        ),
        annotation_factory=annotation_factory,
    )
    evidence, path = LiveCaseRunner(binding, deps).run()
    counts = {result.case_id: result.status.value for result in evidence.case_results}
    print(json.dumps({"result": str(path), "cases": counts}, indent=2, sort_keys=True))
    return 0


def _command_validate(args: argparse.Namespace) -> int:
    binding = load_assignment_binding(args.assignment)
    report = validate_live_evidence(
        binding, args.result, verify_files=not args.no_files
    )
    print(
        json.dumps(
            {
                "valid": report.valid,
                "findings": [
                    {"check": finding.check, "detail": finding.detail}
                    for finding in report.findings
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.valid else 1


def _command_inspect_v2(args: argparse.Namespace) -> int:
    print(json.dumps(inspect_report(inspect_v2_evidence(args.result)), indent=2, sort_keys=True))
    return 0


def _command_example_assignment(args: argparse.Namespace) -> int:
    example = {
        "schema_version": 3,
        "assignment_id": "v44-pilot-000",
        "run_id": "v44-pilot-000-run1",
        "candidate_sha": "<40-hex clean candidate sha>",
        "source_root": "<absolute worktree path>",
        "import_root": "<absolute worktree path>",
        "report_root": "<absolute .local-data report dir>",
        "entry_point": "<absolute path to this tool>",
        "entry_sha256": "<sha256 of the entry file>",
        "target_account_id": "<config account id>",
        "target_castle_ref": "<kingdom>:<castle_name>",
        "target_instance_id": "<config instance id>",
        "target_role": "live_testing",
        "selected_cases": [
            {"case_id": case_id, "params": {}}
            for case_id in CASE_REGISTRY
        ],
        "resource_allowance_ref": None,
        "reservation_disposition": "released",
        "expected_cleanup": {
            "session_closed": True,
            "lease_released": True,
            "observer_restored": True,
            "instance_preserved": True,
        },
        "offline_evidence": [],
        "config_path": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(example, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "run":
            return _command_run(args)
        if args.command == "validate":
            return _command_validate(args)
        if args.command == "inspect-v2":
            return _command_inspect_v2(args)
        return _command_example_assignment(args)
    except AssignmentBindingError as error:
        print(f"assignment refused: {error}", file=sys.stderr)
        return 2
    except PreflightRefusal as error:
        print(f"preflight refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
