"""World search route edges."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldMapNavigator
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapBounds,
    WorldMapCoordinateDomain,
    WorldMapCoordinateMover,
    WorldMapMapCorner,
    WorldMapMovementToolKind,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchService,
    WorldMapTraversalActionFamily,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchRouteEdgesTests(WorldMapSearchFixtures, unittest.TestCase):
    """Proves world search route edges."""

    def test_coordinate_mover_fails_when_direct_target_is_outside_domain(self) -> None:
        """Rejects direct movement targets outside the kingdom coordinate domain."""

        mover = WorldMapCoordinateMover(
            observation_service=None,
            action_executor=None,
            navigator=WorldMapNavigator(focus_tolerance=0),
        )

        with self.assertRaises(SelectorResolutionError):
            mover.move_to_coordinate(
                _make_world_map_observation(0, 0),
                target_coordinate=(0, 5000),
                label_prefix="invalid_direct_move",
            )

    def test_row_major_route_uses_addressable_neighbors_on_one_world_map_row(self) -> None:
        """Skips impossible coordinate pairs while preserving valid same-row integer neighbors."""

        service = WorldMapSearchService(screen_flows=self.flows)
        observation = _make_world_map_observation(507, 1019)

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(507, 1019), max_coordinate=(511, 1019)),
                checkpoint_spacing=1,
            ),
            observation,
        )

        self.assertEqual(
            [checkpoint.coordinate for checkpoint in plan.route],
            [(507, 1019), (509, 1019), (511, 1019)],
        )

    def test_row_major_route_fails_when_rectangle_contains_no_addressable_pair(self) -> None:
        """Fails fast instead of snapping a no-tile rectangle outside its requested boundary."""

        service = WorldMapSearchService(screen_flows=self.flows)

        with self.assertRaises(SelectorResolutionError):
            service.resolve_plan(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.explicit_coordinate((508, 1019)),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(508, 1019), max_coordinate=(508, 1019)),
                    checkpoint_spacing=1,
                ),
                _make_world_map_observation(508, 1018),
            )

    def test_full_map_corner_origin_snaps_to_addressable_coordinate_pair(self) -> None:
        """Resolves impossible map-corner pairs to the closest real world-map coordinate pair."""

        service = WorldMapSearchService(screen_flows=self.flows)
        domain = WorldMapCoordinateDomain.puzzles_and_conquest()

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.map_corner(WorldMapMapCorner.UPPER_RIGHT),
                boundary=WorldMapSearchBoundary.full_map(domain.bounds),
                checkpoint_spacing=1024,
            ),
            _make_world_map_observation(0, 0),
        )

        self.assertEqual(plan.origin_coordinate, (510, 0))
        self.assertIn((510, 0), [checkpoint.coordinate for checkpoint in plan.route])
        self.assertIn((0, 1022), [checkpoint.coordinate for checkpoint in plan.route])
        self.assertTrue(all(domain.is_addressable(checkpoint.coordinate) for checkpoint in plan.route))

    def test_full_map_row_sweep_prepends_non_local_entry_intent_from_far_current_viewport(self) -> None:
        """Models broad full-map entry as one non-local itinerary step instead of ordinary local traversal."""

        service = WorldMapSearchService(screen_flows=self.flows)
        domain = WorldMapCoordinateDomain.puzzles_and_conquest()

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.serpentine_row_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.full_map(domain.bounds),
                checkpoint_spacing=10,
            ),
            _make_world_map_observation(334, 510),
        )

        self.assertEqual(plan.coverage_bounds, WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023))
        self.assertEqual(len(plan.route), 5460)
        self.assertEqual(plan.execution_start_coordinate, (334, 510))
        self.assertEqual(plan.route[0].coordinate, (0, 0))
        self.assertEqual(plan.execution_plan.steps[0].action_family, WorldMapTraversalActionFamily.NON_LOCAL_DIRECT)
        self.assertEqual(plan.execution_plan.steps[1].action_family, WorldMapTraversalActionFamily.LOCAL_DIRECT)
        self.assertEqual(plan.first_step_movement_tool, WorldMapMovementToolKind.COORDINATE_JUMP)
