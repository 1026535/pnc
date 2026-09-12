"""Home city warehouse guidance."""

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


class HomeCityWarehouseGuidanceTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city warehouse guidance."""

    def test_open_home_city_object_guides_hero_war_view_from_root(self) -> None:
        """Uses the deterministic root-to-hero-war transition before generic scan for the upper support band."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Infantry Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Ranged Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.RANGED_BARRACKS),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="hero_hall",
            ),
            reason="open_hero_hall",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_hero_war_view_from_root_view")
        self.assertEqual(actions[0].direction, "up")

    def test_open_home_city_object_guides_sacred_tree_band_from_hero_war_view(self) -> None:
        """Uses the deterministic hero-war-to-sacred-tree transition before generic scan for the lower-left support band."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hero Hall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HERO_HALL),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hall of War",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HALL_OF_WAR),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="sacred_tree",
            ),
            reason="open_sacred_tree",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_sacred_tree_band_from_hero_war_view")
        self.assertEqual(actions[0].direction, "up")

    def test_open_home_city_object_guides_warehouse_search_from_hall_of_war_and_recruiting_center_band(self) -> None:
        """Uses the fixed-map downward warehouse route from the Hall of War / Sacred Tree / Recruiting Center view."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hall of War",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HALL_OF_WAR),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Sacred Tree",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.SACRED_TREE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Recruiting Center",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.RECRUITING_CENTER),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="warehouse",
            ),
            reason="open_warehouse",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_warehouse_search_from_hall_of_war_and_recruiting_center_band")
        self.assertEqual(actions[0].direction, "down")

    def test_open_home_city_object_guides_warehouse_search_from_hall_of_war_and_hero_hall(self) -> None:
        """Uses the fixed-map warehouse route once Hall of War and Hero Hall prove the correct intermediate view."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hall of War",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HALL_OF_WAR),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hero Hall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HERO_HALL),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="warehouse",
            ),
            reason="open_warehouse",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_warehouse_search_from_hall_of_war_and_hero_hall")
        self.assertEqual(actions[0].direction, "left")
