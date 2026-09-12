"""Typed authored-script dispatch on the replacement navigation core."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from pnc_automation.app.automation.collect_kingdom_chat import (
    CollectKingdomChatResult,
    CollectKingdomChatWorkflow,
)
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult, CoreWorkflowRunner
from pnc_automation.app.authoring.config.models import AccountConfig, LiveAutomationRole
from pnc_automation.app.authoring.scripts.models import PreparedScriptStep
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    CurrentCastleMatchStatus,
    resolve_current_castle_match,
)
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.automation.engine.task import TaskId


@dataclass(slots=True)
class CoreScriptDispatcher:
    """Executes typed script steps over one caller-owned connected runtime graph."""

    account: AccountConfig
    chat_archive_store: ChatArchiveStore | None
    core_runtime_factory: Callable[[], CoreRuntime]
    required_role: LiveAutomationRole = LiveAutomationRole.LIVE_TESTING
    _core_runtime: CoreRuntime | None = field(default=None, init=False, repr=False)
    _workflow_runner: CoreWorkflowRunner[Any] | None = field(default=None, init=False, repr=False)

    def execute(self, *, step: PreparedScriptStep) -> CoreWorkflowResult[CollectKingdomChatResult]:
        """Runs one supported typed step without closing the shared connected runtime."""

        self._validate_step(step)
        archive_store = cast(ChatArchiveStore, self.chat_archive_store)
        core_runtime = self._require_core_runtime()
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
                    "Typed Kingdom Chat dispatch preflight did not confirm the requested castle target."
                )
        workflow = CollectKingdomChatWorkflow(
            account_id=self.account.id,
            active_castle=active_castle,
            archive_store=archive_store,
        )
        runner = self._workflow_runner
        if runner is None:
            runner = CoreWorkflowRunner(core_runtime)
            self._workflow_runner = runner
        return runner.run(workflow)

    def _validate_step(self, step: PreparedScriptStep) -> None:
        """Rejects unsupported definitions and malformed parsed parameters before navigation."""

        validate_core_script_step(step, chat_archive_store=self.chat_archive_store)
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
    chat_archive_store: ChatArchiveStore | None,
) -> None:
    """Validates the supported typed Chat binding before connect and before navigation."""

    if step.task != TaskId.COLLECT_KINGDOM_CHAT:
        raise RuntimeError(f"No typed core dispatcher is registered for task '{step.task}'.")
    if step.parsed_params is not None:
        raise RuntimeError("Typed Kingdom Chat dispatch requires parameterless parsed parameters.")
    if not isinstance(chat_archive_store, ChatArchiveStore):
        raise RuntimeError(
            "Kingdom Chat typed dispatch requires a configured ChatArchiveStore before navigation."
        )
