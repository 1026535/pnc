"""Canonical connected Bag adapter for the one-resource-item feature."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnc_automation.app.automation.daily_maintenance.coordinator import DailyMaintenanceCoordinator
from pnc_automation.app.automation.daily_maintenance.resource_inventory_session import ResourceInventorySession
from pnc_automation.app.automation.daily_maintenance.resource_item import resource_item_daily_completed
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapAction, TapListEntryAction
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.observation_builder import ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest


@dataclass(slots=True)
class ConnectedResourceItemSession(ResourceInventorySession):
    """Scans Resource inventory and uses only fresh visual single-Use row targets."""

    observation_service: ObservationService
    action_executor: ObservedActionExecutor
    flows: ScreenFlowPlanner
    daily_coordinator: DailyMaintenanceCoordinator
    max_viewports: int = 40
    _artifacts: list[str] = field(default_factory=list, init=False)

    def _execute_single_use(self, action: TapListEntryAction, observation: Observation) -> bool:
        """Use the connected observed executor without duplicating row selection."""

        return self.action_executor.execute_action(action, observation)

    def daily_requirement_completed(self) -> bool:
        """Uses the shared read-only Daily sweep to prove resource-use completion."""

        survey = self.daily_coordinator.survey_read_only()
        self._artifacts.extend(path for path in survey.artifact_paths if path not in self._artifacts)
        return resource_item_daily_completed(survey)

    def artifact_paths(self) -> tuple[str, ...]:
        """Returns all captured scan and mutation evidence in observation order."""

        return tuple(self._artifacts)

    def _open_inventory(self) -> None:
        """Uses typed navigation only, rejecting generic recovery and Android Back."""

        for index in range(8):
            current = self._observe_with_update_recovery(f"resource_open_{index}")
            if current.screen_type == ScreenType.PNC_BAG:
                if (
                    current.entries(ListEntryKind.RESOURCE_ITEM)
                    or current.entries(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION)
                    or current.entries(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED)
                ):
                    return
                action = TapAction(
                    selector_id=UiElementId.PNC_BAG_SUBTAB_RESOURCE,
                    reason="select_resource_tab", observe_after=True,
                )
            elif current.screen_type == ScreenType.PNC_HOME_CITY:
                action = TapAction(
                    selector_id=UiElementId.PNC_BOTTOM_NAV_BAG,
                    reason="open_resource_inventory", observe_after=True,
                )
            elif current.screen_type in {
                ScreenType.PNC_MORE_MENU,
                ScreenType.PNC_SETTINGS,
                ScreenType.PNC_CASTLE_SELECTION,
                ScreenType.PNC_QUEST_DAILY,
            }:
                actions = self.flows.ensure_home_city(current)
                if len(actions) != 1 or not isinstance(actions[0], TapAction):
                    raise ValueError("Resource navigation requires a typed in-game back control.")
                action = actions[0]
                if action.selector_id not in {
                    UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_BOTTOM_NAV_MORE,
                }:
                    raise ValueError("Resource navigation rejected an unrelated action.")
            else:
                raise ValueError("Resource inventory navigation encountered an unexpected screen.")
            self.action_executor.execute_actions(
                (action,), current,
                observe=lambda label, request=None: self.observation_service.observe(
                    f"resource_open_{index}_{label}", request=request,
                ),
            )
        raise ValueError("Resource inventory navigation exceeded its action budget.")

    def _observe(self, label: str) -> Observation:
        """Requires Bag, reopening it after a recovered required update."""

        observation = self._observe_with_update_recovery(
            label, request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
        )
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            self._open_inventory()
            observation = self._observe_with_update_recovery(
                f"{label}_after_update",
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
            )
        if observation.screen_type != ScreenType.PNC_BAG or observation.blocking_popup:
            raise ValueError("Expected typed Resource Bag, not an unknown screen or popup.")
        if observation.artifact_path is not None:
            path = str(observation.artifact_path)
            if path not in self._artifacts:
                self._artifacts.append(path)
        return observation

    def _observe_with_update_recovery(
        self,
        label: str,
        request: ObservationRequest | None = None,
    ) -> Observation:
        """Captures one frame and delegates interruption recovery to the shared executor."""

        observation = self.observation_service.observe(label, request=request)
        recovered = self.action_executor.recover_interruption_if_required(
            observation,
            label_prefix=f"{label}_update",
            observe=lambda follow_up_label, request=None: self.observation_service.observe(
                f"{label}_{follow_up_label}",
                request=request,
            ),
        )
        if recovered is None:
            return observation
        return recovered

    def _scroll(
        self,
        before: Observation,
        *,
        upward: bool,
        adjusted: bool,
        fine: bool = False,
    ) -> Observation:
        """Performs one bounded normalized list swipe through the canonical executor."""

        low = 0.64 if fine else (0.78 if adjusted else 0.85)
        high = 0.46 if fine else (0.42 if adjusted else 0.32)
        self.action_executor.execute_action(
            SwipeAction(
                reason=(
                    "resource_inventory_focus_scroll"
                    if fine
                    else "resource_inventory_scroll_adjusted"
                    if adjusted
                    else "resource_inventory_scroll"
                ),
                start_x_ratio=0.5, end_x_ratio=0.5,
                start_y_ratio=high if upward else low,
                end_y_ratio=low if upward else high,
                duration_ms=420 if adjusted else 350,
            ),
            before,
        )
        return self._stable("resource_scroll")
