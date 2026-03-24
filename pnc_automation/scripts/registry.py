"""Task registry for concrete automation task implementations."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnc_automation.automation.task import BaseAutomationTask, CastleTargetPolicy, TaskId
from pnc_automation.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.automation.tasks.campaign_task import CampaignTask
from pnc_automation.automation.tasks.collect_mail_task import CollectMailTask
from pnc_automation.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.automation.tasks.gathering_task import GatheringTask
from pnc_automation.automation.tasks.login_task import LoginTask
from pnc_automation.automation.tasks.popup_recovery_task import PopupRecoveryTask
from pnc_automation.automation.tasks.refresh_castle_roster_task import RefreshCastleRosterTask
from pnc_automation.automation.tasks.research_task import ResearchTask
from pnc_automation.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.automation.tasks.send_chat_message_task import (
    SendAllianceChatMessageTask,
    SendWorldChatMessageTask,
)
from pnc_automation.automation.tasks.send_mail_task import SendMailTask
from pnc_automation.config.models import AccountCastleTargetsConfig, CastleIdentity
from pnc_automation.errors import ConfigurationError, ScriptValidationError
from pnc_automation.scripts.models import PreparedRunScript, PreparedScriptStep, RunScript


@dataclass(frozen=True, slots=True)
class TaskRegistry:
    """Owns concrete task lookup by canonical task id."""

    tasks: tuple[BaseAutomationTask, ...]
    _tasks_by_id: dict[TaskId, BaseAutomationTask] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Builds the canonical task lookup table and rejects duplicate ids."""

        tasks_by_id: dict[TaskId, BaseAutomationTask] = {}
        duplicates: list[TaskId] = []
        for task in self.tasks:
            if task.id in tasks_by_id:
                duplicates.append(task.id)
                continue
            tasks_by_id[task.id] = task
        if duplicates:
            duplicate_labels = ", ".join(str(task_id) for task_id in duplicates)
            raise ValueError(f"TaskRegistry received duplicate task ids: {duplicate_labels}.")
        object.__setattr__(self, "_tasks_by_id", tasks_by_id)

    def require(self, task_id: TaskId) -> BaseAutomationTask:
        """Returns a registered task or fails fast."""

        try:
            return self._tasks_by_id[task_id]
        except KeyError as error:
            raise KeyError(f"Task '{task_id}' is not registered.") from error

    def prepare_script(
        self,
        script: RunScript,
        *,
        castle_targets: AccountCastleTargetsConfig | None = None,
    ) -> PreparedRunScript:
        """Converts a raw run script into an execution-ready script with typed params."""

        prepared_steps: list[PreparedScriptStep] = []
        for index, step in enumerate(script.steps):
            try:
                task = self.require(step.task)
            except KeyError as error:
                raise ScriptValidationError(
                    f"Task '{step.task}' is not registered in the active task registry.",
                    step_index=index,
                    task=step.task,
                ) from error
            resolved_castle = _resolve_step_castle(
                step,
                step_index=index,
                castle_targets=castle_targets,
            )
            _validate_castle_target_policy(task, step_index=index, step=step, resolved_castle=resolved_castle)
            try:
                parsed_params = task.parse_params(step.params)
            except ScriptValidationError as error:
                details = dict(error.details)
                details.setdefault("step_index", index)
                details.setdefault("task", step.task)
                raise ScriptValidationError(error.message, **details) from error
            prepared_steps.append(
                PreparedScriptStep(
                    script_step=step,
                    parsed_params=parsed_params,
                    castle_target_policy=task.castle_target_policy,
                    resolved_castle=resolved_castle,
                )
            )
        return PreparedRunScript(name=script.name, path=script.path, steps=tuple(prepared_steps))


def _resolve_step_castle(
    step: object,
    *,
    step_index: int,
    castle_targets: AccountCastleTargetsConfig | None,
) -> CastleIdentity | None:
    """Resolves one script step's authored castle target into a concrete castle identity."""

    target_castle = getattr(step, "castle", None)
    target_ref = getattr(step, "castle_ref", None)
    if target_castle is not None:
        return target_castle
    if target_ref is None:
        return None
    if castle_targets is None:
        raise ScriptValidationError(
            "This run script requires account-scoped castle targets, but none were loaded for the selected account.",
            step_index=step_index,
            task=getattr(step, "task", None),
            castle_ref=target_ref,
        )
    try:
        return castle_targets.require(target_ref)
    except ConfigurationError as error:
        raise ScriptValidationError(
            f"Account '{castle_targets.account_id}' does not define castle target '{target_ref}'.",
            step_index=step_index,
            task=getattr(step, "task", None),
            castle_ref=target_ref,
            account_id=castle_targets.account_id,
        ) from error


def _validate_castle_target_policy(
    task: BaseAutomationTask,
    *,
    step_index: int,
    step: object,
    resolved_castle: CastleIdentity | None,
) -> None:
    """Rejects script steps whose castle targeting does not match the task contract."""

    task_id = getattr(step, "task", None)
    target_ref = getattr(step, "castle_ref", None)
    if task.castle_target_policy == CastleTargetPolicy.DISALLOWED and resolved_castle is not None:
        raise ScriptValidationError(
            f"Task '{task.id}' does not accept a step-level castle target.",
            step_index=step_index,
            task=task_id,
            castle=resolved_castle,
            castle_ref=target_ref,
        )
    if task.castle_target_policy == CastleTargetPolicy.REQUIRED and resolved_castle is None:
        raise ScriptValidationError(
            f"Task '{task.id}' requires a step-level castle target.",
            step_index=step_index,
            task=task_id,
            castle_ref=target_ref,
        )


def build_default_task_registry() -> TaskRegistry:
    """Builds the default concrete task registry for the platform."""

    return TaskRegistry(
        tasks=(
            EnsureGameRunningTask(),
            PopupRecoveryTask(),
            LoginTask(),
            SelectCastleTask(),
            RefreshCastleRosterTask(),
            SendAllianceChatMessageTask(),
            SendWorldChatMessageTask(),
            SendMailTask(),
            CollectMailTask(),
            BuildingUpgradeTask(),
            ResearchTask(),
            GatheringTask(),
            CampaignTask(),
        )
    )
