"""Home city coordinate focus."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import SwipeAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityMapCoordinate,
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class HomeCityCoordinateFocusTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city coordinate focus."""

    def test_focus_home_city_coordinate_uses_inferred_atlas_center(self) -> None:
        """Moves the home-city camera toward one requested atlas coordinate from the inferred current center."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        viewport_offset_ratio=(-9 / 900, -375 / 1600),
                    ),
                ),
            ),
        )

        actions = self.flows.focus_home_city_coordinate(
            observation,
            HomeCityMapCoordinate(x=1500, y=1000),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "left")
        self.assertEqual(actions[0].reason, "focus_home_city_atlas_x")

    def test_focus_home_city_coordinate_precomputes_full_swipe_series_before_observing(self) -> None:
        """Plans the whole atlas route up front and only observes after the last swipe in the series."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        viewport_offset_ratio=(-9 / 900, -375 / 1600),
                    ),
                ),
            ),
        )

        actions = self.flows.focus_home_city_coordinate(
            observation,
            HomeCityMapCoordinate(x=2350, y=1000),
        )

        self.assertEqual(len(actions), 2)
        self.assertTrue(all(isinstance(action, SwipeAction) for action in actions))
        self.assertEqual(actions[0].direction, "left")
        self.assertEqual(actions[0].reason, "focus_home_city_atlas_x")
        self.assertFalse(actions[0].observe_after)
        self.assertEqual(actions[1].direction, "left")
        self.assertEqual(actions[1].reason, "focus_home_city_atlas_x")
        self.assertTrue(actions[1].observe_after)
        self.assertEqual(actions[1].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY))
        self.assertIsNotNone(actions[1].start_x_ratio)
        self.assertEqual(actions[1].start_y_ratio, 0.56)
        self.assertIsNotNone(actions[1].end_x_ratio)
        self.assertEqual(actions[1].end_y_ratio, 0.56)
