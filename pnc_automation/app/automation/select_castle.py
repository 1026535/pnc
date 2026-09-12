"""Typed castle selection workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    CurrentCastleMatchStatus,
    resolve_current_castle_match,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType


@dataclass(frozen=True, slots=True)
class SelectCastleResult:
    """Reports the original and exactly revalidated selected castle identities."""

    original_castle: CastleIdentity
    selected_castle: CastleIdentity
    switched: bool
    captured_at: datetime
    artifact_path: str | None

    def __post_init__(self) -> None:
        """Reject incomplete selection proof metadata."""

        if not isinstance(self.original_castle, CastleIdentity):
            raise TypeError("SelectCastleResult.original_castle must be a CastleIdentity.")
        if not isinstance(self.selected_castle, CastleIdentity):
            raise TypeError("SelectCastleResult.selected_castle must be a CastleIdentity.")
        if type(self.switched) is not bool:
            raise TypeError("SelectCastleResult.switched must be a bool.")
        if not isinstance(self.captured_at, datetime):
            raise TypeError("SelectCastleResult.captured_at must be a datetime.")
        if self.artifact_path is not None and not isinstance(self.artifact_path, str):
            raise TypeError("SelectCastleResult.artifact_path must be a string or None.")


@dataclass(frozen=True, slots=True)
class SelectCastleWorkflow(CoreWorkflow[SelectCastleResult]):
    """Selects one exact castle row and proves the resulting active identity."""

    original_castle: CastleIdentity
    target_castle: CastleIdentity

    @property
    def spec(self) -> WorkflowSpec:
        """Return the non-spending Home-to-Home selection contract."""

        return WorkflowSpec(
            name="select_castle",
            entry_screen=ScreenType.PNC_HOME_CITY,
            exit_screen=ScreenType.PNC_HOME_CITY,
            effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
        )

    def __post_init__(self) -> None:
        """Reject missing typed identities before any workflow navigation."""

        if not isinstance(self.original_castle, CastleIdentity):
            raise TypeError("SelectCastleWorkflow.original_castle must be a CastleIdentity.")
        if not isinstance(self.target_castle, CastleIdentity):
            raise TypeError("SelectCastleWorkflow.target_castle must be a CastleIdentity.")

    def execute(self, context: WorkflowContext) -> SelectCastleResult:
        """Enter Manage Characters, select once when needed, and revalidate exact identity."""

        context.navigate(ScreenType.PNC_CASTLE_SELECTION)
        selection = context.select_castle(self.target_castle)
        selected_castle = context.verify_active_castle_identity(self.target_castle)
        match = resolve_current_castle_match(
            current_castle=self.original_castle,
            evidence_kind=CurrentCastleEvidenceKind.EXACT,
            target=self.target_castle,
            roster=None,
        )
        return SelectCastleResult(
            original_castle=self.original_castle,
            selected_castle=selected_castle,
            switched=match.status != CurrentCastleMatchStatus.MATCH,
            captured_at=selection.captured_at,
            artifact_path=None if selection.artifact_path is None else str(selection.artifact_path),
        )
