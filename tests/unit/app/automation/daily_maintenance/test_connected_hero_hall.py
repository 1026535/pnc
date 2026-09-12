"""Offline tests for direct Home City Hero Hall entry."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.connected_hero_hall import (
    ConnectedHeroHallSession,
)
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface


class ConnectedHeroHallEntryTests(unittest.TestCase):
    """Protects the Hero Hall canary from regressing to Daily-Go navigation."""

    def setUp(self) -> None:
        """Builds a session with a mocked shared Home City flow planner."""

        self.flows = Mock()
        self.session = ConnectedHeroHallSession(
            runner=Mock(),
            observation_service=Mock(),
            action_executor=Mock(),
            flows=self.flows,
        )

    def test_visible_hero_hall_uses_exact_home_city_object_tap(self) -> None:
        """Taps the observed Hero Hall object and never asks a Daily flow for entry."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hero Hall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HERO_HALL),
                        action_point=(91, 37),
                    ),
                ),
            ),
        )
        planned = [TapSpatialObjectAction(reason="test_hero_hall_tap", target_point=(91, 37))]
        self.flows.open_visible_home_city_object.return_value = planned

        actions = self.session._plan_open(observation)

        self.assertEqual(planned, actions)
        self.flows.open_visible_home_city_object.assert_called_once()
        self.flows.focus_home_city_object.assert_not_called()

    def test_missing_hero_hall_requests_home_city_focus_only(self) -> None:
        """Focuses the camera when Hero Hall is not visible instead of using a blind tap."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
        )
        planned = [SwipeAction(direction="left", reason="focus_hero_hall")]
        self.flows.focus_home_city_object.return_value = planned

        actions = self.session._plan_open(observation)

        self.assertEqual(planned, actions)
        self.flows.focus_home_city_object.assert_called_once()
        self.flows.open_visible_home_city_object.assert_not_called()


if __name__ == "__main__":
    unittest.main()
