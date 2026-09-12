"""Campaign."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.campaign_task import CampaignTask
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class CampaignTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves campaign."""

    def test_campaign_task_can_open_campaign_from_spatial_home_city_target_without_private_search_logic(self) -> None:
        """Falls through to the shared home-city spatial opener when no Campaign shortcut selector is visible."""

        task = CampaignTask()
        context = self._make_context(params=task.parse_params({"enabled_modes": ["standard"]}), task_id=TaskId.CAMPAIGN)
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Campaign",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CAMPAIGN),
                    ),
                ),
            ),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].query.metadata_key, "home_city_object_id")
        self.assertEqual(actions[0].query.metadata_value, "campaign")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.campaign_map_follow_up())

    def test_campaign_task_accepts_battle_prep_as_campaign_entry_outcome(self) -> None:
        """Keeps Campaign entry proof consistent with the task's owned battle-prep state."""

        task = CampaignTask()
        context = self._make_context(params=task.parse_params({"enabled_modes": ["standard"]}), task_id=TaskId.CAMPAIGN)

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(ScreenType.PNC_BATTLE_PREP),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
