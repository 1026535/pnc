"""Inspect or execute one bounded Hero Hall free-single canary increment."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from _script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.daily_maintenance.canaries import (
    CanaryOutcome,
    CanaryReason,
    CanaryResult,
    CanaryRole,
    planned_canaries,
)
from pnc_automation.app.automation.daily_maintenance.canary_runtime import (
    persist_canary_result,
    verify_canary_identity,
)
from pnc_automation.app.automation.daily_maintenance.connected_hero_hall import ConnectedHeroHallSession
from pnc_automation.app.automation.daily_maintenance.coordinator import DailyMaintenanceCoordinator
from pnc_automation.app.automation.daily_maintenance.hero_hall import (
    HeroHallRecruitmentExecutor,
    HeroHallState,
)
from pnc_automation.app.automation.daily_maintenance.live_session import ConnectedDailyQuestSession
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import JournaledMutationDispatcher
from pnc_automation.app.authoring.config.daily_maintenance import load_daily_maintenance_config
from pnc_automation.app.authoring.config.loader import load_app_config
from pnc_automation.app.authoring.config.mutation_acknowledgement import parse_mutation_acknowledgement
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    MutationIntentState,
)
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore


def main() -> int:
    """Defaults to a read-only Hero Hall inspection; mutation needs exact authority."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/accounts.yaml")
    parser.add_argument("--daily-config", default="config/daily_maintenance.yaml")
    parser.add_argument("--role", required=True, choices=tuple(role.value for role in CanaryRole))
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--execute", action="store_true")
    mode_group.add_argument("--reconcile-only", action="store_true")
    parser.add_argument("--game-reset-id")
    acknowledgement_group = parser.add_mutually_exclusive_group()
    acknowledgement_group.add_argument("--acknowledgement")
    acknowledgement_group.add_argument("--acknowledgement-base64")
    arguments = parser.parse_args()

    role = CanaryRole(arguments.role)
    case = next(
        case for case in planned_canaries()
        if case.role == role and case.quest_id == DailyQuestId.HERO_HALL
    )
    config = load_app_config(Path(arguments.config))
    daily = load_daily_maintenance_config(Path(arguments.daily_config), app_config=config)
    matching = tuple(
        target for target in daily.canary_targets
        if (target.account_id, target.castle_ref) == (case.account_id, case.castle_ref)
    )
    if len(matching) != 1:
        parser.error("Requested castle is not uniquely configured as a canary.")
    target = matching[0]
    policy = target.capability(DailyQuestId.HERO_HALL)
    if policy is None or policy.max_mutations != 5 or policy.max_diamond_spend != 0:
        parser.error("Hero Hall canary requires exactly five mutations and zero diamonds.")

    now = datetime.now(UTC)
    local_date = now.astimezone(ZoneInfo("America/Toronto")).date()
    acknowledgement = arguments.acknowledgement
    if arguments.acknowledgement_base64 is not None:
        try:
            acknowledgement = base64.b64decode(arguments.acknowledgement_base64, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            parser.error(f"--acknowledgement-base64 must contain UTF-8 JSON: {error}")
    if arguments.reconcile_only and not arguments.game_reset_id:
        parser.error("--reconcile-only requires --game-reset-id.")
    if arguments.reconcile_only and acknowledgement is not None:
        parser.error("Do not supply mutation authority for --reconcile-only.")
    if arguments.execute:
        if acknowledgement is None:
            parser.error("--execute requires --acknowledgement.")
        parse_mutation_acknowledgement(acknowledgement).authorize(
            account_id=target.account_id,
            castle_ref=target.castle_ref,
            quest_id=DailyQuestId.HERO_HALL,
            maintenance_date=local_date,
            max_mutations=5,
            max_diamond_spend=0,
        )
    elif acknowledgement is not None:
        parser.error("Do not supply mutation authority for a read-only inspection.")

    store = DailyRunJournalStore(config.artifact_root)
    reset_id = arguments.game_reset_id or f"pnc-reset-{now.date().isoformat()}-00"
    checkpoint = None
    if arguments.reconcile_only:
        checkpoint = store.load(game_reset_id=reset_id, account_id=target.account_id, castle=target.castle)
        if checkpoint is None:
            parser.error("No existing journal was found for --reconcile-only.")
        if not any(
            intent.quest_id == DailyQuestId.HERO_HALL
            and intent.state != MutationIntentState.COMMITTED
            for intent in checkpoint.mutation_intents
        ):
            parser.error("The selected journal has no unresolved Hero Hall operation.")

    logging.disable(logging.CRITICAL)
    application = build_application_runner(arguments.config)
    bundle = application.script_runner.build_connected_runtime_bundle(
        account=config.require_account(target.account_id),
    )
    verified = verify_canary_identity(
        script_runner=application.script_runner,
        connected=bundle,
        target=target,
    )
    observer = bundle.runtime.observation_service
    actions = verified.action_executor
    if verified.observation.screen_type != ScreenType.PNC_HOME_CITY:
        home = bundle.runner.execute_flow_until(
            label_prefix="hero_hall_canary_home",
            planner=bundle.runner.flow_planner.ensure_home_city,
            done=lambda observation: observation.screen_type == ScreenType.PNC_HOME_CITY,
            start_observation=verified.observation,
            max_steps=8,
        )
    else:
        home = verified.observation
    daily_session = ConnectedDailyQuestSession(bundle.runner, observer, actions)
    daily_coordinator = DailyMaintenanceCoordinator.for_read_only(
        session=daily_session,
        journal_store=store,
        catalog=DailyQuestCatalog(),
    )
    hero_session = ConnectedHeroHallSession(
        runner=bundle.runner,
        observation_service=observer,
        action_executor=actions,
        flows=bundle.runner.flow_planner,
        daily_completion_probe=lambda: _daily_hero_hall_complete(daily_coordinator),
    )
    hero_session.open_hero_hall()
    state = HeroHallState.from_observation(hero_session.observe_hero_hall("hero_hall_canary_state"))
    if not arguments.execute and not arguments.reconcile_only:
        report = {
            "mode": "read_only",
            "account_id": target.account_id,
            "castle_ref": target.castle_ref,
            "castle": asdict(target.castle),
            "hero_hall_state": asdict(state),
            "live_canary_passed": False,
        }
        _write_report(config.artifact_root, target.account_id, report)
        daily_session.return_to_home()
        return 0

    checkpoint = checkpoint or store.load(
        game_reset_id=reset_id,
        account_id=target.account_id,
        castle=target.castle,
    ) or DailyTaskCheckpoint(
        maintenance_date=local_date.isoformat(),
        game_reset_id=reset_id,
        account_id=target.account_id,
        castle=target.castle,
    )
    if checkpoint.game_reset_id != reset_id:
        raise ValueError("Hero Hall journal reset identity conflicts; do not replay it.")
    checkpoint, outcome = HeroHallRecruitmentExecutor(
        session=hero_session,
        dispatcher=JournaledMutationDispatcher(store),
    ).execute(checkpoint=checkpoint)
    result_kind, reason = _classify_outcome(outcome.status)
    result = CanaryResult(
        quest_id=case.quest_id,
        role=role,
        revision=_hero_hall_revision(),
        outcome=result_kind,
        reason=reason,
        artifact_paths=outcome.artifact_paths,
    )
    evidence_path = persist_canary_result(artifact_root=config.artifact_root, result=result)
    report = {
        "mode": "reconcile_only" if arguments.reconcile_only else "execute_increment",
        "account_id": target.account_id,
        "castle_ref": target.castle_ref,
        "castle": asdict(target.castle),
        "game_reset_id": reset_id,
        "result": asdict(result),
        "outcome": asdict(outcome),
        "canary_evidence_path": str(evidence_path),
        "journal_path": str(store.checkpoint_path(
            game_reset_id=checkpoint.game_reset_id,
            account_id=target.account_id,
            castle=target.castle,
        )),
    }
    _write_report(config.artifact_root, target.account_id, report)
    daily_session.return_to_home()
    return 0 if result_kind in {CanaryOutcome.PASSED, CanaryOutcome.APPLICABILITY_SKIP} else 1


def _daily_hero_hall_complete(coordinator: DailyMaintenanceCoordinator) -> bool:
    """Proves the Hero Hall Daily row through the shared read-only coordinator."""

    survey = coordinator.survey_read_only()
    return any(
        row.quest_id == DailyQuestId.HERO_HALL
        and (
            row.state.value in {"claim", "completed"}
            or (
                row.progress_current is not None
                and row.progress_required is not None
                and row.progress_current >= 5
            )
        )
        for row in survey.rows
    )


def _classify_outcome(status: DailyTargetOutcomeStatus) -> tuple[CanaryOutcome, CanaryReason]:
    """Maps one feature outcome to the canary evidence vocabulary."""

    if status == DailyTargetOutcomeStatus.SUCCESS:
        return CanaryOutcome.PASSED, CanaryReason.NONE
    if status == DailyTargetOutcomeStatus.WAITING_COOLDOWN:
        return CanaryOutcome.BLOCKED, CanaryReason.UNPROVEN_POSTCONDITION
    return CanaryOutcome.BLOCKED, CanaryReason.UNPROVEN_POSTCONDITION


def _hero_hall_revision() -> str:
    """Fingerprints the Hero Hall implementation and shared observation/journal dependencies."""

    root = Path(__file__).resolve().parents[1]
    paths = (
        "pnc_automation/app/automation/daily_maintenance/hero_hall.py",
        "pnc_automation/app/automation/daily_maintenance/connected_hero_hall.py",
        "pnc_automation/app/automation/daily_maintenance/mutation_dispatcher.py",
        "pnc_automation/app/pnc/vision/pnc_observation_enricher.py",
        "pnc_automation/app/pnc/vision/data/selector_registry.yaml",
        "pnc_automation/app/pnc/persistence/daily_run_journal_store.py",
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode())
        digest.update((root / path).read_bytes())
    return digest.hexdigest()


def _write_report(root: Path, account_id: str, report: dict[str, object]) -> None:
    """Persists structured canary evidence through the artifact store."""

    artifact = ArtifactStore(root).persist_bytes(
        artifact_directory=account_id,
        label="hero_hall_canary",
        extension="json",
        payload=json.dumps(report, indent=2, default=str).encode("utf-8"),
    )
    print(json.dumps({"report_path": str(artifact.path), **report}, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
