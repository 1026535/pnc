"""Coordinate mover arrival."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import ActionTimingProfile
from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldCoordinate, WorldMapNavigator
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapCoordinateMover,
    WorldMapMovementPolicy,
    _resolve_cardinal_sweep_leg_target,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation


class CoordinateMoverArrivalTests(WorldMapSearchFixtures, unittest.TestCase):
    """Proves coordinate mover arrival."""

    def test_coordinate_mover_normalizes_unaddressable_target_before_planning(self) -> None:
        """Lets direct movement callers target raw magnifier coordinates while planning against the corrected tile."""

        mover = WorldMapCoordinateMover(
            observation_service=None,
            action_executor=None,
            navigator=WorldMapNavigator(focus_tolerance=0),
        )
        observation = _make_world_map_observation(506, 1020)

        result = mover.move_to_coordinate(
            observation,
            target_coordinate=(507, 1020),
            label_prefix="normalized_direct_move",
        )

        self.assertIs(result, observation)

    def test_coordinate_mover_accepts_near_target_without_unstable_micro_correction(self) -> None:
        """Avoids issuing tiny correction swipes that can overshoot live coordinate-bar movement."""

        mover = WorldMapCoordinateMover(
            observation_service=None,
            action_executor=None,
            navigator=WorldMapNavigator(focus_tolerance=1),
            movement_policy=WorldMapMovementPolicy(arrival_tolerance_units=2),
        )
        observation = _make_world_map_observation(154, 0)

        result = mover.move_to_coordinate(
            observation,
            target_coordinate=(152, 0),
            label_prefix="near_target_live_overshoot_guard",
        )

        self.assertIs(result, observation)



    def test_coordinate_mover_can_cap_one_axis_delta_per_observed_leg(self) -> None:
        """Lets callers configure coordinate granularity instead of always targeting the full remaining axis delta."""

        leg_target = _resolve_cardinal_sweep_leg_target(
            current=_make_world_map_observation(100, 200),
            target_coordinate=(109, 200),
            focus_tolerance=1,
            max_axis_delta_per_leg=4,
        )

        self.assertIsNotNone(leg_target)
        assert leg_target is not None
        self.assertEqual((leg_target.x, leg_target.y), (104, 200))

    def test_coordinate_mover_rejects_granularity_that_is_not_above_focus_tolerance(self) -> None:
        """Fails fast when granularity would collapse capped legs into the navigator's in-tolerance no-op band."""

        with self.assertRaises(SelectorResolutionError) as error:
            WorldMapCoordinateMover(
                observation_service=None,
                action_executor=None,
                navigator=WorldMapNavigator(focus_tolerance=1),
                movement_policy=WorldMapMovementPolicy(traverse_max_axis_delta_per_leg=1),
            )

        self.assertIn("must be greater than the navigator focus_tolerance", str(error.exception))
        self.assertEqual(error.exception.details["field_name"], "traverse_max_axis_delta_per_leg")
        self.assertEqual(error.exception.details["value"], 1)
        self.assertEqual(error.exception.details["focus_tolerance"], 1)

    def test_world_map_navigation_swipes_use_dedicated_movement_follow_up_and_timing(self) -> None:
        """Uses the dedicated movement pacing/follow-up contract so world-map swipes can be tuned independently."""

        actions = self.flows.world_map_navigator.plan_focus_coordinate(
            _make_world_map_observation(100, 100),
            WorldCoordinate(x=110, y=100),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].timing_profile, ActionTimingProfile.WORLD_MAP_MOVEMENT)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_movement_proof_follow_up())
