"""Connected-runtime adapter for Daily Quest navigation and observations."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, SwipeAction, TapAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.errors import SelectorResolutionError


@dataclass(slots=True)
class ConnectedDailyQuestSession:
    """Uses the canonical connected runner and executor for one castle's Daily screen."""

    runner: AutomationRunner
    observation_service: ObservationService
    action_executor: ObservedActionExecutor

    def open_daily_quest(self) -> None:
        """Reaches Daily Quest explicitly and proves its typed selected-tab state."""

        start = self._observe_with_update_recovery(
            "daily_open_start",
            request=ObservationRequest.full_runtime_default(),
        )
        if start.screen_type not in {
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_QUEST_MAIN,
            ScreenType.PNC_QUEST_DAILY,
        }:
            start = self.runner.execute_flow_until(
                label_prefix="daily_safe_home",
                planner=self.runner.flow_planner.ensure_home_city,
                done=lambda observation: observation.screen_type == ScreenType.PNC_HOME_CITY,
                start_observation=start,
                max_steps=8,
            )
        self.runner.execute_flow_until(
            label_prefix="daily_open",
            planner=self._plan_open_daily,
            done=lambda observation: observation.screen_type == ScreenType.PNC_QUEST_DAILY,
            start_observation=start,
            max_steps=4,
        )

    def observe_daily_quest(self, label: str) -> Observation:
        """Captures Daily Quest, reopening it after a recovered required update."""

        observation = self._observe_with_update_recovery(
            label,
            request=ObservationRequest.daily_quest_follow_up(),
        )
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            self.open_daily_quest()
            observation = self._observe_with_update_recovery(
                f"{label}_after_update",
                request=ObservationRequest.daily_quest_follow_up(),
            )
        return observation

    def scroll_daily_quest(self, *, adjusted: bool) -> None:
        """Performs one bounded normalized Daily-list scroll without observing implicitly."""

        action = SwipeAction(
            reason="daily_scroll_adjusted" if adjusted else "daily_scroll",
            start_x_ratio=0.5,
            start_y_ratio=0.82 if adjusted else 0.80,
            end_x_ratio=0.5,
            end_y_ratio=0.49 if adjusted else 0.44,
            duration_ms=420 if adjusted else 350,
        )
        before = self.observe_daily_quest("daily_scroll_source")
        self.action_executor.execute_action(action, before)

    def return_to_home(self) -> None:
        """Uses the in-game gold back control and requires typed Home."""

        start = self._observe_with_update_recovery(
            "daily_return_home_start",
            request=ObservationRequest.daily_quest_follow_up(),
        )
        self.runner.execute_flow_until(
            label_prefix="daily_return_home",
            planner=self.runner.flow_planner.ensure_home_city,
            done=lambda observation: observation.screen_type == ScreenType.PNC_HOME_CITY,
            start_observation=start,
            max_steps=4,
        )

    def _observe_with_update_recovery(
        self,
        label: str,
        *,
        request: ObservationRequest,
    ) -> Observation:
        """Captures one frame and globally recovers an exact required-update popup."""

        observation = self.observation_service.observe(label, request=request)
        if not observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON):
            return observation
        recovered = self.action_executor.recover_update_if_required(
            observation,
            label_prefix=f"{label}_update",
            observe=lambda follow_up_label, request=None: self.observation_service.observe(
                f"{label}_{follow_up_label}",
                request=request,
            ),
        )
        if recovered is None:
            raise AssertionError("Required-update recovery returned no observation for a detected Confirm control.")
        return recovered

    @staticmethod
    def _plan_open_daily(observation: Observation) -> list[ActionRequest]:
        """Returns the next explicit Home → Quest → Daily navigation action."""

        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            return [
                TapAction(
                    selector_id=UiElementId.PNC_BOTTOM_NAV_QUEST,
                    reason="open_quest",
                    observe_after=True,
                    follow_up_request=ObservationRequest.daily_quest_follow_up(),
                )
            ]
        if observation.screen_type == ScreenType.PNC_QUEST_MAIN:
            return [
                TapAction(
                    selector_id=UiElementId.PNC_QUEST_TAB_DAILY,
                    reason="select_daily_quest_tab",
                    observe_after=True,
                    follow_up_request=ObservationRequest.daily_quest_follow_up(),
                )
            ]
        if observation.screen_type == ScreenType.PNC_QUEST_DAILY:
            return []
        raise SelectorResolutionError(
            "Daily Quest navigation encountered an unexpected typed screen.",
            screen_type=observation.screen_type,
        )
