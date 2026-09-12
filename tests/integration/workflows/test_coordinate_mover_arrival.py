"""Offline integration of coordinate mover arrival."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapMovementPolicy

from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation


class CoordinateMoverArrivalTests(WorldMapRuntimeFixtures, unittest.TestCase):

    def test_coordinate_mover_stops_after_post_swipe_near_target_overshoot(self) -> None:
        """Stops after a swipe lands inside arrival tolerance instead of chasing oscillating corrections."""

        service, _observer, session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(216, 0),
            ]
        )
        mover = service.coordinate_mover_for_runtime()
        mover.movement_policy = WorldMapMovementPolicy(arrival_tolerance_units=2)

        result = mover.move_to_coordinate(
            _make_world_map_observation(210, 0),
            target_coordinate=(214, 0),
            label_prefix="near_target_post_swipe_overshoot_guard",
        )

        self.assertEqual(result.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate, (216, 0))
        self.assertEqual(len(session.swipes), 1)

    def test_coordinate_mover_accepts_crossed_target_inside_overshoot_band(self) -> None:
        """Accepts live quantized movement that crosses a checkpoint instead of oscillating back and forth."""

        service, _observer, session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(268, 0),
            ]
        )
        mover = service.coordinate_mover_for_runtime()
        mover.movement_policy = WorldMapMovementPolicy(
            arrival_tolerance_units=2,
            overshoot_tolerance_units=4,
        )

        result = mover.move_to_coordinate(
            _make_world_map_observation(260, 0),
            target_coordinate=(264, 0),
            label_prefix="crossed_target_overshoot_guard",
        )

        self.assertEqual(result.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate, (268, 0))
        self.assertEqual(len(session.swipes), 1)
