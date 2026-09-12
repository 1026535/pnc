"""World search planning."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapBounds,
    WorldMapMapCorner,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchService,
    WorldMapTraversalCorner,
)

from tests.support.pnc.spatial import make_spatial_object
from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchPlanningTests(WorldMapSearchFixtures, unittest.TestCase):
    """Proves world search planning."""

    def test_resolve_plan_uses_self_territory_origin_for_row_major_radius_search(self) -> None:
        """Defaults origin resolution to My Territory and produces a deterministic row-major bounded route."""

        service = WorldMapSearchService(screen_flows=self.flows)
        observation = _make_world_map_observation(
            100,
            100,
            objects=(
                make_spatial_object(
                    SpatialObjectKind.CASTLE,
                    name_text="My Territory",
                    relationship=SpatialObjectRelationship.SELF,
                    estimated_world_coordinate=(100, 100),
                ),
            ),
        )

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.CASTLE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                boundary=WorldMapSearchBoundary.radius_from_origin(10),
                checkpoint_spacing=10,
            ),
            observation,
        )

        self.assertEqual(plan.origin_coordinate, (100, 100))
        self.assertEqual(
            [checkpoint.coordinate for checkpoint in plan.route],
            [
                (90, 90),
                (100, 90),
                (110, 90),
                (90, 100),
                (100, 100),
                (110, 100),
                (90, 110),
                (100, 110),
                (110, 110),
            ],
        )

    def test_resolve_plan_builds_expanding_ring_route_from_explicit_origin(self) -> None:
        """Produces the deterministic expanding-ring order around an explicit center coordinate."""

        service = WorldMapSearchService(screen_flows=self.flows)
        observation = _make_world_map_observation(100, 100)

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.MONSTER),
                pattern=WorldMapSearchPattern.expanding_ring(),
                origin=WorldMapSearchOrigin.explicit_coordinate((100, 100)),
                boundary=WorldMapSearchBoundary.radius_from_origin(10),
                checkpoint_spacing=10,
            ),
            observation,
        )

        self.assertEqual(
            [checkpoint.coordinate for checkpoint in plan.route],
            [
                (100, 100),
                (90, 90),
                (100, 90),
                (110, 90),
                (110, 100),
                (110, 110),
                (100, 110),
                (90, 110),
                (90, 100),
            ],
        )

    def test_resolve_plan_builds_perimeter_route_from_full_map_bounds(self) -> None:
        """Builds one explicit perimeter traversal around the requested bounds."""

        service = WorldMapSearchService(screen_flows=self.flows)
        observation = _make_world_map_observation(0, 0)

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.perimeter_ring_sweep(start_corner=WorldMapTraversalCorner.UPPER_LEFT),
                origin=WorldMapSearchOrigin.map_corner(WorldMapMapCorner.UPPER_LEFT),
                boundary=WorldMapSearchBoundary.full_map(
                    WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=20),
                ),
                checkpoint_spacing=10,
            ),
            observation,
        )

        self.assertEqual(
            [checkpoint.coordinate for checkpoint in plan.route],
            [(0, 0), (10, 0), (20, 0), (20, 10), (20, 20), (10, 20), (0, 20), (0, 10)],
        )
