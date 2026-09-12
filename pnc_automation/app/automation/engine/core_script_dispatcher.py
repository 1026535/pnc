"""Typed authored-script dispatch on the replacement navigation core."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pnc_automation.app.automation.collect_kingdom_chat import (
    CollectKingdomChatResult,
    CollectKingdomChatWorkflow,
)
from pnc_automation.app.automation.collect_mail import CollectMailResult, CollectMailWorkflow
from pnc_automation.app.automation.refresh_castle_roster import (
    RefreshCastleRosterResult,
    RefreshCastleRosterWorkflow,
)
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflowResult,
    CoreWorkflowRunner,
    WorkflowEffect,
)
from pnc_automation.app.authoring.config.models import AccountConfig, LiveAutomationRole
from pnc_automation.app.authoring.scripts.models import PreparedScriptStep
from pnc_automation.app.pnc.domain.mail import CollectMailParams
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    CurrentCastleMatchStatus,
    resolve_current_castle_match,
)
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.pnc.enums.screen_type import ScreenType


@dataclass(frozen=True, slots=True)
class GameReadyResult:
    """Captures the stable in-game endpoint proved by lifecycle preflight."""

    screen_type: ScreenType
    captured_at: datetime
    artifact_path: Path | None


@dataclass(slots=True)
class CoreScriptDispatcher:
    """Executes typed script steps over one caller-owned connected runtime graph."""

    account: AccountConfig
    chat_archive_store: ChatArchiveStore | None
    core_runtime_factory: Callable[[], CoreRuntime]
    mail_archive_store: MailArchiveStore | None = None
    castle_roster_store: CastleRosterStore | None = None
    required_role: LiveAutomationRole = LiveAutomationRole.LIVE_TESTING
    _core_runtime: CoreRuntime | None = field(default=None, init=False, repr=False)
    _workflow_runner: CoreWorkflowRunner[Any] | None = field(default=None, init=False, repr=False)

    def execute(
        self,
        *,
        step: PreparedScriptStep,
    ) -> CoreWorkflowResult[GameReadyResult | CollectKingdomChatResult | CollectMailResult | RefreshCastleRosterResult]:
        """Runs one supported typed step without closing the shared connected runtime."""

        self._validate_step(step)
        core_runtime = self._require_core_runtime()
        if step.task == TaskId.ENSURE_GAME_RUNNING:
            return self._execute_game_ready(core_runtime)
        active_castle = core_runtime.preflight_active_castle_identity()
        if step.castle is not None:
            match = resolve_current_castle_match(
                current_castle=active_castle,
                evidence_kind=CurrentCastleEvidenceKind.EXACT,
                target=step.castle,
                roster=None,
            )
            if match.status != CurrentCastleMatchStatus.MATCH:
                raise RuntimeError(
                    f"Typed '{step.task}' dispatch preflight did not confirm the requested castle target."
                )
        if step.task == TaskId.COLLECT_KINGDOM_CHAT:
            workflow = CollectKingdomChatWorkflow(
                account_id=self.account.id,
                active_castle=active_castle,
                archive_store=cast(ChatArchiveStore, self.chat_archive_store),
            )
        elif step.task == TaskId.COLLECT_MAIL:
            workflow = CollectMailWorkflow(
                params=cast(CollectMailParams, step.parsed_params),
                account_id=self.account.id,
                pnc_account_id=self.account.pnc_account_id,
                active_castle=active_castle.castle_name,
                archive_store=cast(MailArchiveStore, self.mail_archive_store),
            )
        elif step.task == TaskId.REFRESH_CASTLE_ROSTER:
            workflow = RefreshCastleRosterWorkflow(
                account_id=self.account.id,
                pnc_account_id=self.account.pnc_account_id,
                active_castle=active_castle,
                roster_store=cast(CastleRosterStore, self.castle_roster_store),
            )
        else:
            raise RuntimeError(f"No typed core dispatcher is registered for task '{step.task}'.")
        runner = self._workflow_runner
        if runner is None:
            runner = CoreWorkflowRunner(core_runtime)
            self._workflow_runner = runner
        return runner.run(workflow)

    def _execute_game_ready(self, core_runtime: CoreRuntime) -> CoreWorkflowResult[GameReadyResult]:
        """Runs lifecycle readiness without castle identity or workflow navigation."""

        core_runtime.record(
            {
                "event": "workflow_started",
                "workflow": TaskId.ENSURE_GAME_RUNNING.value,
                "effect": WorkflowEffect.READ_ONLY.value,
            }
        )
        try:
            observation = core_runtime.ensure_game_ready()
            result = CoreWorkflowResult(
                workflow_name=TaskId.ENSURE_GAME_RUNNING.value,
                succeeded=True,
                value=GameReadyResult(
                    screen_type=observation.screen_type,
                    captured_at=observation.captured_at,
                    artifact_path=observation.artifact_path,
                ),
                exit_screen=observation.screen_type,
                trace_path=str(core_runtime.trace_path),
            )
            core_runtime.record(
                {
                    "event": "workflow_succeeded",
                    "workflow": TaskId.ENSURE_GAME_RUNNING.value,
                    "screen": observation.screen_type.name,
                }
            )
            return result
        except Exception as error:
            core_runtime.record(
                {
                    "event": "workflow_failed",
                    "workflow": TaskId.ENSURE_GAME_RUNNING.value,
                    "error_type": type(error).__name__,
                }
            )
            raise

    def _validate_step(self, step: PreparedScriptStep) -> None:
        """Rejects unsupported definitions and malformed parsed parameters before navigation."""

        validate_core_script_step(
            step,
            chat_archive_store=self.chat_archive_store,
            mail_archive_store=self.mail_archive_store,
            castle_roster_store=self.castle_roster_store,
        )
        if not isinstance(self.account, AccountConfig):
            raise TypeError("Typed core dispatch requires a configured AccountConfig binding.")
        self.account.require_live_role(self.required_role)

    def _require_core_runtime(self) -> CoreRuntime:
        """Lazily composes one core runtime over the existing connected services."""

        if self._core_runtime is None:
            self._core_runtime = self.core_runtime_factory()
        return self._core_runtime


def validate_core_script_step(
    step: PreparedScriptStep,
    *,
    chat_archive_store: ChatArchiveStore | None = None,
    mail_archive_store: MailArchiveStore | None = None,
    castle_roster_store: CastleRosterStore | None = None,
) -> None:
    """Validates one supported typed binding before connect and before navigation."""

    if step.task == TaskId.ENSURE_GAME_RUNNING:
        if step.parsed_params is not None:
            raise RuntimeError("Typed Ensure Game Running dispatch requires parameterless parsed parameters.")
        return
    if step.task not in {
        TaskId.COLLECT_KINGDOM_CHAT,
        TaskId.COLLECT_MAIL,
        TaskId.REFRESH_CASTLE_ROSTER,
    }:
        raise RuntimeError(f"No typed core dispatcher is registered for task '{step.task}'.")
    if step.task == TaskId.COLLECT_KINGDOM_CHAT:
        if step.parsed_params is not None:
            raise RuntimeError("Typed Kingdom Chat dispatch requires parameterless parsed parameters.")
        if not isinstance(chat_archive_store, ChatArchiveStore):
            raise RuntimeError(
                "Kingdom Chat typed dispatch requires a configured ChatArchiveStore before navigation."
            )
        return
    if step.task == TaskId.COLLECT_MAIL:
        if not isinstance(step.parsed_params, CollectMailParams):
            raise RuntimeError("Typed Collect Mail dispatch requires parsed CollectMailParams.")
        if not isinstance(mail_archive_store, MailArchiveStore):
            raise RuntimeError(
                "Collect Mail typed dispatch requires a configured MailArchiveStore before navigation."
            )
        return
    if step.parsed_params is not None:
        raise RuntimeError("Typed castle-roster refresh dispatch requires parameterless parsed parameters.")
    if not isinstance(castle_roster_store, CastleRosterStore):
        raise RuntimeError(
            "Castle roster typed dispatch requires a configured CastleRosterStore before navigation."
        )
