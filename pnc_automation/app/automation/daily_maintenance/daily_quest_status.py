"""Read-only Daily Quest status workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.automation.daily_maintenance.coordinator import (
    DailyQuestViewport,
    daily_viewport_from_observation,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import TaskVerificationError


VISIBLE_VIEWPORT: Literal["visible_viewport"] = "visible_viewport"


@dataclass(frozen=True, slots=True)
class DailyQuestStatusResult:
    """Carries the typed visible Daily viewport and its capture evidence."""

    viewport: DailyQuestViewport
    captured_at: datetime
    coverage: Literal["visible_viewport"] = VISIBLE_VIEWPORT

    def __post_init__(self) -> None:
        """Keeps the result honest about its bounded viewport coverage."""

        if self.coverage != VISIBLE_VIEWPORT:
            raise ValueError("Daily Quest status coverage must be 'visible_viewport'.")


@dataclass(frozen=True, slots=True)
class DailyQuestStatusWorkflow(CoreWorkflow[DailyQuestStatusResult]):
    """Reads the currently visible Daily Quest rows without scrolling or mutation."""

    _spec: WorkflowSpec = WorkflowSpec(
        name="daily_quest_status",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.READ_ONLY,
    )

    @property
    def spec(self) -> WorkflowSpec:
        """Returns the fixed read-only Home-to-Home workflow contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> DailyQuestStatusResult:
        """Navigates to Daily, captures one fresh content frame, and converts its visible rows."""

        context.navigate(ScreenType.PNC_QUEST_DAILY)
        observation = context.observe_content(expected_screen=ScreenType.PNC_QUEST_DAILY)
        viewport = daily_viewport_from_observation(observation)
        if not viewport.rows and not viewport.unknown_titles:
            raise TaskVerificationError(
                "Daily Quest status found no recognized rows or unknown titles in the visible viewport.",
                artifact_path=viewport.artifact_path,
            )
        return DailyQuestStatusResult(
            viewport=viewport,
            captured_at=observation.captured_at,
        )
