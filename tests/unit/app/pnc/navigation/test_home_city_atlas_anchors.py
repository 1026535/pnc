"""Home city atlas anchors."""

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


class HomeCityAtlasAnchorsTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city atlas anchors."""

    def test_open_home_city_object_uses_atlas_swipe_when_target_is_offscreen(self) -> None:
        """Uses the static home-city atlas to move toward an offscreen target before any generic sweep starts."""

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
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {}

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="alliance_hall",
            ),
            reason="open_alliance_hall",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertFalse(actions[0].observe_after)
        self.assertEqual(actions[0].direction, "left")
        self.assertEqual(actions[0].reason, "focus_alliance_hall_from_home_city_atlas_x")
        self.assertIsInstance(actions[1], SwipeAction)
        self.assertFalse(actions[1].observe_after)
        self.assertEqual(actions[1].direction, "up")
        self.assertEqual(actions[1].reason, "focus_alliance_hall_from_home_city_atlas_y")
        self.assertIsInstance(actions[2], TapPointAction)
        self.assertEqual((actions[2].x, actions[2].y), (640, 1085))
        self.assertTrue(actions[2].observe_after)
        self.assertEqual(actions[2].reason, "open_alliance_hall_from_home_city_atlas")

    def test_open_home_city_object_ignores_repeatable_small_buildings_as_atlas_anchors(self) -> None:
        """Refuses to infer the atlas center from repeatable small-building labels whose slots are not uniquely fixed."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Farm",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.FARM),
                        viewport_offset_ratio=(0.1, -0.2),
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
                metadata_value="castle",
            ),
            reason="open_castle",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "scan_home_city_upper_right_to_left_1")

    def test_open_home_city_object_can_use_remembered_atlas_center_when_current_view_has_no_unique_anchor(self) -> None:
        """Keeps using the last planned viewport center when the latest screenshot is visually ambiguous after blind motion."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {
            "home_city_navigation": {
                "known_viewport_center": (1521, 1000),
            }
        }

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="castle",
            ),
            reason="open_castle",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "right")
        self.assertEqual(actions[0].reason, "focus_castle_from_home_city_atlas_x")
        self.assertIsInstance(actions[1], TapPointAction)
        self.assertEqual(actions[1].reason, "open_castle_from_home_city_atlas")

    def test_open_home_city_object_repositions_before_tapping_when_the_current_view_would_put_the_target_under_hud(self) -> None:
        """Refuses blind taps that would land inside the persistent home-city HUD and nudges the camera first."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {
            "home_city_navigation": {
                "known_viewport_center": (1394, 851),
            }
        }

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="trap_workshop",
            ),
            reason="open_trap_workshop",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")
        self.assertEqual(actions[0].reason, "focus_trap_workshop_from_home_city_atlas_y")
        self.assertEqual(actions[0].start_x_ratio, 0.55)
        self.assertIsNotNone(actions[0].start_y_ratio)
        self.assertEqual(actions[0].end_x_ratio, 0.55)
        self.assertIsNotNone(actions[0].end_y_ratio)
        self.assertIsInstance(actions[1], TapPointAction)
        self.assertEqual((actions[1].x, actions[1].y), (351, 1085))
        self.assertEqual(actions[1].reason, "open_trap_workshop_from_home_city_atlas")
