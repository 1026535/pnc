"""Shared core recording doubles and fixtures."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.navigation.core_frames import Actuator, observation


class RecordedFramesCore:
    def make_core(self, frames):
        actuator = Actuator()
        now = datetime.now(UTC)
        iterator = iter(replace(frame, captured_at=now + timedelta(seconds=index)) for index, frame in enumerate(frames))
        core = NavigationCore(actuator, lambda _: next(iterator), reviewed_navigation_edges(),
                              NavigationPolicy(max_observations=4), sleep=lambda _: None)
        return core, actuator, core.edges[0]


class RecordingNavigationCore:
    """Construct the non-spending navigation core for typed content tests."""

    def make_core(self, actuator=None):
        return NavigationCore(
            actuator or Actuator(),
            lambda _: observation(ScreenType.PNC_HOME_CITY),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
