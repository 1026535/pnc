"""Home city atlas entry."""

from __future__ import annotations

import unittest

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import (
    SwipeAction,
    TapPointAction,
    TapSpatialObjectAction,
    WaitAction,
)
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
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class HomeCityAtlasEntryTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city atlas entry."""

    def test_open_home_city_object_refreshes_when_home_city_surface_parse_is_temporarily_missing(self) -> None:
        """Requests one bounded re-observation instead of crashing when home-city chrome is visible but the parsed surface is absent."""

        actions = self.flows.open_home_city_object(
            make_observation(ScreenType.PNC_HOME_CITY),
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                name_text="Castle",
            ),
            reason="open_castle",
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY))

    def test_open_institute_uses_home_city_spatial_building_when_fixed_button_is_missing(self) -> None:
        """Falls back to the home-city spatial surface instead of a legacy academy selector."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Academy",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                ),
            ),
        )

        actions = self.flows.open_institute(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].query.kind, SpatialObjectKind.HOME_BUILDING)
        self.assertEqual(actions[0].query.metadata_key, "home_city_object_id")
        self.assertEqual(actions[0].query.metadata_value, "institute")
        self.assertEqual(actions[0].target_point, (50, 50))

    def test_focus_home_city_object_uses_extended_fixed_map_tour_before_exhaustion(self) -> None:
        """Keeps home-city search alive across the full canonical fixed-map tour before failing fast."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
        )
        runtime_state: dict[str, object] = {}
        query = SpatialObjectQuery(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            kind=SpatialObjectKind.HOME_BUILDING,
            metadata_key="home_city_object_id",
            metadata_value="wall",
        )

        first_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        second_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        third_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        fourth_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        fifth_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        sixth_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)

        for actions in (
            first_actions,
            second_actions,
            third_actions,
            fourth_actions,
            fifth_actions,
            sixth_actions,
        ):
            self.assertEqual(len(actions), 1)
            self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(first_actions[0].direction, "left")
        self.assertEqual(first_actions[0].reason, "scan_home_city_upper_right_to_left_1")
        self.assertEqual(second_actions[0].direction, "left")
        self.assertEqual(second_actions[0].reason, "scan_home_city_upper_right_to_left_2")
        self.assertEqual(third_actions[0].direction, "down")
        self.assertEqual(third_actions[0].reason, "scan_home_city_shift_to_lower_view")
        self.assertEqual(fourth_actions[0].direction, "right")
        self.assertEqual(fourth_actions[0].reason, "scan_home_city_lower_left_to_right_1")
        self.assertEqual(fifth_actions[0].direction, "right")
        self.assertEqual(fifth_actions[0].reason, "scan_home_city_lower_left_to_right_2")
        self.assertEqual(sixth_actions[0].direction, "up")
        self.assertEqual(sixth_actions[0].reason, "scan_home_city_reset_to_upper_view")

        remaining_steps = self.flows.home_city_navigator.focus_step_budget() - 6
        for _ in range(remaining_steps):
            actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
            self.assertEqual(len(actions), 1)
            self.assertIsInstance(actions[0], SwipeAction)
        with self.assertRaises(SelectorResolutionError):
            self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)

    def test_open_home_city_object_uses_atlas_tap_when_target_should_already_be_visible(self) -> None:
        """Uses the static home-city atlas to click the target even when OCR only recognized the anchor building."""

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

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="infantry_barracks",
            ),
            reason="open_infantry_barracks",
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "right")
        self.assertEqual(actions[0].reason, "focus_infantry_barracks_from_home_city_atlas_x")
        self.assertIsInstance(actions[1], TapPointAction)
        self.assertEqual((actions[1].x, actions[1].y), (180, 699))
        self.assertEqual(actions[1].reason, "open_infantry_barracks_from_home_city_atlas")

    def test_build_home_city_object_metadata_exposes_static_atlas_coordinate(self) -> None:
        """Keeps the atlas coordinate on canonical building metadata so runtime inference only consumes static data."""

        metadata = build_home_city_object_metadata(HomeCityObjectId.ALLIANCE_HALL)

        self.assertEqual(metadata["home_city_map_coordinate"], (1881, 1538))
