"""Home city view guidance."""

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


class HomeCityViewGuidanceTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city view guidance."""

    def test_open_home_city_object_guides_utility_view_from_root_before_generic_scan(self) -> None:
        """Uses the deterministic root-to-utility transition before falling back to raster movement for right-side fixed buildings."""

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
                metadata_value="alliance_hall",
            ),
            reason="open_alliance_hall",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_utility_view_from_root_view")
        self.assertEqual(actions[0].direction, "left")

    def test_open_home_city_object_guides_institute_wall_quadrant_from_utility_view(self) -> None:
        """Uses the deterministic utility-to-support-quadrant transition before generic scan for alliance buildings and wall-side structures."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Watch Tower",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WATCHTOWER),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Sauroi Lair",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.SAUROI_LAIR),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Campaign",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CAMPAIGN),
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
                metadata_value="blacksmith",
            ),
            reason="open_blacksmith",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_institute_wall_quadrant_from_utility_view")
        self.assertEqual(actions[0].direction, "up")

    def test_open_home_city_object_guides_root_view_from_utility_for_infantry_barracks(self) -> None:
        """Uses the deterministic utility-to-root transition before generic scan for root-view barracks targets."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Watch Tower",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WATCHTOWER),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Sauroi Lair",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.SAUROI_LAIR),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Campaign",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CAMPAIGN),
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
                metadata_value="infantry_barracks",
            ),
            reason="open_infantry_barracks",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_root_view_from_utility_view")
        self.assertEqual(actions[0].direction, "right")

    def test_hero_hall_without_visible_label_does_not_use_disproved_atlas_tap(self) -> None:
        """A Castle anchor must not authorize a blind tap at the former Hero Hall coordinate."""
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(make_spatial_object(
                    SpatialObjectKind.HOME_BUILDING,
                    name_text="Castle",
                    metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                ),),
            ),
        )
        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id", metadata_value="hero_hall",
            ),
            reason="open_hero_hall", runtime_state={},
        )
        self.assertTrue(actions)
        self.assertTrue(all(isinstance(action, SwipeAction) for action in actions))
