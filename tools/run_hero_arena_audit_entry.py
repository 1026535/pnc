"""Runs one guarded daily Hero Arena gate audit and persists a JSON summary."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.audits.hero_arena_audit import (
    HeroArenaEntryAuditor,
    find_existing_hero_arena_audit_summary,
    hero_arena_audit_label,
)
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore


def main() -> None:
    """Runs one calendar-day audit only after exact account and castle preparation succeeds."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(root / "config" / "accounts.yaml"), help="Runtime config path.")
    parser.add_argument("--account", default="mega_old_acc", help="Configured BlueStacks account id.")
    parser.add_argument("--kingdom", default="K157", help="Exact target castle kingdom.")
    parser.add_argument("--castle-name", default="NPC 2", help="Exact target castle name.")
    parser.add_argument("--castle-level", type=int, default=22, help="Expected target castle level.")
    parser.add_argument("--timezone", default="America/Toronto", help="Calendar timezone for duplicate-entry protection.")
    arguments = parser.parse_args()

    application = build_application_runner(Path(arguments.config), verbose=True)
    artifact_root = application.script_runner.config.artifact_root
    local_date = datetime.now(ZoneInfo(arguments.timezone)).date()
    target = CastleIdentity(
        kingdom=arguments.kingdom,
        castle_name=arguments.castle_name,
        castle_level=arguments.castle_level,
    )
    label = hero_arena_audit_label(local_date)
    duplicate = find_existing_hero_arena_audit_summary(
        artifact_root,
        local_date=local_date,
        account_id=arguments.account,
        castle=target,
    )
    if duplicate is not None:
        raise RuntimeError(f"A Hero Arena audit entry already exists for {local_date.isoformat()}: {duplicate}")

    preparation = application.prepare_account_session(account_id=arguments.account, castle=target)
    successful_preparation_statuses = {TaskStatus.SUCCESS, TaskStatus.SKIPPED}
    if not preparation.steps or any(step.status not in successful_preparation_statuses for step in preparation.steps):
        raise RuntimeError(f"Exact account/castle preparation failed: {preparation.steps}")
    open_arena = application.run_task(
        account_id=arguments.account,
        task_id=TaskId.OPEN_BUILDING,
        params={"building": "arena"},
    )
    if open_arena.status != TaskStatus.SUCCESS:
        raise RuntimeError(f"Versus Center navigation failed: {open_arena}")

    account = application.script_runner.config.require_account(arguments.account)
    runtime = application.script_runner.build_connected_runtime(account=account)
    auditor = HeroArenaEntryAuditor(
        observation_service=runtime.observation_service,
        action_executor=runtime.require_observed_action_executor(
            "Hero Arena audit requires the canonical selector-backed executor."
        ),
    )
    result = auditor.run(label_prefix=label)
    document = {
        "local_date": local_date.isoformat(),
        "timezone": arguments.timezone,
        "account_id": arguments.account,
        "castle": {
            "kingdom": target.kingdom,
            "castle_name": target.castle_name,
            "castle_level": target.castle_level,
        },
        "elemental_intro_appeared": result.elemental_intro_appeared,
        "hero_formation_gate_appeared": result.hero_formation_gate_appeared,
        "destination_screen": result.destination_screen.value,
        "final_screen": result.final_screen.value,
        "evidence_artifact_paths": [str(path) for path in result.evidence_artifact_paths],
        "safety": {
            "saved_formation": False,
            "started_challenge": False,
            "used_paid_attempt": False,
        },
    }
    summary = ArtifactStore(root=artifact_root).persist_bytes(
        artifact_directory=runtime.observation_service.artifact_directory,
        label=label,
        extension="json",
        payload=(json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    print(summary.path)


if __name__ == "__main__":
    main()
