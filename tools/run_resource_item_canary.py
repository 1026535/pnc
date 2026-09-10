"""Inspect or execute the bounded resource-item canary on one configured canary castle."""

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
    CanaryOutcome, CanaryReason, CanaryResult, CanaryRole, planned_canaries,
)
from pnc_automation.app.automation.daily_maintenance.canary_runtime import (
    persist_canary_result,
    verify_canary_identity,
)
from pnc_automation.app.automation.daily_maintenance.connected_resource_item import ConnectedResourceItemSession
from pnc_automation.app.automation.daily_maintenance.coordinator import DailyMaintenanceCoordinator
from pnc_automation.app.automation.daily_maintenance.live_session import ConnectedDailyQuestSession
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import JournaledMutationDispatcher
from pnc_automation.app.automation.daily_maintenance.resource_item import ResourceItemExecutor
from pnc_automation.app.authoring.config.daily_maintenance import load_daily_maintenance_config
from pnc_automation.app.authoring.config.loader import load_app_config
from pnc_automation.app.authoring.config.mutation_acknowledgement import parse_mutation_acknowledgement
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId, DailyTargetOutcomeStatus, DailyTaskCheckpoint, MutationIntentState,
)
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.app.pnc.domain.resource_items import smallest_resource_item
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore


