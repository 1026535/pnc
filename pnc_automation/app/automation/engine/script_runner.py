"""Application-facing script runner that wires session-specific services."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.adb.client import AdbClient
from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.runner import AutomationRunner, RunResult, StepRunResult
from pnc_automation.app.authoring.scripts.loader import load_run_script
from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.pnc.domain.action_requests import SwipeGesturePrimitive
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.authoring.mail.loader import (
    build_generated_send_mail_script_for_hour,
    generated_mail_schedule_name_for_hour,
    resolve_due_mail_dispatches_for_hour,
    resolve_scheduled_hour_bucket,
)
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, ScreenshotService
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.persistence.world_map_movement_calibration_store import WorldMapMovementCalibrationStore
from pnc_automation.app.pnc.persistence.world_map_survey_debug_store import WorldMapSurveyDebugStore
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    AppConfig,
    LiveAutomationRole,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import BlueStacksInstanceResolver
from pnc_automation.app.pnc.navigation.world_map_movement_calibration import WorldMapMovementCalibrationService
from pnc_automation.app.pnc.navigation.world_map_analysis import WorldMapViewportAnalyzer
from pnc_automation.app.pnc.navigation.world_map_search import (
    ObservationBackedWorldMapCastleInspector,
    WorldMapSearchService,
)
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.core.infra.emulator.session import (
    BlueStacksInstanceCloser,
    BlueStacksSession,
    BlueStacksSessionCleanupPolicy,
)
from pnc_automation.core.lifecycle import close_preserving_error
from pnc_automation.bluestacks_management.instance_shutdown import (
    InstanceShutdownIntentStore,
    PowerShellBlueStacksInstanceCloser,
)
from pnc_automation.bluestacks_management.instance_lease import (
    PROCESS_INSTANCE_LEASES,
    InstanceLeaseBundle,
    InstanceLeaseRegistry,
    ProcessInstanceLease,
)
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.observation_builder import ObservationBuilder, ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest


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
    observed_action_executor: ObservedActionExecutor | None

    def close(self) -> None:
        """Releases the connected session's operation lease."""

        self.session.close()

    def __enter__(self) -> "ConnectedAccountRuntime":
        """Enters an explicitly scoped connected runtime."""

        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        """Releases the connected runtime on normal or exceptional exit."""

        active_error = _exception if isinstance(_exception, BaseException) else None
        close_preserving_error(
            self.close,
            active_error,
            message="Connected runtime operation and cleanup both failed.",
        )

    def require_observed_action_executor(self, reason: str) -> ObservedActionExecutor:
        """Returns the selector-backed executor required by live connected-runtime operations."""

        if self.observed_action_executor is None:
            raise SelectorResolutionError(reason)
        return self.observed_action_executor


