"""Application-facing script runner that wires session-specific services."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pnc_automation.core.infra.adb.client import AdbClient
from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.runner import AutomationRunner, RunResult, StepRunResult
from pnc_automation.app.authoring.scripts.loader import load_run_script
from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.mail.loader import (
    build_generated_send_mail_script_for_hour,
    generated_mail_schedule_name_for_hour,
    resolve_due_mail_dispatches_for_hour,
    resolve_scheduled_hour_bucket,
)
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.persistence.world_map_movement_calibration_store import WorldMapMovementCalibrationStore
from pnc_automation.app.pnc.persistence.world_map_survey_debug_store import WorldMapSurveyDebugStore
from pnc_automation.app.authoring.config.models import AccountConfig, AppConfig, CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import BlueStacksInstanceResolver
from pnc_automation.app.pnc.navigation.world_map_movement_calibration import WorldMapMovementCalibrationService
from pnc_automation.app.pnc.navigation.world_map_search import (
    ObservationBackedWorldMapCastleInspector,
    WorldMapSearchService,
)
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.core.infra.emulator.session import BlueStacksSession
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.observation_builder import ObservationBuilder, ObservationService


@dataclass(frozen=True, slots=True)
class ConnectedAccountRuntime:
    """Bundles the connected live-session services shared by automation runs, tools, and smoke tests."""

    session: BlueStacksSession
    observation_service: ObservationService
    flow_planner: ScreenFlowPlanner
    world_map_survey_recorder: WorldMapSurveyRecorder
    world_map_search_service: WorldMapSearchService
    world_map_movement_calibration_service: WorldMapMovementCalibrationService
    world_map_movement_calibration_store: WorldMapMovementCalibrationStore


@dataclass(frozen=True, slots=True)
class _ConnectedRuntimeServices:
    """Carries the canonical connected runtime services reused by both tooling and automation execution."""

    session: BlueStacksSession
    observation_service: ObservationService
    flow_planner: ScreenFlowPlanner
    world_map_survey_recorder: WorldMapSurveyRecorder
    world_map_search_service: WorldMapSearchService
    world_map_movement_calibration_service: WorldMapMovementCalibrationService
    world_map_movement_calibration_store: WorldMapMovementCalibrationStore
    observed_action_executor: ObservedActionExecutor | None


@dataclass(slots=True)
class ScriptRunner:
    """Creates the per-run runtime and executes one automation script."""

    config: AppConfig
    task_registry: TaskRegistry
    screenshot_service: ScreenshotService
    observation_builder: ObservationBuilder
    castle_roster_store: CastleRosterStore | None
    mail_archive_store: MailArchiveStore | None
    chat_archive_store: ChatArchiveStore | None
    adb_client: AdbClient
    instance_resolver: BlueStacksInstanceResolver
    logger: logging.LoggerAdapter

    def run(self, *, account_id: str, script_path: str) -> RunResult:
        """Executes the selected script for one configured account target."""

        return self.run_script(account_id=account_id, script=load_run_script(script_path))

    def run_script(self, *, account_id: str, script: RunScript) -> RunResult:
        """Executes one already-loaded run script for the selected account."""

        account = self.config.require_account(account_id)
        return self._run_script_for_account(account=account, script=script)

    def _run_script_for_account(self, *, account: AccountConfig, script: RunScript) -> RunResult:
        """Executes one already-loaded run script for one already-resolved account target."""

        prepared_script = self.task_registry.prepare_script(
            script,
            castle_targets=self.config.find_castle_targets(account.id),
        )
        runner, castle_roster_provider = self._build_runner(account)
        return runner.run(
            account,
            prepared_script,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=self.castle_roster_store,
            mail_archive_store=self.mail_archive_store,
            chat_archive_store=self.chat_archive_store,
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

    def run_mail_schedules(
        self,
        *,
        account_id: str,
        schedule_ids: list[str] | None = None,
        scheduled_for_utc: datetime | None = None,
    ) -> RunResult:
        """Resolves the due authored mail schedules and executes them as canonical send-mail steps."""

        account = self.config.require_account(account_id)
        catalog = self.config.require_mail_schedule_catalog()
        scheduled_hour = resolve_scheduled_hour_bucket(scheduled_for_utc)
        due_mail_dispatches = resolve_due_mail_dispatches_for_hour(
            catalog,
            scheduled_hour_utc=scheduled_hour,
            schedule_ids=schedule_ids,
        )
        if not due_mail_dispatches:
            return _build_noop_run_result(
                account_id=account.id,
                script_name=generated_mail_schedule_name_for_hour(scheduled_hour),
            )
        return self._run_script_for_account(
            account=account,
            script=build_generated_send_mail_script_for_hour(
                scheduled_hour_utc=scheduled_hour,
                due_mail_dispatches=due_mail_dispatches,
            ),
        )

    def build_connected_runtime(self, *, account: AccountConfig) -> ConnectedAccountRuntime:
        """Builds the canonical connected session plus observation-owned runtime helpers for one configured account."""

        services = self._build_connected_runtime_services(account=account)
        return ConnectedAccountRuntime(
            session=services.session,
            observation_service=services.observation_service,
            flow_planner=services.flow_planner,
            world_map_survey_recorder=services.world_map_survey_recorder,
            world_map_search_service=services.world_map_search_service,
            world_map_movement_calibration_service=services.world_map_movement_calibration_service,
            world_map_movement_calibration_store=services.world_map_movement_calibration_store,
        )

    def _build_connected_runtime_services(self, *, account: AccountConfig) -> _ConnectedRuntimeServices:
        """Builds the canonical connected runtime service graph shared by tooling and automation runs."""

        session = self.build_connected_session(account=account)
        observation_service = self._build_observation_service(account=account, session=session)
        flow_planner = ScreenFlowPlanner()
        world_map_survey_recorder = WorldMapSurveyRecorder(
            observation_service=observation_service,
            debug_store=WorldMapSurveyDebugStore(root=self.config.artifact_root),
        )
        world_map_movement_calibration_store = WorldMapMovementCalibrationStore(root=self.config.artifact_root)
        world_map_search_service = WorldMapSearchService(
            screen_flows=flow_planner,
            observation_service=observation_service,
            survey_recorder=world_map_survey_recorder,
        )
        world_map_movement_calibration_service = WorldMapMovementCalibrationService(
            screen_flows=flow_planner,
            observation_service=observation_service,
            survey_recorder=world_map_survey_recorder,
            search_service=world_map_search_service,
        )
        observed_executor = self._build_observed_action_executor(account=account, session=session)
        if observed_executor is not None:
            world_map_search_service.action_executor = observed_executor
            world_map_search_service.castle_inspector = ObservationBackedWorldMapCastleInspector(
                screen_flows=flow_planner,
                action_executor=observed_executor,
                observation_service=observation_service,
                survey_recorder=world_map_survey_recorder,
            )
            world_map_movement_calibration_service.action_executor = observed_executor
        return _ConnectedRuntimeServices(
            session=session,
            observation_service=observation_service,
            flow_planner=flow_planner,
            world_map_survey_recorder=world_map_survey_recorder,
            world_map_search_service=world_map_search_service,
            world_map_movement_calibration_service=world_map_movement_calibration_service,
            world_map_movement_calibration_store=world_map_movement_calibration_store,
            observed_action_executor=observed_executor,
        )

    def build_connected_automation_runner(self, *, account: AccountConfig) -> AutomationRunner:
        """Builds one connected automation runner through the same canonical runtime wiring used by `run_script()`."""

        runner, _ = self._build_runner(account)
        return runner

    def _build_runner(
        self,
        account: AccountConfig,
    ) -> tuple[AutomationRunner, Callable[[], PncAccountCastleRosterConfig | None]]:
        """Builds one connected runtime runner and roster provider for a specific account."""

        def castle_roster_provider() -> PncAccountCastleRosterConfig | None:
            """Returns the freshest roster snapshot for the active account throughout the run."""

            if self.castle_roster_store is not None:
                return self.castle_roster_store.get(account.pnc_account_id)
            return self.config.find_castle_roster(account.pnc_account_id)

        connected_runtime = self._build_connected_runtime_services(account=account)
        if connected_runtime.observed_action_executor is None:
            raise AttributeError("Automation runner requires an observation builder exposing selector_registry.")
        shared_extra = self._build_shared_extra(account=account, instance=connected_runtime.session.instance)
        return (
            AutomationRunner(
                defaults=self.config.defaults,
                observation_service=connected_runtime.observation_service,
                world_map_survey_recorder=connected_runtime.world_map_survey_recorder,
                world_map_search_service=connected_runtime.world_map_search_service,
                action_executor=connected_runtime.observed_action_executor,
                task_registry=self.task_registry,
                flow_planner=connected_runtime.flow_planner,
                logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
            ),
            castle_roster_provider,
        )

    def build_connected_session(self, *, account: AccountConfig) -> BlueStacksSession:
        """Resolves, logs, connects, and validates one canonical BlueStacks session for the selected account."""

        instance = self._resolve_instance(account=account)
        logging.LoggerAdapter(
            self.logger.logger,
            extra={
                **self.logger.extra,
                **self._build_shared_extra(account=account, instance=instance),
                "instance_display_name": instance.display_name,
                "device_id": instance.device_id,
            },
        ).info(
            f"Resolved BlueStacks instance '{instance.display_name}' to '{instance.device_id}'.",
        )
        session = BlueStacksSession(adb_client=self.adb_client, instance=instance)
        session.connect()
        session.ensure_responsive()
        return session

    def _build_observation_service(
        self,
        *,
        account: AccountConfig,
        session: BlueStacksSession,
    ) -> ObservationService:
        """Builds the canonical observation service for one already-connected account session."""

        return ObservationService(
            screenshot_service=self.screenshot_service,
            observation_builder=self.observation_builder,
            session=session,
            artifact_directory=account.artifact_directory_name,
            mode=self.config.runtime.observation_mode,
            pnc_account_id=account.pnc_account_id,
            castle_roster_store=self.castle_roster_store,
        )

    def _resolve_instance(self, *, account: AccountConfig) -> BlueStacksInstance:
        """Resolves the configured BlueStacks display name for one account into a live runtime target."""

        instance_config = self.config.require_instance(account.instance_id)
        return self.instance_resolver.resolve(instance_config)

    def _build_shared_extra(self, *, account: AccountConfig, instance: BlueStacksInstance) -> dict[str, str]:
        """Builds the shared structured log context for one account-bound runtime session."""

        return {
            "account_id": account.id,
            "instance_id": instance.id,
            "pnc_account_id": account.pnc_account_id,
        }

    def _build_observed_action_executor(
        self,
        *,
        account: AccountConfig,
        session: BlueStacksSession,
    ) -> ObservedActionExecutor | None:
        """Builds the canonical observed-action executor when the observation builder exposes selector metadata."""

        selector_registry = getattr(self.observation_builder, "selector_registry", None)
        if selector_registry is None:
            return None
        shared_extra = self._build_shared_extra(account=account, instance=session.instance)
        return ObservedActionExecutor(
            selector_registry=selector_registry,
            action_executor=ActionExecutor(
                session=session,
                stable_click_delay_ms=self.config.defaults.stable_click_delay_ms,
                post_action_observe_delay_ms=self.config.defaults.post_action_observe_delay_ms,
                chat_stable_click_delay_ms=self.config.defaults.chat_stable_click_delay_ms,
                chat_post_action_observe_delay_ms=self.config.defaults.chat_post_action_observe_delay_ms,
                logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
            ),
            logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
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


def _build_noop_run_result(*, account_id: str, script_name: str) -> RunResult:
    """Builds one successful no-op run result when no scheduled mail is due."""

    now = datetime.now(tz=UTC)
    return RunResult(
        account_id=account_id,
        script_name=script_name,
        steps=(),
        started_at=now,
        finished_at=now,
    )

