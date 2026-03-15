"""Application-facing script runner that wires session-specific services."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pnc_automation.adb.client import AdbClient
from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.automation.observed_action_executor import ObservedActionExecutor
from pnc_automation.automation.runner import AutomationRunner, RunResult, StepRunResult
from pnc_automation.automation.scripts.loader import load_run_script
from pnc_automation.automation.scripts.models import RunScript, ScriptStep
from pnc_automation.automation.scripts.registry import TaskRegistry
from pnc_automation.automation.task import TaskId
from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.models import AccountConfig, AppConfig, CastleIdentity, PncAccountCastleRosterConfig
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

        return self.run_script(account_id=account_id, script=load_run_script(script_path))

    def run_script(self, *, account_id: str, script: RunScript) -> RunResult:
        """Executes one already-loaded run script for the selected account."""

        account = self.config.require_account(account_id)
        prepared_script = self.task_registry.prepare_script(script)
        runner, castle_roster_provider = self._build_runner(account)
        return runner.run(
            account,
            prepared_script,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=self.castle_roster_store,
        )

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
    ) -> RunResult:
        """Runs the canonical session-preparation path for one account and optional castle target."""

        return self.run_script(
            account_id=account_id,
            script=RunScript(
                name="prepare_account_session",
                path=Path("<generated:prepare_account_session>"),
                steps=_prepare_account_session_steps(castle),
            ),
        )

    def run_task(
        self,
        *,
        account_id: str,
        task_id: TaskId,
        params: dict[str, Any] | None = None,
    ) -> StepRunResult:
        """Runs one task step against the selected account using current-castle semantics."""

        result = self.run_script(
            account_id=account_id,
            script=RunScript(
                name=f"direct_{task_id.value}",
                path=Path(f"<generated:{task_id.value}>"),
                steps=(ScriptStep(task=task_id, params={} if params is None else params),),
            ),
        )
        return result.steps[0]

    def _build_runner(
        self,
        account: AccountConfig,
    ) -> tuple[AutomationRunner, Callable[[], PncAccountCastleRosterConfig | None]]:
        """Builds one connected runtime runner and roster provider for a specific account."""

        instance_config = self.config.require_instance(account.instance_id)
        instance = BlueStacksInstance.from_config(instance_config)

        def castle_roster_provider() -> PncAccountCastleRosterConfig | None:
            """Returns the freshest roster snapshot for the active account throughout the run."""

            if self.castle_roster_store is not None:
                return self.castle_roster_store.get(account.pnc_account_id)
            return self.config.find_castle_roster(account.pnc_account_id)

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
            chat_stable_click_delay_ms=self.config.defaults.chat_stable_click_delay_ms,
            chat_post_action_observe_delay_ms=self.config.defaults.chat_post_action_observe_delay_ms,
            logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
        )
        return (
            AutomationRunner(
                defaults=self.config.defaults,
                observation_service=observation_service,
                action_executor=ObservedActionExecutor(
                    selector_registry=self.observation_builder.selector_registry,
                    action_executor=action_executor,
                    logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
                ),
                task_registry=self.task_registry,
                flow_planner=flow_planner,
                logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
            ),
            castle_roster_provider,
        )


def _prepare_account_session_steps(castle: CastleIdentity | None) -> tuple[ScriptStep, ...]:
    """Builds the canonical session-preparation step sequence for runtime entry points."""

    steps = [
        ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),
        ScriptStep(task=TaskId.LOGIN),
    ]
    if castle is not None:
        steps.append(ScriptStep(task=TaskId.SELECT_CASTLE, castle=castle))
    return tuple(steps)
