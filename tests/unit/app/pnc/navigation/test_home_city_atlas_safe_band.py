"""Home city atlas safe band."""

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


class HomeCityAtlasSafeBandTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city atlas safe band."""

    def test_open_home_city_object_routes_exactly_to_the_safe_band_for_final_taps(self) -> None:
        """Uses exact atlas routing for open actions so the final blind tap never stops just outside the safe band."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {
            "home_city_navigation": {
                "known_viewport_center": (1774, 704),
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

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")
        self.assertEqual(actions[0].reason, "focus_trap_workshop_from_home_city_atlas_y")
        self.assertIsInstance(actions[1], SwipeAction)
        self.assertEqual(actions[1].direction, "right")
        self.assertEqual(actions[1].reason, "focus_trap_workshop_from_home_city_atlas_x")
        self.assertIsInstance(actions[2], TapPointAction)
        self.assertEqual((actions[2].x, actions[2].y), (180, 1085))
        self.assertEqual(actions[2].reason, "open_trap_workshop_from_home_city_atlas")

    def test_open_home_city_object_prioritizes_the_x_axis_before_vertical_motion_in_the_sauroi_band(self) -> None:
        """Keeps blind routes through the Sauroi/Campaign skyline deterministic by shifting horizontally before vertical motion."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Sauroi Lair",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.SAUROI_LAIR),
                        viewport_offset_ratio=(0.005555555555555556, 0.03875),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Arena",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.ARENA),
                        viewport_offset_ratio=(0.37777777777777777, 0.223125),
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

        self.assertGreaterEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "right")
        self.assertEqual(actions[0].reason, "focus_trap_workshop_from_home_city_atlas_x")
        self.assertIsInstance(actions[1], SwipeAction)
        self.assertEqual(actions[1].direction, "up")
        self.assertEqual(actions[1].reason, "focus_trap_workshop_from_home_city_atlas_y")
        self.assertEqual(actions[1].start_x_ratio, 0.55)
        self.assertEqual(actions[1].end_x_ratio, 0.55)

    def test_open_home_city_object_uses_the_castle_utility_vertical_swipe_lane_for_trap_workshop(self) -> None:
        """Routes y-first trap-workshop pans through the reviewed right-side lane when the castle utility band is visible."""

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
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                        viewport_offset_ratio=(55 / 900, 460 / 1600),
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

        self.assertGreaterEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")
        self.assertEqual(actions[0].reason, "focus_trap_workshop_from_home_city_atlas_y")
        self.assertEqual(actions[0].start_x_ratio, 0.69)
        self.assertEqual(actions[0].end_x_ratio, 0.69)

    def test_open_home_city_object_guides_trap_workshop_into_the_blacksmith_lower_band(self) -> None:
        """Uses a deterministic short upward pan once the blacksmith-only skyline proves the lower-band trap view is nearby."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                        viewport_offset_ratio=(0.18333333333333332, 0.009375),
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
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")
        self.assertEqual(actions[0].reason, "guide_trap_workshop_lower_band_from_blacksmith")

    def test_open_home_city_object_uses_blacksmith_lower_band_direct_tap_for_trap_workshop(self) -> None:
        """Treats the calibrated blacksmith-plus-farm lower band as a trusted direct-tap view for trap workshop."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                        viewport_offset_ratio=(0.18444444444444444, -0.22875),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Farm",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.FARM),
                        viewport_offset_ratio=(0.31666666666666665, 0.1775),
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
        self.assertEqual(actions[0].reason, "open_trap_workshop_from_blacksmith_lower_band")
        self.assertEqual((actions[0].x, actions[0].y), (667, 875))
