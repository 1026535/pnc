"""Application-facing script runner that wires session-specific services."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pnc_automation.adb.client import AdbClient
from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.automation.runner import AutomationRunner, RunResult
from pnc_automation.automation.scripts.loader import load_run_script
from pnc_automation.automation.scripts.registry import TaskRegistry
from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.models import AppConfig
from pnc_automation.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.vision.observation_builder import ObservationBuilder, ObservationService


@dataclass(slots=True)
class ScriptRunner:
    """Creates the per-run runtime and executes one automation script."""

    config: AppConfig
    task_registry: TaskRegistry
    screenshot_service: ScreenshotService
    observation_builder: ObservationBuilder
    castle_roster_store: CastleRosterStore | None
    adb_client: AdbClient
    logger: logging.LoggerAdapter

    def run(self, *, account_id: str, script_path: str) -> RunResult:
        """Executes the selected script for one configured account target."""

        account = self.config.require_account(account_id)
        run_script = load_run_script(script_path)
        prepared_script = self.task_registry.prepare_script(run_script)
        instance_config = self.config.require_instance(account.instance_id)
        instance = BlueStacksInstance.from_config(instance_config)

        session = BlueStacksSession(adb_client=self.adb_client, instance=instance)
        session.connect()
        session.ensure_responsive()

        observation_service = ObservationService(
            screenshot_service=self.screenshot_service,
            observation_builder=self.observation_builder,
            session=session,
            artifact_directory=account.artifact_directory_name,
            pnc_account_id=account.pnc_account_id,
            castle_roster_store=self.castle_roster_store,
        )
        flow_planner = ScreenFlowPlanner()
        shared_extra = {
            "account_id": account.id,
            "instance_id": instance.id,
            "pnc_account_id": account.pnc_account_id,
        }
        action_executor = ActionExecutor(
            session=session,
            stable_click_delay_ms=self.config.defaults.stable_click_delay_ms,
            post_action_observe_delay_ms=self.config.defaults.post_action_observe_delay_ms,
            logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
        )
        runner = AutomationRunner(
            defaults=self.config.defaults,
            observation_service=observation_service,
            action_executor=action_executor,
            task_registry=self.task_registry,
            flow_planner=flow_planner,
            logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
        )
        return runner.run(account, prepared_script)
