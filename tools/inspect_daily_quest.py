"""Perform one explicit read-only live traversal of a castle's Daily Quest list."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from _script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.automation.engine.script_runner import require_successful_preparation
from pnc_automation.app.automation.daily_maintenance.coordinator import DailyMaintenanceCoordinator
from pnc_automation.app.automation.daily_maintenance.live_session import ConnectedDailyQuestSession
from pnc_automation.app.authoring.config.loader import load_app_config
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


def main() -> int:
    """Aligns one explicit castle and prints a non-mutating Daily survey."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/accounts.yaml")
    parser.add_argument("--account", required=True)
    parser.add_argument("--castle-ref", required=True)
    arguments = parser.parse_args()
    app_config = load_app_config(Path(arguments.config))
    account = app_config.require_account(arguments.account)
    target_catalog = app_config.find_castle_targets(arguments.account)
    if target_catalog is None:
        parser.error(f"Account '{arguments.account}' has no authored castle targets.")
    castle = target_catalog.require(arguments.castle_ref)
    application = build_application_runner(arguments.config)
    account.require_live_role(LiveAutomationRole.DAILY_CANARY)
    with application.script_runner.reserve_accounts((arguments.account,)):
        require_successful_preparation(
            application.prepare_account_session(
                account_id=arguments.account,
                castle=castle,
                required_role=LiveAutomationRole.DAILY_CANARY,
            )
        )
        with application.script_runner.build_connected_runtime_bundle(
            account=account,
            required_role=LiveAutomationRole.DAILY_CANARY,
        ) as bundle:
            action_executor = bundle.runtime.require_observed_action_executor(
                "Daily survey requires the canonical selector-backed action executor."
            )
            session = ConnectedDailyQuestSession(
                runner=bundle.runner,
                observation_service=bundle.runtime.observation_service,
                action_executor=action_executor,
            )
            coordinator = DailyMaintenanceCoordinator.for_read_only(
                session=session,
                journal_store=DailyRunJournalStore(app_config.artifact_root),
                catalog=DailyQuestCatalog(),
            )
            survey = coordinator.survey_read_only()
            print(json.dumps(asdict(survey), indent=2, default=str))
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
