"""Canonical observe-plan-act-verify automation runner."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.authoring.scripts.models import PreparedRunScript, PreparedScriptStep, ScriptStep
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.automation.engine.task import CastleTargetPolicy, TaskId, TaskPreflight
from pnc_automation.app.automation.engine.task_executor import TaskExecutionResult, TaskExecutor
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapSearchService
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.authoring.config.models import AccountConfig, DefaultsConfig
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.core.errors import SelectorResolutionError, TaskVerificationError
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, WaitAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.observation_builder import ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.domain.observation_policy import ObservationArtifactKind, observation_artifact_selection


@dataclass(frozen=True, slots=True)
class StepRunResult:
    """Summarizes one completed script step."""

    task_id: TaskId
    status: TaskStatus
    attempts: int
    message: str
    requested_castle: CastleIdentity | None = None
    provenance: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunResult:
    """Summarizes one completed automation run."""

    account_id: str
    script_name: str
    steps: tuple[StepRunResult, ...]
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class StepExecutionPolicy:
    """Centralizes retry and replan limits for one automation runner."""

    max_replans_per_step: int = 5
    max_retries_per_step: int = 1

    def __post_init__(self) -> None:
        """Rejects invalid negative execution-policy limits."""

        if self.max_replans_per_step < 0:
            raise ValueError("StepExecutionPolicy.max_replans_per_step cannot be negative.")
        if self.max_retries_per_step < 0:
            raise ValueError("StepExecutionPolicy.max_retries_per_step cannot be negative.")


@dataclass(slots=True)
class AutomationRunner:
    """Executes a run script through the canonical observation loop."""

    defaults: DefaultsConfig
    observation_service: ObservationService
    action_executor: ObservedActionExecutor
    task_registry: TaskRegistry
    flow_planner: ScreenFlowPlanner
    logger: logging.LoggerAdapter
    world_map_survey_recorder: WorldMapSurveyRecorder | None = None
    world_map_search_service: WorldMapSearchService | None = None
    policy: StepExecutionPolicy = field(default_factory=StepExecutionPolicy)
    close_callback: Callable[[], None] | None = field(default=None, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        """Releases any connected session owned by this runner."""

        if self._closed:
            return
        self._closed = True
        if self.close_callback is not None:
            self.close_callback()

    def __enter__(self) -> "AutomationRunner":
        """Enters an explicitly scoped automation runner."""

        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        """Releases the runner's connected session on exit."""

        self.close()

    def execute_flow_until(
        self,
        *,
        label_prefix: str,
        planner: Callable[[Observation], list[ActionRequest]],
        done: Callable[[Observation], bool],
        start_observation: Observation | None = None,
        max_steps: int | None = None,
    ) -> Observation:
        """Executes one bounded external navigation loop through the canonical observe-plan-act seam."""

        current = start_observation or self.observation_service.observe(f"{label_prefix}_start")
        step_budget = self.policy.max_replans_per_step if max_steps is None else max_steps
        if step_budget < 0:
            raise ValueError("AutomationRunner.execute_flow_until max_steps cannot be negative.")
        step_index = 0
        while step_index <= step_budget:
            recovered = self.action_executor.recover_interruption_if_required(
                current,
                label_prefix=f"{label_prefix}_interruption",
                observe=lambda label, request=None: self.observation_service.observe(
                    f"{label_prefix}_{label}",
                    request=request,
                ),
            )
            if recovered is not None:
                current = recovered
                continue
            if done(current):
                return current
            if current.screen_type == ScreenType.UNKNOWN:
                actions = self.flow_planner.recover_unknown_game_screen(
                    current,
                    reason=f"{label_prefix}_recover_unknown",
                )
            else:
                actions = planner(current)
            if not actions:
                raise SelectorResolutionError(
                    "Automation runner could not derive an action for the requested flow state.",
                    screen_type=current.screen_type.value,
                    label_prefix=label_prefix,
                )
            current = self.action_executor.execute_actions(
                actions,
                current,
                observe=lambda label, request=None: self.observation_service.observe(
                    f"{label_prefix}_step_{step_index}_{label}",
                    request=request,
                ),
            ).observation
            step_index += 1
        raise SelectorResolutionError(
            "Automation runner could not prove the requested flow state within the configured budget.",
            screen_type=current.screen_type.value,
            label_prefix=label_prefix,
        )

    def prove_preflight_state(
        self,
        account: AccountConfig,
        requirement: TaskPreflight,
        *,
        label_prefix: str,
        start_observation: Observation | None = None,
        max_steps: int | None = None,
        castle_roster_store: CastleRosterStore | None = None,
        mail_archive_store: MailArchiveStore | None = None,
        chat_archive_store: ChatArchiveStore | None = None,
    ) -> Observation:
        """Proves one shared runner-owned preflight state for external callers such as live tools and smoke helpers."""

        current = start_observation or self.observation_service.observe(f"{label_prefix}_start")
        if requirement == TaskPreflight.NONE:
            return current
        del account, castle_roster_store, mail_archive_store, chat_archive_store
        return self.execute_flow_until(
            label_prefix=label_prefix,
            planner=lambda observation: self._plan_task_preflight(requirement, observation),
            done=lambda observation: self._task_preflight_is_satisfied(requirement, observation),
            start_observation=current,
            max_steps=max_steps,
        )

    def run(
        self,
        account: AccountConfig,
        script: PreparedRunScript,
        *,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None = None,
        castle_roster_store: CastleRosterStore | None = None,
        mail_archive_store: MailArchiveStore | None = None,
        chat_archive_store: ChatArchiveStore | None = None,
    ) -> RunResult:
        """Runs the provided script for one account target."""

        started_at = datetime.now(tz=UTC)
        step_results = [
            self._run_step(
                account,
                step,
                castle_roster_provider=castle_roster_provider,
                castle_roster_store=castle_roster_store,
                mail_archive_store=mail_archive_store,
                chat_archive_store=chat_archive_store,
            )
            for step in script.steps
        ]
        finished_at = datetime.now(tz=UTC)
        return RunResult(
            account_id=account.id,
            script_name=script.name,
            steps=tuple(step_results),
            started_at=started_at,
            finished_at=finished_at,
        )

    def _run_step(
        self,
        account: AccountConfig,
        step: PreparedScriptStep,
        *,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
    ) -> StepRunResult:
        """Executes one script step until it succeeds or fails."""

        before = self.observation_service.observe(f"{step.task.value}_before")
        before = self._align_step_castle_target(
            account=account,
            step=step,
            before=before,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
        )
        execution = self._execute_step_loop(
            account=account,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
            step=step.script_step,
            parsed_params=step.parsed_params,
            target_castle=step.castle,
            before=before,
        )
        return StepRunResult(
            task_id=step.task,
            status=execution.result.status,
            attempts=execution.attempts,
            message=execution.result.message,
            requested_castle=step.castle,
            provenance=dict(step.provenance),
        )

    def _align_step_castle_target(
        self,
        *,
        account: AccountConfig,
        step: PreparedScriptStep,
        before: Observation,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
    ) -> Observation:
        """Runs the canonical synthetic pre-step castle alignment when one target was requested."""

        if step.castle is None or step.castle_target_policy != CastleTargetPolicy.OPTIONAL:
            return before
        synthetic_step = ScriptStep(task=TaskId.SELECT_CASTLE, castle=step.castle)
        select_castle_task = self.task_registry.require(TaskId.SELECT_CASTLE)
        execution = self._execute_step_loop(
            account=account,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
            step=synthetic_step,
            parsed_params=select_castle_task.parse_params({}),
            target_castle=step.castle,
            before=before,
        )
        return execution.final_observation

    def _execute_step_loop(
        self,
        *,
        account: AccountConfig,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
        step: ScriptStep,
        parsed_params: Any,
        target_castle: CastleIdentity | None,
        before: Observation,
    ) -> TaskExecutionResult:
        """Preflights one task and delegates to the canonical task executor."""

        task = self.task_registry.require(step.task)
        context = self._build_context(
            account=account,
            castle_roster_provider=castle_roster_provider,
            castle_roster_store=castle_roster_store,
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
            step=step,
            parsed_params=parsed_params,
            target_castle=target_castle,
        )
        current_before = self._run_task_preflight(
            task=task,
            step=step,
            context=context,
            before=before,
            account=account,
            castle_roster_store=castle_roster_store,
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
        )
        return TaskExecutor(
            observation_service=self.observation_service,
            action_executor=self.action_executor,
            logger=self.logger,
            max_replans_per_step=self.policy.max_replans_per_step,
            max_retries_per_step=self.policy.max_retries_per_step,
        ).execute(task=task, context=context, before=current_before)

    def _run_task_preflight(
        self,
        *,
        task: object,
        step: ScriptStep,
        context: TaskContext,
        before: Observation,
        account: AccountConfig,
        castle_roster_store: CastleRosterStore | None,
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
    ) -> Observation:
        """Proves the task-declared entry state once before the task body begins executing."""

        recovered = self.action_executor.recover_interruption_if_required(
            before,
            label_prefix=f"{step.task.value}_preflight_update",
            observe=lambda label, request=None: self.observation_service.observe(
                f"{step.task.value}_{label}",
                request=request,
            ),
        )
        if recovered is not None:
            before = recovered
        requirement = getattr(task, "preflight", TaskPreflight.NONE)
        if requirement == TaskPreflight.NONE:
            return before
        current = before
        attempts = 0
        while not self._task_preflight_is_satisfied(requirement, current):
            recovered = self.action_executor.recover_interruption_if_required(
                current,
                label_prefix=f"{step.task.value}_preflight_interruption",
                observe=lambda label, request=None: self.observation_service.observe(
                    f"{step.task.value}_{label}",
                    request=request,
                ),
            )
            if recovered is not None:
                current = recovered
                continue
            attempts += 1
            if attempts > self.policy.max_replans_per_step:
                self._raise_task_verification_error(
                    f"Task '{step.task}' could not prove its required preflight screen '{requirement.value}'.",
                    task_id=step.task,
                    observation=current,
                    screen_type=current.screen_type,
                    label=f"{step.task.value}_failure_preflight",
                    preflight=requirement.value,
                )
            if self._task_preflight_is_satisfied(requirement, current):
                return current
            actions = self._plan_task_preflight(requirement, current)
            if not actions:
                self._raise_task_verification_error(
                    f"Task '{step.task}' could not derive a preflight action for '{requirement.value}'.",
                    task_id=step.task,
                    observation=current,
                    screen_type=current.screen_type,
                    label=f"{step.task.value}_failure_preflight_plan",
                    preflight=requirement.value,
                )
            execution = self.action_executor.execute_actions(
                actions,
                current,
                observe=lambda label, request=None: self.observation_service.observe(
                    f"{step.task.value}_{label}",
                    request=request,
                ),
            )
            current = execution.observation
        return current

    def _task_preflight_is_satisfied(self, requirement: TaskPreflight, observation: Observation) -> bool:
        """Returns whether one observation already proves the declared task preflight."""

        if requirement == TaskPreflight.NONE:
            return True
        if requirement == TaskPreflight.HOME_CITY:
            return observation.screen_type == ScreenType.PNC_HOME_CITY
        if requirement == TaskPreflight.WORLD_MAP:
            return observation.screen_type == ScreenType.PNC_WORLD_MAP and observation.spatial_surface is not None
        raise AssertionError(f"Unsupported task preflight '{requirement}'.")

    def _plan_task_preflight(self, requirement: TaskPreflight, observation: Observation) -> list[ActionRequest]:
        """Returns the next runner-owned action increment needed to prove one task preflight."""

        if requirement == TaskPreflight.HOME_CITY:
            if observation.screen_type == ScreenType.PNC_HOME_CITY_ROOT:
                return [
                    WaitAction(
                        milliseconds=250,
                        reason="prove_home_city_root",
                        observe_after=True,
                        follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
                    )
                ]
            return self.flow_planner.ensure_home_city(observation)
        if requirement == TaskPreflight.WORLD_MAP:
            if observation.screen_type == ScreenType.PNC_WORLD_MAP_ROOT:
                return [
                    WaitAction(
                        milliseconds=250,
                        reason="prove_world_map_root",
                        observe_after=True,
                        follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
                    )
                ]
            return self.flow_planner.ensure_world_map_ready(observation)
        raise AssertionError(f"Unsupported task preflight '{requirement}'.")

    def _build_context(
        self,
        *,
        account: AccountConfig,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None,
        castle_roster_store: CastleRosterStore | None,
        mail_archive_store: MailArchiveStore | None,
        chat_archive_store: ChatArchiveStore | None,
        step: ScriptStep,
        parsed_params: Any,
        target_castle: CastleIdentity | None,
    ) -> TaskContext:
        """Builds the shared task context for one canonical task execution."""

        logger_extra = {**self.logger.extra, "task_id": step.task}
        if target_castle is not None:
            logger_extra["target_castle"] = f"{target_castle.kingdom}/{target_castle.castle_name}"
        mail_id = step.provenance.get("mail_id")
        if isinstance(mail_id, str) and mail_id.strip() != "":
            logger_extra["mail_id"] = mail_id
        schedule_id = step.provenance.get("schedule_id")
        if isinstance(schedule_id, str) and schedule_id.strip() != "":
            logger_extra["schedule_id"] = schedule_id
        return TaskContext(
            account=account,
            castle_roster_provider=castle_roster_provider or (lambda: None),
            defaults=self.defaults,
            step=step,
            params=parsed_params,
            flows=self.flow_planner,
            logger=logging.LoggerAdapter(self.logger.logger, extra=logger_extra),
            target_castle=target_castle,
            castle_roster_store=castle_roster_store,
            mail_archive_store=mail_archive_store,
            chat_archive_store=chat_archive_store,
            observation_service=self.observation_service,
            world_map_survey_recorder=self.world_map_survey_recorder,
            world_map_search_service=self.world_map_search_service,
        )

    def _raise_task_verification_error(
        self,
        message: str,
        *,
        task_id: TaskId,
        observation: Observation | None,
        screen_type: object | None,
        label: str,
        **details: object,
    ) -> None:
        """Raises one task verification error after forcing a persisted failure artifact when needed."""

        artifact_path = None if observation is None or observation.artifact_path is None else str(observation.artifact_path)
        if artifact_path is None:
            failure_observation = self._capture_failure_observation(label)
            if failure_observation is not None and failure_observation.artifact_path is not None:
                artifact_path = str(failure_observation.artifact_path)
        raise TaskVerificationError(
            message,
            task_id=task_id,
            screen_type=screen_type,
            artifact_path=artifact_path,
            **details,
        )

    def _capture_failure_observation(self, label: str) -> Observation | None:
        """Captures one persisted full-runtime failure observation when the current one was ephemeral."""

        try:
            return self.observation_service.observe(
                label,
                request=ObservationRequest.full_runtime_default(),
                artifact_selection=observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
            )
        except Exception:
            self.logger.exception("Failed to persist a debug artifact for task failure.")
            return None

