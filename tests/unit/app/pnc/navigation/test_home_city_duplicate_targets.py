"""Home city duplicate targets."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class HomeCityDuplicateTargetsTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves home city duplicate targets."""

    def test_open_visible_home_city_object_preserves_selected_duplicate_building_identity(self) -> None:
        """Keeps the chosen home-city duplicate target instead of collapsing repeated buildings into one query match."""

        first = make_spatial_object(
            SpatialObjectKind.HOME_BUILDING,
            name_text="Infantry Barracks",
            metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
            action_point=(61, 71),
        )
        second = make_spatial_object(
            SpatialObjectKind.HOME_BUILDING,
            name_text="Infantry Barracks",
            metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
            action_point=(133, 144),
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(first, second),
            ),
        )

        actions = self.flows.open_visible_home_city_object(observation, second, reason="open_duplicate_infantry_barracks")

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].target_point, (133, 144))
