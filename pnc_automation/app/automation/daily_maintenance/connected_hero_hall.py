"""Connected runtime adapter for the Hero Hall free-single canary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import (
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.observation_builder import ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.errors import SelectorResolutionError


@dataclass(slots=True)
class ConnectedHeroHallSession:
    """Navigates to Hero Hall and dispatches only the observed free 1x action."""

    runner: AutomationRunner
    observation_service: ObservationService
    action_executor: ObservedActionExecutor
    flows: ScreenFlowPlanner
    daily_completion_probe: Callable[[], bool] | None = None
    _artifacts: list[str] = field(default_factory=list, init=False)
    _runtime_state: dict[str, object] = field(default_factory=dict, init=False)

    def open_hero_hall(self) -> None:
        """Reaches Hero Hall through the typed Home City building flow."""

        start = self.observe_hero_hall("hero_hall_open_start", allow_home=True)
        self.runner.execute_flow_until(
            label_prefix="hero_hall_open",
            planner=self._plan_open,
            done=lambda observation: observation.screen_type == ScreenType.PNC_HERO_HALL,
            start_observation=start,
            max_steps=self.flows.home_city_navigator.focus_step_budget() + 4,
        )

    def observe_hero_hall(self, label: str, *, allow_home: bool = False) -> Observation:
        """Captures typed Hero Hall evidence and delegates interruption recovery to the shared executor."""

        observation = self.observation_service.observe(
            label,
            request=(
                ObservationRequest.full_runtime_default()
                if allow_home
                else ObservationRequest.source_screen_retry(ScreenType.PNC_HERO_HALL)
            ),
        )
        self._remember_artifact(observation)
        recovered = self.action_executor.recover_interruption_if_required(
            observation,
            label_prefix=f"{label}_update",
            observe=lambda follow_up_label, request=None: self.observation_service.observe(
                f"{label}_{follow_up_label}", request=request,
            ),
        )
        if recovered is not None:
            observation = recovered
            self._remember_artifact(observation)
        if observation.screen_type == ScreenType.PNC_HERO_HALL:
            return observation
        if allow_home and observation.screen_type == ScreenType.PNC_HOME_CITY:
            return observation
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            self.open_hero_hall()
            observation = self.observation_service.observe(
                f"{label}_after_reopen",
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_HERO_HALL),
            )
            self._remember_artifact(observation)
            if observation.screen_type == ScreenType.PNC_HERO_HALL:
                return observation
        raise SelectorResolutionError(
            "Hero Hall canary encountered an unexpected typed screen.",
            screen_type=observation.screen_type,
        )

    def recruit_free_single(self) -> None:
        """Re-observes Hero Hall and taps the normalized free 1x region once."""

        observation = self.observe_hero_hall("hero_hall_recruit_dispatch")
        if not observation.has(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON):
            raise SelectorResolutionError(
                "Hero Hall did not expose the free 1x recruit control before dispatch.",
                selector_id=UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON,
            )
        self.action_executor.execute_action(
            TapAction(
                selector_id=UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON,
                reason="hero_hall_free_single",
            ),
            observation,
        )

    def daily_requirement_completed(self) -> bool:
        """Delegates final Daily proof to the caller-owned read-only Daily survey."""

        if self.daily_completion_probe is None:
            raise RuntimeError("Hero Hall finalization requires a read-only Daily completion probe.")
        return self.daily_completion_probe()

    def artifact_paths(self) -> tuple[str, ...]:
        """Returns all screenshots captured by this session."""

        return tuple(self._artifacts)

    def _plan_open(self, observation: Observation):
        """Plans one typed Home City increment toward Hero Hall."""

        if observation.screen_type == ScreenType.PNC_HERO_HALL:
            return []
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            query = SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value=HomeCityObjectId.HERO_HALL.value,
            )
            target = observation.find_spatial_object(query)
            if target is not None:
                return self.flows.open_visible_home_city_object(
                    observation,
                    target,
                    reason="open_hero_hall_visible_target",
                    runtime_state=self._runtime_state,
                    final_follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HERO_HALL),
                )
            return self.flows.focus_home_city_object(
                observation,
                query,
                runtime_state=self._runtime_state,
            )
        if observation.screen_type in {
            ScreenType.PNC_QUEST_DAILY,
            ScreenType.PNC_QUEST_MAIN,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_SETTINGS,
        }:
            return self.flows.ensure_home_city(observation)
        raise SelectorResolutionError(
            "Hero Hall navigation encountered an unexpected typed screen.",
            screen_type=observation.screen_type,
        )

    def _remember_artifact(self, observation: Observation) -> None:
        """Adds one observation artifact to the session evidence set."""

        if observation.artifact_path is not None:
            path = str(observation.artifact_path)
            if path not in self._artifacts:
                self._artifacts.append(path)
