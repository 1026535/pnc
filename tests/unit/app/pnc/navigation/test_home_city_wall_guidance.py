"""Home city wall guidance."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import SwipeAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class HomeCityWallGuidanceTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city wall guidance."""

    def test_open_home_city_object_guides_wall_search_from_castle_before_generic_scan(self) -> None:
        """Uses the reviewed Castle-to-Blacksmith shift before the generic wall raster begins."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                    ),
                ),
            ),
        )
        runtime_state: dict[str, object] = {}

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="wall",
            ),
            reason="open_wall",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_wall_search_from_castle")
        self.assertEqual(actions[0].direction, "up")

    def test_open_home_city_object_guides_wall_search_from_blacksmith_before_generic_scan(self) -> None:
        """Uses the reviewed Blacksmith-to-Wall shift before the generic wall raster begins."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                    ),
                ),
            ),
        )
        runtime_state: dict[str, object] = {}

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="wall",
            ),
            reason="open_wall",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_wall_search_from_blacksmith")
        self.assertEqual(actions[0].direction, "left")

    def test_open_home_city_object_does_not_repeat_wall_guidance_from_same_anchor_view(self) -> None:
        """Falls back to the generic raster after the current Castle-guided wall move was already spent."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                    ),
                ),
            ),
        )
        runtime_state: dict[str, object] = {}
        query = SpatialObjectQuery(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            kind=SpatialObjectKind.HOME_BUILDING,
            metadata_key="home_city_object_id",
            metadata_value="wall",
        )

        first_actions = self.flows.open_home_city_object(
            observation,
            query,
            reason="open_wall",
            runtime_state=runtime_state,
        )
        second_actions = self.flows.open_home_city_object(
            observation,
            query,
            reason="open_wall",
            runtime_state=runtime_state,
        )

        self.assertEqual(first_actions[0].reason, "guide_wall_search_from_castle")
        self.assertEqual(len(second_actions), 1)
        self.assertIsInstance(second_actions[0], SwipeAction)
        self.assertEqual(second_actions[0].reason, "scan_home_city_upper_right_to_left_1")
