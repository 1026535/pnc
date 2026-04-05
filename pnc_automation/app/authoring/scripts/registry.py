"""Task registry for concrete automation task implementations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from pnc_automation.app.automation.engine.task import BaseAutomationTask, CastleTargetPolicy, TaskId
from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.app.automation.tasks.campaign_task import CampaignTask
from pnc_automation.app.automation.tasks.collect_kingdom_chat_task import CollectKingdomChatTask
from pnc_automation.app.automation.tasks.collect_mail_task import CollectMailTask
from pnc_automation.app.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.app.automation.tasks.gathering_task import GatheringTask
from pnc_automation.app.automation.tasks.login_task import LoginTask
from pnc_automation.app.automation.tasks.open_building_task import OpenBuildingTask
from pnc_automation.app.automation.tasks.popup_recovery_task import PopupRecoveryTask
from pnc_automation.app.automation.tasks.refresh_castle_roster_task import RefreshCastleRosterTask
from pnc_automation.app.automation.tasks.research_task import ResearchTask
from pnc_automation.app.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.app.automation.tasks.send_chat_message_task import (
    SendAllianceChatMessageTask,
    SendWorldChatMessageTask,
)
from pnc_automation.app.automation.tasks.send_mail_task import SendMailTask
from pnc_automation.app.authoring.config.models import AccountCastleTargetsConfig, CastleIdentity
from pnc_automation.core.errors import ConfigurationError, ScriptValidationError
from pnc_automation.app.authoring.scripts.models import (
    CastleRefRepeatBlock,
    PreparedRunScript,
    PreparedScriptStep,
    RunScript,
    ScriptNode,
    ScriptStep,
)

_UNRESOLVED_CASTLE: Final[object] = object()


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

        prepared_steps = self._prepare_script_nodes(script.steps, castle_targets=castle_targets)
        return PreparedRunScript(name=script.name, path=script.path, steps=tuple(prepared_steps))

    def _prepare_script_nodes(
        self,
        nodes: Sequence[ScriptNode],
        *,
        castle_targets: AccountCastleTargetsConfig | None,
    ) -> list[PreparedScriptStep]:
        """Flattens authored nodes into the canonical ordered prepared task-step list."""

        prepared_steps: list[PreparedScriptStep] = []
        for index, node in enumerate(nodes):
            prepared_steps.extend(
                self._prepare_script_node(
                    node,
                    step_index=index,
                    step_path=f"steps[{index}]",
                    castle_targets=castle_targets,
                )
            )
        return prepared_steps

    def _prepare_script_node(
        self,
        node: ScriptNode,
        *,
        step_index: int,
        step_path: str,
        castle_targets: AccountCastleTargetsConfig | None,
    ) -> list[PreparedScriptStep]:
        """Prepares one authored node or expands one repeat block into ordinary prepared steps."""

        if isinstance(node, ScriptStep):
            return [self._prepare_task_step(node, step_index=step_index, step_path=step_path, castle_targets=castle_targets)]
        if isinstance(node, CastleRefRepeatBlock):
            return self._prepare_repeat_block(
                node,
                step_index=step_index,
                step_path=step_path,
                castle_targets=castle_targets,
            )
        raise AssertionError(f"Unsupported script node type '{type(node).__name__}'.")

    def _prepare_repeat_block(
        self,
        block: CastleRefRepeatBlock,
        *,
        step_index: int,
        step_path: str,
        castle_targets: AccountCastleTargetsConfig | None,
    ) -> list[PreparedScriptStep]:
        """Expands one multi-castle workflow block into the canonical ordered prepared task steps."""

        prepared_steps: list[PreparedScriptStep] = []
        for castle_index, castle_ref in enumerate(block.castle_refs):
            resolved_castle = _resolve_castle_ref(
                castle_ref,
                step_index=step_index,
                step_path=f"{step_path}.castle_refs[{castle_index}]",
                castle_targets=castle_targets,
            )
            for nested_index, nested_step in enumerate(block.steps):
                if not isinstance(nested_step, ScriptStep):
                    raise ScriptValidationError(
                        "CastleRefRepeatBlock steps must contain only ScriptStep items.",
                        step_index=step_index,
                        step_path=f"{step_path}.steps[{nested_index}]",
                        nested_step_type=type(nested_step).__name__,
                    )
                if nested_step.castle is not None or nested_step.castle_ref is not None:
                    raise ScriptValidationError(
                        "Repeat-block nested task steps cannot define their own castle target; the repeat block owns castle targeting for its nested workflow.",
                        step_index=step_index,
                        step_path=f"{step_path}.steps[{nested_index}]",
                        task=nested_step.task,
                        castle=nested_step.castle,
                        castle_ref=nested_step.castle_ref,
                    )
                generated_step = nested_step.with_castle_ref(
                    castle_ref,
                    provenance={
                        **dict(block.provenance),
                        "step_path": f"{step_path}.steps[{nested_index}]",
                        "repeat_castle_ref": castle_ref,
                    },
                )
                prepared_steps.append(
                    self._prepare_task_step(
                        generated_step,
                        step_index=step_index,
                        step_path=f"{step_path}.steps[{nested_index}]",
                        castle_targets=castle_targets,
                        resolved_castle=resolved_castle,
                    )
                )
        return prepared_steps

    def _prepare_task_step(
        self,
        step: ScriptStep,
        *,
        step_index: int,
        step_path: str,
        castle_targets: AccountCastleTargetsConfig | None,
        resolved_castle: CastleIdentity | object = _UNRESOLVED_CASTLE,
    ) -> PreparedScriptStep:
        """Prepares one ordinary task step after validating task id, params, and castle targeting."""

        try:
            task = self.require(step.task)
        except KeyError as error:
            raise ScriptValidationError(
                f"Task '{step.task}' is not registered in the active task registry.",
                step_index=step_index,
                step_path=step_path,
                task=step.task,
            ) from error
        if resolved_castle is _UNRESOLVED_CASTLE:
            resolved_castle = _resolve_step_castle(
                step,
                step_index=step_index,
                step_path=step_path,
                castle_targets=castle_targets,
            )
        _validate_castle_target_policy(
            task,
            step_index=step_index,
            step_path=step_path,
            step=step,
            resolved_castle=resolved_castle,
        )
        try:
            parsed_params = task.parse_params(step.params)
        except ScriptValidationError as error:
            details = dict(error.details)
            details.setdefault("step_index", step_index)
            details.setdefault("step_path", step_path)
            details.setdefault("task", step.task)
            raise ScriptValidationError(error.message, **details) from error
        return PreparedScriptStep(
            script_step=step,
            parsed_params=parsed_params,
            castle_target_policy=task.castle_target_policy,
            resolved_castle=resolved_castle,
        )


def _resolve_step_castle(
    step: object,
    *,
    step_index: int,
    step_path: str,
    castle_targets: AccountCastleTargetsConfig | None,
) -> CastleIdentity | None:
    """Resolves one script step's authored castle target into a concrete castle identity."""

    target_castle = getattr(step, "castle", None)
    target_ref = getattr(step, "castle_ref", None)
    if target_castle is not None:
        return target_castle
    if target_ref is None:
        return None
    return _resolve_castle_ref(
        target_ref,
        step_index=step_index,
        step_path=step_path,
        castle_targets=castle_targets,
        task=getattr(step, "task", None),
    )


