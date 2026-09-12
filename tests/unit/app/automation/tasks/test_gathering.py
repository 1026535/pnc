"""Gathering."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskPreflight, TaskStatus
from pnc_automation.app.automation.tasks.campaign_task import CampaignTask
from pnc_automation.app.automation.tasks.gathering_task import GatheringTask
from pnc_automation.app.pnc.domain.action_requests import TapAction, TapSpatialObjectAction
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.domain.policy_models import GatheringPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class GatheringTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves gathering."""

    def test_gathering_task_declares_runner_owned_world_map_preflight(self) -> None:
        """Declares one shared runner-owned world-map preflight before the gathering body runs."""

        self.assertEqual(GatheringTask.preflight, TaskPreflight.WORLD_MAP)

    def test_gathering_task_uses_canonical_world_map_readiness_when_reentered_off_root(self) -> None:
        """Reuses the shared world-map readiness flow if a gathering replan observes an off-root screen."""

        task = GatheringTask()
        context = self._make_context(params=GatheringPolicy(), task_id=TaskId.GATHERING)
        observation = make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,))

        actions = task.plan(context, observation)

        self.assertEqual(actions, self.flows.ensure_world_map_ready(observation))

    def test_gathering_task_chooses_highest_priority_visible_resource_node(self) -> None:
        """Chooses visible world-map resource nodes from the spatial surface instead of list entries."""

        task = GatheringTask()
        context = self._make_context(params=GatheringPolicy(), task_id=TaskId.GATHERING)
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=253,
                y=447,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Wood Lot",
                        metadata={"resource_type": "wood"},
                    ),
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                        action_point=(68, 52),
                    ),
                ),
            ),
            available_march_slots=2,
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].query.kind, SpatialObjectKind.RESOURCE_NODE)
        self.assertEqual(actions[0].query.metadata_key, "resource_type")
        self.assertEqual(actions[0].query.metadata_value, "food")
        self.assertEqual(actions[0].target_point, (68, 52))
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.gather_node_follow_up())

    def test_gathering_task_plans_each_gathering_phase_with_strict_follow_up(self) -> None:
        """Emits only the action valid for the current gathering screen and proves its next phase."""

        task = GatheringTask()
        context = self._make_context(params=GatheringPolicy(), task_id=TaskId.GATHERING)

        gather_node_actions = task.plan(
            context,
            make_observation(ScreenType.PNC_GATHER_NODE, visible_ids=(UiElementId.PNC_GATHER_BUTTON,)),
        )
        march_confirm_actions = task.plan(
            context,
            make_observation(ScreenType.PNC_MARCH_CONFIRM, visible_ids=(UiElementId.PNC_MARCH_CONFIRM_BUTTON,)),
        )

        self.assertEqual(len(gather_node_actions), 1)
        self.assertIsInstance(gather_node_actions[0], TapAction)
        self.assertEqual(gather_node_actions[0].selector_id, UiElementId.PNC_GATHER_BUTTON)
        self.assertEqual(gather_node_actions[0].follow_up_request, ObservationRequest.march_confirm_follow_up())
        self.assertEqual(len(march_confirm_actions), 1)
        self.assertIsInstance(march_confirm_actions[0], TapAction)
        self.assertEqual(march_confirm_actions[0].selector_id, UiElementId.PNC_MARCH_CONFIRM_BUTTON)
        self.assertEqual(
            march_confirm_actions[0].follow_up_request,
            ObservationRequest.post_march_dispatch_follow_up(),
        )

    def test_gathering_task_replans_between_proven_gathering_phases(self) -> None:
        """Treats node opening and march-confirm opening as intermediate states, not final success."""

        task = GatheringTask()
        context = self._make_context(params=GatheringPolicy(), task_id=TaskId.GATHERING)
        world_map = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                    ),
                ),
            ),
        )

        node_result = task.verify(context, world_map, make_observation(ScreenType.PNC_GATHER_NODE))
        confirm_result = task.verify(
            context,
            make_observation(ScreenType.PNC_GATHER_NODE),
            make_observation(ScreenType.PNC_MARCH_CONFIRM),
        )

        self.assertEqual(node_result.status, TaskStatus.REPLAN)
        self.assertEqual(confirm_result.status, TaskStatus.REPLAN)

    def test_gathering_task_does_not_accept_unchanged_world_map_with_unknown_slots_as_success(self) -> None:
        """Requires proof that the dispatch phase was reached before unknown march slots can still succeed."""

        task = GatheringTask()
        context = self._make_context(params=GatheringPolicy(), task_id=TaskId.GATHERING)
        before = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                    ),
                ),
            ),
            available_march_slots=None,
        )
        after = make_observation(ScreenType.PNC_WORLD_MAP, available_march_slots=None)

        result = task.verify(context, before, after)

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(result.retryable)

    def test_campaign_task_uses_shared_home_city_target_opening_with_campaign_map_proof(self) -> None:
        """Opens Campaign through the shared Home City target helper with an action-scoped Campaign-map proof."""

        task = CampaignTask()
        context = self._make_context(params=task.parse_params({"enabled_modes": ["standard"]}), task_id=TaskId.CAMPAIGN)
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_CAMPAIGN_ENTRY,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_CAMPAIGN_ENTRY)
        self.assertEqual(actions[0].reason, "open_campaign_map")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.campaign_map_follow_up())

    def test_gathering_task_skips_when_no_march_slots_remain(self) -> None:
        """Treats zero available march slots as a safe no-op."""

        task = GatheringTask()
        context = self._make_context(params=GatheringPolicy(), task_id=TaskId.GATHERING)
        before = make_observation(ScreenType.PNC_WORLD_MAP, available_march_slots=0)
        after = before

        result = task.verify(context, before, after)

        self.assertTrue(result.succeeded)
        self.assertIn("No march slots", result.message)
