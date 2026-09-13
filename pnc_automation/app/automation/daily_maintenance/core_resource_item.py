"""Typed Resource Item workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcome,
    DailyTaskCheckpoint,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType


@dataclass(frozen=True, slots=True)
class CoreResourceItemWorkflow(CoreWorkflow[tuple[DailyTaskCheckpoint, DailyTargetOutcome]]):
    """Delegate one authorized canonical Resource Item execution."""

    checkpoint: DailyTaskCheckpoint
    allow_empty_skip: bool = False

    _spec: ClassVar[WorkflowSpec] = WorkflowSpec(
        name="resource_item",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.RESOURCE_CHANGING,
        mutation_capability=DailyQuestId.USE_RESOURCE_ITEM,
    )

    def __post_init__(self) -> None:
        """Reject malformed workflow parameters before navigation or mutation."""

        if not isinstance(self.checkpoint, DailyTaskCheckpoint):
            raise TypeError("CoreResourceItemWorkflow requires a DailyTaskCheckpoint.")
        if not isinstance(self.allow_empty_skip, bool):
            raise TypeError("CoreResourceItemWorkflow.allow_empty_skip must be a bool.")

    @property
    def spec(self) -> WorkflowSpec:
        """Return the fixed resource-changing Home-to-Home contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Delegate exactly one authorized Resource Item operation to the context."""

        checkpoint, outcome = context.use_resource_item(
            self.checkpoint,
            allow_empty_skip=self.allow_empty_skip,
        )
        if outcome.quest_id != DailyQuestId.USE_RESOURCE_ITEM:
            raise ValueError("WorkflowContext.use_resource_item returned an unrelated mutation outcome.")
        return checkpoint, outcome