def _resolve_castle_ref(
    castle_ref: str,
    *,
    step_index: int,
    step_path: str,
    castle_targets: AccountCastleTargetsConfig | None,
    task: TaskId | None = None,
) -> CastleIdentity:
    """Resolves one authored castle alias into its concrete configured castle identity."""

    if castle_targets is None:
        raise ScriptValidationError(
            "This run script requires account-scoped castle targets, but none were loaded for the selected account.",
            step_index=step_index,
            step_path=step_path,
            task=task,
            castle_ref=castle_ref,
        )
    try:
        return castle_targets.require(castle_ref)
    except ConfigurationError as error:
        raise ScriptValidationError(
            f"Account '{castle_targets.account_id}' does not define castle target '{castle_ref}'.",
            step_index=step_index,
            step_path=step_path,
            task=task,
            castle_ref=castle_ref,
            account_id=castle_targets.account_id,
        ) from error


def _validate_castle_target_policy(
    task: BaseAutomationTask,
    *,
    step_index: int,
    step_path: str,
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
            step_path=step_path,
            task=task_id,
            castle=resolved_castle,
            castle_ref=target_ref,
        )
    if task.castle_target_policy == CastleTargetPolicy.REQUIRED and resolved_castle is None:
        raise ScriptValidationError(
            f"Task '{task.id}' requires a step-level castle target.",
            step_index=step_index,
            step_path=step_path,
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
            CollectKingdomChatTask(),
            OpenBuildingTask(),
            BuildingUpgradeTask(),
            ResearchTask(),
            GatheringTask(),
            CampaignTask(),
        )
    )
