"""Hero Hall device adapter used only inside the canonical mutation boundary."""

from collections.abc import Callable
from dataclasses import dataclass, field

from pnc_automation.app.automation.daily_maintenance.coordinator import DailyReadOnlySurvey
from pnc_automation.app.automation.daily_maintenance.hero_hall import HeroHallState, hero_hall_daily_completed
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


@dataclass(slots=True)
class CoreHeroHallSession:
    """Supply fresh guarded observations and one free dispatch to the existing executor."""

    runtime: CoreRuntime
    observe: Callable[[str], Observation]
    daily_survey: Callable[[], DailyReadOnlySurvey]
    _artifacts: list[str] = field(default_factory=list, init=False)
    _last_observation: Observation | None = field(default=None, init=False)
    _dispatch_source: Observation | None = field(default=None, init=False)
    _result_observations: list[Observation] = field(default_factory=list, init=False)

    def observe_hero_hall(self, label: str) -> Observation:
        """Retain the context's freshness and guard proof and its screenshot evidence."""

        dispatch_source, self._dispatch_source = self._dispatch_source, None
        frame = self.observe(label)
        self._retain(frame)
        if dispatch_source is not None and frame.screen_type in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
            # Only a locally proved dispatch can enter passive result settling.
            # A saved ambiguous receipt does not authorize a new input or retry.
            frame = self.runtime.navigation.confirm_content_after_action(
                frame, frozenset({ScreenType.PNC_HERO_HALL, ScreenType.PNC_HERO_RECRUIT_RESULT}),
                label, self.observe,
            )
            self._retain(frame)
        seen_phases = set()
        while frame.screen_type == ScreenType.PNC_HERO_RECRUIT_RESULT:
            result = frame.hero_recruit_result
            if result is None or result.phase in seen_phases:
                raise RuntimeError("Hero result phase is unproved or repeated; no acknowledgment replayed.")
            seen_phases.add(result.phase)
            frame = self.runtime.navigation.acknowledge_hero_recruit_result(
                frame, observe_content=self.observe,
            )
            self._retain(frame)
        HeroHallState.from_observation(frame)
        self._last_observation = frame
        return frame

    def _retain(self, frame: Observation) -> None:
        """Retain result facts and their artifact before any acknowledgment."""

        if frame.artifact_path is not None and str(frame.artifact_path) not in self._artifacts:
            self._artifacts.append(str(frame.artifact_path))
        if frame.hero_recruit_result is not None:
            self._result_observations.append(frame)

    @property
    def result_observations(self) -> tuple[Observation, ...]:
        """Expose the measured result chain without interpreting it as a receipt."""

        return tuple(self._result_observations)

    def recruit_free_single(self) -> None:
        """Reacquire the distinct free control after the journal records dispatch intent."""

        if self._last_observation is None:
            raise RuntimeError("Hero Hall requires an observed precondition before dispatch.")
        expected = HeroHallState.from_observation(self._last_observation)
        frame = self.observe_hero_hall("hero_hall_dispatch")
        state = HeroHallState.from_observation(frame)
        if (
            not state.free_single_available or not state.daily_attempts_remaining
            or state.daily_attempts_remaining != expected.daily_attempts_remaining
        ):
            raise RuntimeError("Hero Hall lost its free control or positive attempts; no tap sent.")
        executor = self.runtime.runtime.require_observed_action_executor(
            "Hero Hall requires the canonical observed action executor."
        )
        if not executor.execute_action(
            TapAction(
                selector_id=UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON,
                reason="hero_hall_free_single",
            ), frame,
        ):
            raise RuntimeError("Hero Hall free single was not executed; its intent prevents replay.")
        self._dispatch_source = frame

    def daily_requirement_completed(self) -> bool:
        """Keep the existing complete read-only Daily survey as the final proof."""

        survey = self.daily_survey()
        self._artifacts.extend(path for path in survey.artifact_paths if path not in self._artifacts)
        return hero_hall_daily_completed(survey)

    def artifact_paths(self) -> tuple[str, ...]:
        """Return only evidence actually collected by this increment."""

        return tuple(self._artifacts)