@dataclass(frozen=True, slots=True)
class ConnectedAutomationRuntime:
    """Exposes feature services and runner execution from one shared connected object graph."""

    runtime: ConnectedAccountRuntime
    runner: AutomationRunner

    def close(self) -> None:
        """Releases the shared connected runtime and its operation lease."""

        self.runtime.close()

    def __enter__(self) -> "ConnectedAutomationRuntime":
        """Enters an explicitly scoped connected runtime bundle."""

        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        """Releases the connected runtime bundle on exit."""

        active_error = _exception if isinstance(_exception, BaseException) else None
        close_preserving_error(
            self.close,
            active_error,
            message="Connected automation operation and cleanup both failed.",
        )


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
    p2_observation_builder_factory: Callable[[], ObservationBuilder] | None = None
    instance_lease_registry: InstanceLeaseRegistry = field(
        default_factory=lambda: PROCESS_INSTANCE_LEASES,
        repr=False,
    )
    instance_closer: BlueStacksInstanceCloser | None = field(default=None, repr=False)

    def reserve_accounts(
        self,
        account_ids: tuple[str, ...],
        *,
        timeout_seconds: float | None = None,
    ) -> InstanceLeaseBundle:
        """Reserves a complete multi-instance bundle before any account session connects."""

        display_names = tuple(
            dict.fromkeys(
                self.config.require_instance(self.config.require_account(account_id).instance_id).display_name
                for account_id in account_ids
            )
        )
        return self.instance_lease_registry.acquire_bundle(
            display_names,
            timeout_seconds=timeout_seconds,
        )

    def run(
        self,
        *,
        account_id: str,
        script_path: str,
        castle_refs: list[str] | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> RunResult:
        """Executes the selected script for one account and optional ordered castle aliases."""

        return self.run_script(
            account_id=account_id,
            script=load_run_script(script_path),
            castle_refs=castle_refs,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )

    def run_script(
        self,
        *,
        account_id: str,
        script: RunScript,
        castle_refs: list[str] | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> RunResult:
        """Executes one loaded script for an account and optional ordered castle aliases."""

        account = self.config.require_account(account_id)
        return self._run_script_for_account(
            account=account,
            script=script,
            castle_refs=castle_refs,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )

    def _run_script_for_account(
        self,
        *,
        account: AccountConfig,
        script: RunScript,
        castle_refs: list[str] | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> RunResult:
        """Executes one already-loaded run script for one already-resolved account target."""

        prepared_script = self.task_registry.prepare_script(
            script,
            castle_targets=self.config.find_castle_targets(account.id),
            castle_refs=castle_refs,
        )
        runner, castle_roster_provider = self._build_runner(
            account,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )
        try:
            result = runner.run(
                account,
                prepared_script,
                castle_roster_provider=castle_roster_provider,
                castle_roster_store=self.castle_roster_store,
                mail_archive_store=self.mail_archive_store,
                chat_archive_store=self.chat_archive_store,
            )
        except BaseException as error:
            close_preserving_error(
                runner.close,
                error,
                message="Automation execution and BlueStacks phase cleanup both failed.",
            )
            raise
        runner.close()
        return result

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> RunResult:
        """Runs the canonical session-preparation path for one account and optional castle target."""

        return self.run_script(
            account_id=account_id,
            script=RunScript(
                name="prepare_account_session",
                path=Path("<generated:prepare_account_session>"),
                steps=_prepare_account_session_steps(castle),
            ),
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )

    def run_task(
        self,
        *,
        account_id: str,
        task_id: TaskId,
        params: dict[str, Any] | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> StepRunResult:
        """Runs one task step against the selected account using current-castle semantics."""

        result = self.run_script(
            account_id=account_id,
            script=RunScript(
                name=f"direct_{task_id.value}",
                path=Path(f"<generated:{task_id.value}>"),
                steps=(ScriptStep(task=task_id, params={} if params is None else params),),
            ),
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )
        return result.steps[0]

    def run_mail_schedules(
        self,
        *,
        account_id: str,
        schedule_ids: list[str] | None = None,
        scheduled_for_utc: datetime | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
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
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )

    def build_connected_runtime(
        self,
        *,
        account: AccountConfig,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> ConnectedAccountRuntime:
        """Builds the canonical connected session plus observation-owned runtime helpers for one configured account."""

        if required_role is not None:
            account.require_live_role(required_role)
        return self._build_connected_runtime_services(
            account=account,
            session_cleanup_policy=session_cleanup_policy,
        )

    def _build_connected_runtime_services(
        self,
        *,
        account: AccountConfig,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> ConnectedAccountRuntime:
        """Builds the canonical connected runtime service graph shared by tooling and automation runs."""

        session = self.build_connected_session(
            account=account,
            cleanup_policy=session_cleanup_policy,
        )
        try:
            return self._build_connected_runtime_services_for_session(account=account, session=session)
        except BaseException as error:
            close_preserving_error(
                session.close,
                error,
                message="Connected runtime construction and BlueStacks phase cleanup both failed.",
            )
            raise

    def _build_connected_runtime_services_for_session(
        self,
        *,
        account: AccountConfig,
        session: BlueStacksSession,
    ) -> ConnectedAccountRuntime:
        """Builds service helpers for a session whose lease is already owned by this operation."""

        observation_service = self._build_observation_service(account=account, session=session)
        flow_planner = ScreenFlowPlanner()
        world_map_survey_recorder = WorldMapSurveyRecorder(
            observation_service=observation_service,
            debug_store=WorldMapSurveyDebugStore(root=self.config.artifact_root),
        )
        world_map_movement_calibration_store = WorldMapMovementCalibrationStore(root=self.config.artifact_root)
        p2_observation_builder: ObservationBuilder | None = None

        def build_p2_observation(screenshot: CapturedScreenshot, request: ObservationRequest) -> Observation:
            """Lazily builds the independently owned P2 pipeline on its worker thread."""

            nonlocal p2_observation_builder
            if p2_observation_builder is None:
                p2_observation_builder = (
                    self.observation_builder
                    if self.p2_observation_builder_factory is None
                    else self.p2_observation_builder_factory()
                )
            return p2_observation_builder.build(screenshot, request=request)

        world_map_search_service = WorldMapSearchService(
            screen_flows=flow_planner,
            observation_service=observation_service,
            survey_recorder=world_map_survey_recorder,
            viewport_analyzer=WorldMapViewportAnalyzer(observation_builder=build_p2_observation),
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
        return ConnectedAccountRuntime(
            session=session,
            observation_service=observation_service,
            flow_planner=flow_planner,
            world_map_survey_recorder=world_map_survey_recorder,
            world_map_search_service=world_map_search_service,
            world_map_movement_calibration_service=world_map_movement_calibration_service,
            world_map_movement_calibration_store=world_map_movement_calibration_store,
            observed_action_executor=observed_executor,
        )

    def build_connected_automation_runner(
        self,
        *,
        account: AccountConfig,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> AutomationRunner:
        """Builds one connected automation runner through the same canonical runtime wiring used by `run_script()`."""

        runner, _ = self._build_runner(
            account,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )
        return runner

    def build_connected_runtime_bundle(
        self,
        *,
        account: AccountConfig,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> ConnectedAutomationRuntime:
        """Builds feature services and an automation runner that share one connected service graph."""

        if required_role is not None:
            account.require_live_role(required_role)
        connected_runtime = self._build_connected_runtime_services(
            account=account,
            session_cleanup_policy=session_cleanup_policy,
        )
        return ConnectedAutomationRuntime(
            runtime=connected_runtime,
            runner=self._build_automation_runner_from_services(
                account=account,
                connected_runtime=connected_runtime,
            ),
        )

    def _build_runner(
        self,
        account: AccountConfig,
        *,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> tuple[AutomationRunner, Callable[[], PncAccountCastleRosterConfig | None]]:
        """Builds one connected runtime runner and roster provider for a specific account."""

        def castle_roster_provider() -> PncAccountCastleRosterConfig | None:
            """Returns the freshest roster snapshot for the active account throughout the run."""

            if self.castle_roster_store is not None:
                return self.castle_roster_store.get(account.pnc_account_id)
            return self.config.find_castle_roster(account.pnc_account_id)

        if required_role is not None:
            account.require_live_role(required_role)
        connected_runtime = self._build_connected_runtime_services(
            account=account,
            session_cleanup_policy=session_cleanup_policy,
        )
        return (
            self._build_automation_runner_from_services(
                account=account,
                connected_runtime=connected_runtime,
            ),
            castle_roster_provider,
        )

    def _build_automation_runner_from_services(
        self,
        *,
        account: AccountConfig,
        connected_runtime: ConnectedAccountRuntime,
    ) -> AutomationRunner:
        """Builds a runner over an already-created connected service graph."""

        try:
            observed_action_executor = connected_runtime.require_observed_action_executor(
                "Automation runner requires an observation builder exposing selector_registry."
            )
            shared_extra = self._build_shared_extra(account=account, instance=connected_runtime.session.instance)
            return AutomationRunner(
                defaults=self.config.defaults,
                observation_service=connected_runtime.observation_service,
                world_map_survey_recorder=connected_runtime.world_map_survey_recorder,
                world_map_search_service=connected_runtime.world_map_search_service,
                action_executor=observed_action_executor,
                task_registry=self.task_registry,
                flow_planner=connected_runtime.flow_planner,
                logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
                close_callback=connected_runtime.close,
            )
        except BaseException as error:
            close_preserving_error(
                connected_runtime.close,
                error,
                message="Automation runner construction and BlueStacks phase cleanup both failed.",
            )
            raise

    def build_connected_session(
        self,
        *,
        account: AccountConfig,
        required_role: LiveAutomationRole | None = None,
        cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> BlueStacksSession:
        """Resolves, logs, connects, and validates one canonical BlueStacks session for the selected account."""

        if required_role is not None:
            account.require_live_role(required_role)
        instance_config = self.config.require_instance(account.instance_id)
        instance_lease = self.instance_lease_registry.acquire(display_name=instance_config.display_name)
        try:
            instance = self._resolve_instance(account=account)
        except BaseException:
            instance_lease.release()
            raise
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
        session = BlueStacksSession(
            adb_client=self.adb_client,
            instance=instance,
            lease_registry=self.instance_lease_registry,
            capabilities=account.bluestacks_capabilities,
            cleanup_policy=cleanup_policy or BlueStacksSessionCleanupPolicy.keep_warm(),
            instance_closer=self._build_instance_closer(),
            instance_lease=instance_lease,
        )
        try:
            session.connect()
            session.ensure_responsive()
        except BaseException as error:
            close_preserving_error(
                session.close,
                error,
                message="BlueStacks readiness validation and phase cleanup both failed.",
            )
            raise
        return session

    def _build_instance_closer(self) -> BlueStacksInstanceCloser | None:
        """Builds the host closer only when the configured resolver exposes live process discovery."""

        if self.instance_closer is not None:
            return self.instance_closer
        running_instance_source = getattr(self.instance_resolver, "running_instance_source", None)
        if running_instance_source is None:
            return None
        metadata_path = getattr(self.instance_resolver, "config_path", None)
        if not isinstance(metadata_path, Path):
            return None
        return PowerShellBlueStacksInstanceCloser(
            running_instance_source=running_instance_source,
            metadata_path=metadata_path,
            intent_store=InstanceShutdownIntentStore(
                self.instance_lease_registry.root / "shutdown-intents"
            ),
            lease_registry_factory=lambda: InstanceLeaseRegistry(
                root=self.instance_lease_registry.root,
                wait_timeout_seconds=0,
            ),
        )

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
        return self.instance_resolver.resolve(
            instance_config,
            allow_launch=account.bluestacks_capabilities.allow_instance_launch,
        )

    def _build_shared_extra(self, *, account: AccountConfig, instance: BlueStacksInstance) -> dict[str, str]:
        """Builds the shared structured log context for one account-bound runtime session."""

        return {
            "account_id": account.id,
            "instance_id": instance.id,
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
                world_map_movement_stable_click_delay_ms=self.config.defaults.world_map_movement_stable_click_delay_ms,
                world_map_movement_post_action_observe_delay_ms=self.config.defaults.world_map_movement_post_action_observe_delay_ms,
                logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
            ),
            logger=logging.LoggerAdapter(self.logger.logger, extra={**self.logger.extra, **shared_extra}),
        )


def configure_world_map_movement_budget(runtime: ConnectedAccountRuntime, movement_step_budget: int) -> None:
    """Applies one shared world-map movement step budget to the connected runtime services."""

    if movement_step_budget <= 0:
        raise ValueError("World-map movement step budget must be positive.")
    runtime.world_map_movement_calibration_service.movement_step_budget = movement_step_budget
    runtime.world_map_search_service.movement_step_budget = movement_step_budget


def require_successful_preparation(result: RunResult) -> RunResult:
    """Requires every preparation step to finish successfully or be safely skipped."""

    accepted_statuses = {TaskStatus.SUCCESS, TaskStatus.SKIPPED}
    if not result.steps or any(step.status not in accepted_statuses for step in result.steps):
        raise RuntimeError(f"Account session preparation failed: {result.steps}")
    return result


def configure_world_map_movement_granularity(
    runtime: ConnectedAccountRuntime,
    *,
    max_axis_delta_per_leg: int | None,
) -> None:
    """Applies one shared direct-movement granularity cap to the connected world-map coordinate mover."""

    mover = runtime.world_map_search_service.coordinate_mover_for_runtime()
    mover.movement_policy = type(mover.movement_policy)(
        gesture_primitive=mover.movement_policy.gesture_primitive,
        arrival_tolerance_units=mover.movement_policy.arrival_tolerance_units,
        overshoot_tolerance_units=mover.movement_policy.overshoot_tolerance_units,
        correction_threshold_units=mover.movement_policy.correction_threshold_units,
        traverse_max_axis_delta_per_leg=max_axis_delta_per_leg,
        correction_max_axis_delta_per_leg=max_axis_delta_per_leg,
    )


def configure_world_map_movement_gesture_primitive(
    runtime: ConnectedAccountRuntime,
    *,
    gesture_primitive: SwipeGesturePrimitive,
) -> None:
    """Applies one shared world-map drag primitive across the connected search and calibration services."""

    runtime.flow_planner.world_map_navigator.gesture_primitive = gesture_primitive
    mover = runtime.world_map_search_service.coordinate_mover
    if mover is not None:
        mover.movement_policy = type(mover.movement_policy)(
            gesture_primitive=gesture_primitive,
            correction_threshold_units=mover.movement_policy.correction_threshold_units,
            traverse_max_axis_delta_per_leg=mover.movement_policy.traverse_max_axis_delta_per_leg,
            correction_max_axis_delta_per_leg=mover.movement_policy.correction_max_axis_delta_per_leg,
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

