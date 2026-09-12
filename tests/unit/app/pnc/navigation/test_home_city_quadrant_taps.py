"""Home city quadrant taps."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapPointAction
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


class HomeCityQuadrantTapsTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city quadrant taps."""

    def test_open_home_city_object_uses_institute_wall_quadrant_direct_tap_for_alliance_hall(self) -> None:
        """Uses the known lower-right quadrant tap for Alliance Hall when the surrounding fixed buildings prove the view."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
            image_size=(900, 1600),
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
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_alliance_hall_from_institute_wall_quadrant")
        self.assertEqual((actions[0].x, actions[0].y), (827, 666))

    def test_open_home_city_object_uses_institute_wall_quadrant_direct_tap_for_blacksmith(self) -> None:
        """Uses the known lower-left quadrant tap for Blacksmith when the surrounding fixed buildings prove the view."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Alliance Hall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.ALLIANCE_HALL),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
            image_size=(900, 1600),
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
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_blacksmith_from_institute_wall_quadrant")
        self.assertEqual((actions[0].x, actions[0].y), (190, 924))

    def test_open_home_city_object_uses_institute_wall_quadrant_direct_tap_for_trap_workshop(self) -> None:
        """Uses the fixed lower-left support-slot tap for Trap Workshop when the institute-wall framing is proven."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="trap_workshop",
            ),
            reason="open_trap_workshop",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_trap_workshop_from_institute_wall_quadrant")
        self.assertEqual((actions[0].x, actions[0].y), (241, 1365))

    def test_open_home_city_object_does_not_repeat_direct_tap_from_same_anchor_view(self) -> None:
        """Spends one trusted fixed-view tap attempt once before falling back to the remaining fixed-map navigation budget."""

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
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {}
        query = SpatialObjectQuery(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            kind=SpatialObjectKind.HOME_BUILDING,
            metadata_key="home_city_object_id",
            metadata_value="institute",
        )

        first_actions = self.flows.open_home_city_object(
            observation,
            query,
            reason="open_institute",
            runtime_state=runtime_state,
        )
        second_actions = self.flows.open_home_city_object(
            observation,
            query,
            reason="open_institute",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(first_actions), 1)
        self.assertIsInstance(first_actions[0], TapPointAction)
        self.assertEqual(first_actions[0].reason, "open_institute_from_root_view")
        self.assertEqual(len(second_actions), 1)
        self.assertIsInstance(second_actions[0], SwipeAction)
        self.assertEqual(second_actions[0].reason, "scan_home_city_upper_right_to_left_1")
