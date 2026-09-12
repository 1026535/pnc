"""Home city root taps."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import TapAction, TapPointAction
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
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class HomeCityRootTapsTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city root taps."""

    def test_open_home_city_object_uses_research_shortcut_for_institute(self) -> None:
        """Uses the fixed home-city research shortcut instead of moving the camera for Institute."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_RESEARCH_BUTTON,),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="institute",
            ),
            reason="open_institute",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_RESEARCH_BUTTON)
        self.assertEqual(actions[0].reason, "open_institute")

    def test_open_home_city_object_uses_root_view_direct_tap_for_institute_when_label_is_missing(self) -> None:
        """Uses the canonical fixed root-view tap when Institute is off the OCR surface but its anchor buildings prove the view."""

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

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="institute",
            ),
            reason="open_institute",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_institute_from_root_view")
        self.assertEqual((actions[0].x, actions[0].y), (722, 912))

    def test_open_home_city_object_uses_root_view_direct_tap_for_castle_when_label_is_missing(self) -> None:
        """Uses the canonical root-view tap for Castle when the barracks pair proves the framing despite OCR drift on Castle itself."""

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
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_castle_from_root_view")
        self.assertEqual((actions[0].x, actions[0].y), (441, 425))

    def test_open_home_city_object_uses_utility_view_direct_tap_for_warehouse_when_label_is_missing(self) -> None:
        """Uses the canonical utility-view tap when Warehouse OCR is missing but the right-side anchor view is known."""

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
            image_size=(900, 1600),
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
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_warehouse_from_utility_view")
        self.assertEqual((actions[0].x, actions[0].y), (395, 841))
