"""Core runtime adapter for the canonical one-resource-item executor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pnc_automation.app.automation.daily_maintenance.coordinator import DailyReadOnlySurvey
from pnc_automation.app.automation.daily_maintenance.resource_inventory_session import (
    ResourceInventorySession,
)
from pnc_automation.app.automation.daily_maintenance.resource_item import resource_item_daily_completed
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.pnc.domain.action_requests import TapListEntryAction
from pnc_automation.app.pnc.domain.observation import Observation


@dataclass(slots=True)
class CoreResourceItemSession(ResourceInventorySession):
    """Supply typed core hooks to the existing Resource Item executor."""

    runtime: CoreRuntime
    observe: Callable[[str], Observation]
    open_inventory: Callable[[], None]
    daily_survey: Callable[[], DailyReadOnlySurvey]
    max_viewports: int = 40
    _artifacts: list[str] = field(default_factory=list, init=False)

    def _execute_single_use(self, action: TapListEntryAction, observation: Observation) -> bool:
        """Dispatch the shared single-row action through the runtime's observed executor."""

        action_executor = self.runtime.runtime.require_observed_action_executor(
            "Core Resource Item use requires the canonical observed action executor."
        )
        return action_executor.execute_action(action, observation)

    def daily_requirement_completed(self) -> bool:
        """Use the shared read-only Daily survey to prove resource-use completion."""

        survey = self.daily_survey()
        self._artifacts.extend(path for path in survey.artifact_paths if path not in self._artifacts)
        return resource_item_daily_completed(survey)

    def artifact_paths(self) -> tuple[str, ...]:
        """Return captured inventory, mutation, and Daily evidence in order."""

        return tuple(self._artifacts)

    def _open_inventory(self) -> None:
        """Delegate Resource navigation to the constrained workflow context."""

        self.open_inventory()

    def _observe(self, label: str) -> Observation:
        """Delegate fresh guarded Bag observation and retain its artifact evidence."""

        observation = self.observe(label)
        if observation.artifact_path is not None:
            path = str(observation.artifact_path)
            if path not in self._artifacts:
                self._artifacts.append(path)
        return observation

    def _scroll(
        self,
        before: Observation,
        *,
        upward: bool,
        adjusted: bool,
        fine: bool = False,
    ) -> Observation:
        """Delegate one bounded Resource swipe and canonical stable completion."""

        return self.runtime.navigation.scroll_resource_inventory(
            upward=upward,
            adjusted=adjusted,
            fine=fine,
            observe_content=self._observe,
            confirm_scroll=lambda: self._stable("resource_scroll"),
        )