def main() -> int:
    """Defaults to read-only inspection; execution requires exact one-item authority."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/accounts.yaml")
    parser.add_argument("--daily-config", default="config/daily_maintenance.yaml")
    parser.add_argument("--role", required=True, choices=tuple(role.value for role in CanaryRole))
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--execute", action="store_true")
    mode_group.add_argument(
        "--reconcile-only", action="store_true",
        help="reconcile an existing unresolved journal without permitting a new use action",
    )
    parser.add_argument(
        "--game-reset-id",
        help="existing reset journal to reconcile; required with --reconcile-only",
    )
    acknowledgement_group = parser.add_mutually_exclusive_group()
    acknowledgement_group.add_argument("--acknowledgement")
    acknowledgement_group.add_argument(
        "--acknowledgement-base64",
        help="Base64-encoded acknowledgement JSON for shells that rewrite JSON arguments.",
    )
    arguments = parser.parse_args()
    role = CanaryRole(arguments.role)
    case = next(
        case for case in planned_canaries()
        if case.role == role and case.quest_id == DailyQuestId.USE_RESOURCE_ITEM
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
    policy = target.capability(DailyQuestId.USE_RESOURCE_ITEM)
    if policy is None or policy.max_mutations != 1 or policy.max_diamond_spend != 0:
        parser.error("Resource canary requires the configured one-item, zero-diamond policy.")
    now = datetime.now(UTC)
    local_date = now.astimezone(ZoneInfo("America/Toronto")).date()
    acknowledgement = arguments.acknowledgement
    if arguments.acknowledgement_base64 is not None:
        try:
            acknowledgement = base64.b64decode(
                arguments.acknowledgement_base64,
                validate=True,
            ).decode("utf-8")
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
            account_id=target.account_id, castle_ref=target.castle_ref,
            quest_id=DailyQuestId.USE_RESOURCE_ITEM, maintenance_date=local_date,
            max_mutations=1, max_diamond_spend=0,
        )
    elif acknowledgement is not None:
        parser.error("Do not supply mutation authority for a read-only inspection.")

    store = DailyRunJournalStore(config.artifact_root)
    reset_id = arguments.game_reset_id or f"pnc-reset-{now.date().isoformat()}-00"
    checkpoint: DailyTaskCheckpoint | None = None
    if arguments.reconcile_only:
        checkpoint = store.load(
            game_reset_id=reset_id, account_id=target.account_id, castle=target.castle,
        )
        if checkpoint is None:
            parser.error("No existing journal was found for --reconcile-only.")
        if not any(
            intent.quest_id == DailyQuestId.USE_RESOURCE_ITEM
            and intent.state != MutationIntentState.COMMITTED
            for intent in checkpoint.mutation_intents
        ):
            parser.error("The selected journal has no unresolved resource-use operation.")

    # This tool never invokes LoginTask or changes the selected castle. Avoid account
    # identifiers in generic framework console output; retain screenshot/journal evidence.
    logging.disable(logging.CRITICAL)
    application = build_application_runner(arguments.config)
    bundle = application.script_runner.build_connected_runtime_bundle(
        account=config.require_account(target.account_id),
    )
    connected = bundle.runtime
    observer = connected.observation_service
    actions = connected.require_observed_action_executor("Resource canary requires canonical observed actions.")
    verify_canary_identity(
        script_runner=application.script_runner,
        connected=bundle,
        target=target,
    )

    daily_session = ConnectedDailyQuestSession(bundle.runner, observer, actions)
    coordinator = DailyMaintenanceCoordinator.for_read_only(
        session=daily_session, journal_store=store, catalog=DailyQuestCatalog(),
    )
    session = ConnectedResourceItemSession(observer, actions, bundle.runner.flow_planner, coordinator)
    if not arguments.execute and not arguments.reconcile_only:
        inventory = session.scan_inventory()
        selected = smallest_resource_item(inventory)
        report = {
            "mode": "read_only", "account_id": target.account_id, "castle_ref": target.castle_ref,
            "inventory": asdict(inventory), "selected": None if selected is None else asdict(selected),
            "live_canary_passed": False,
        }
        _write_report(config.artifact_root, target.account_id, report)
        daily_session.return_to_home()
        return 0

    checkpoint = checkpoint or store.load(
        game_reset_id=reset_id, account_id=target.account_id, castle=target.castle,
    ) or DailyTaskCheckpoint(
        maintenance_date=local_date.isoformat(), game_reset_id=reset_id,
        account_id=target.account_id, castle=target.castle,
    )
    if checkpoint.game_reset_id != reset_id:
        raise ValueError("Journal reset identity conflicts; do not replay or discard existing receipts.")
    checkpoint, outcome = ResourceItemExecutor(session, JournaledMutationDispatcher(store)).execute(
        checkpoint=checkpoint, allow_empty_skip=role == CanaryRole.FREE_COOKIES,
    )
    if outcome.status == DailyTargetOutcomeStatus.SUCCESS and len(outcome.artifact_paths) >= 2:
        result_kind, reason = CanaryOutcome.PASSED, CanaryReason.NONE
    elif outcome.status == DailyTargetOutcomeStatus.APPLICABILITY_SKIP:
        result_kind, reason = CanaryOutcome.APPLICABILITY_SKIP, CanaryReason.NO_INVENTORY
    elif outcome.status == DailyTargetOutcomeStatus.SUCCESS:
        result_kind, reason = CanaryOutcome.BLOCKED, CanaryReason.ALREADY_COMMITTED
    else:
        result_kind, reason = CanaryOutcome.BLOCKED, CanaryReason.UNPROVEN_POSTCONDITION
    result = CanaryResult(
        quest_id=case.quest_id, role=role, revision=_resource_revision(),
        outcome=result_kind, reason=reason, artifact_paths=outcome.artifact_paths,
    )
    evidence_path = persist_canary_result(artifact_root=config.artifact_root, result=result)
    _write_report(config.artifact_root, target.account_id, {
        "mode": "reconcile_only" if arguments.reconcile_only else "execute",
        "account_id": target.account_id, "castle_ref": target.castle_ref,
        "castle": asdict(target.castle), "game_reset_id": reset_id,
        "result": asdict(result), "outcome": asdict(outcome),
        "canary_evidence_path": str(evidence_path),
        "journal_path": str(store.checkpoint_path(
            game_reset_id=checkpoint.game_reset_id,
            account_id=target.account_id, castle=target.castle,
        )),
    })
    return 0 if result_kind in {CanaryOutcome.PASSED, CanaryOutcome.APPLICABILITY_SKIP} else 1


def _resource_revision() -> str:
    """Fingerprints the current resource feature and shared mutation dependencies."""

    root = Path(__file__).resolve().parents[1]
    paths = (
        "pnc_automation/app/automation/daily_maintenance/resource_item.py",
        "pnc_automation/app/automation/daily_maintenance/connected_resource_item.py",
        "pnc_automation/app/automation/daily_maintenance/mutation_dispatcher.py",
        "pnc_automation/app/pnc/domain/resource_items.py",
        "pnc_automation/app/pnc/vision/resource_inventory.py",
        "pnc_automation/app/pnc/vision/pnc_observation_enricher.py",
        "pnc_automation/app/pnc/vision/observation_builder.py",
        "pnc_automation/app/pnc/navigation/screen_flows.py",
        "pnc_automation/app/pnc/persistence/daily_run_journal_store.py",
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode())
        digest.update((root / path).read_bytes())
    return digest.hexdigest()


def _write_report(root: Path, account_id: str, report: dict[str, object]) -> None:
    """Persists structured evidence through the canonical artifact store and prints its path."""

    artifact = ArtifactStore(root).persist_bytes(
        artifact_directory=account_id, label="resource_item_canary", extension="json",
        payload=json.dumps(report, indent=2, default=str).encode("utf-8"),
    )
    print(json.dumps({"report_path": str(artifact.path), **report}, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
