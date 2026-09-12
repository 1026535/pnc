"""World search plan rejection."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapMovementPreferences,
    WorldMapMovementToolKind,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchService,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.spatial import make_spatial_object
from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchPlanRejectionTests(WorldMapSearchFixtures, unittest.TestCase):
    """Proves world search plan rejection."""

    def test_resolve_plan_fails_when_self_territory_origin_cannot_be_resolved(self) -> None:
        """Fails fast when a self-territory-relative search is requested from a surface that lacks self evidence."""

        service = WorldMapSearchService(screen_flows=self.flows)

        with self.assertRaises(SelectorResolutionError):
            service.resolve_plan(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.CASTLE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    boundary=WorldMapSearchBoundary.radius_from_origin(10),
                    checkpoint_spacing=10,
                ),
                _make_world_map_observation(100, 100),
            )

    def test_resolve_plan_fails_when_visible_self_territory_lacks_coordinate(self) -> None:
        """Fails fast when the visible self castle cannot provide the canonical self-territory origin coordinate."""

        service = WorldMapSearchService(screen_flows=self.flows)

        with self.assertRaises(SelectorResolutionError):
            service.resolve_plan(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.CASTLE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    boundary=WorldMapSearchBoundary.radius_from_origin(10),
                    checkpoint_spacing=10,
                ),
                _make_world_map_observation(
                    100,
                    100,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.CASTLE,
                            name_text="My Territory",
                            relationship=SpatialObjectRelationship.SELF,
                        ),
                    ),
                ),
            )

    def test_resolve_plan_fails_when_requested_movement_tool_is_not_supported(self) -> None:
        """Fails fast when a request requires a placeholder movement primitive in a swipe-only runtime."""

        service = WorldMapSearchService(screen_flows=self.flows)
        service.coordinate_navigator.supported = False
        service.overview_navigator.movement_supported = False

        for movement_tool in (WorldMapMovementToolKind.COORDINATE_JUMP, WorldMapMovementToolKind.OVERVIEW_SEED):
            with self.subTest(movement_tool=movement_tool):
                with self.assertRaises(SelectorResolutionError):
                    service.resolve_plan(
                        _search_request(
                            matcher=SpatialObjectQuery(
                                surface_type=SpatialSurfaceType.WORLD_MAP,
                                kind=SpatialObjectKind.RESOURCE_NODE,
                            ),
                            pattern=WorldMapSearchPattern.row_major_sweep(),
                            origin=WorldMapSearchOrigin.current_viewport(),
                            boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
                            checkpoint_spacing=10,
                            movement_preferences=WorldMapMovementPreferences((movement_tool,)),
                        ),
                        _make_world_map_observation(0, 0),
                    )
