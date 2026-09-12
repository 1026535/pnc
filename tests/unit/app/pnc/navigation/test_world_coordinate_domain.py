"""World coordinate domain."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapBounds,
    WorldMapCoordinateDomain,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchService,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldCoordinateDomainTests(WorldMapSearchFixtures, unittest.TestCase):
    """Proves world coordinate domain."""

    def test_coordinate_domain_models_addressable_coordinate_pairs_not_axes(self) -> None:
        """Treats every integer axis value as usable while rejecting impossible x/y pair parity."""

        domain = WorldMapCoordinateDomain.puzzles_and_conquest()

        self.assertTrue(domain.is_addressable((506, 1020)))
        self.assertTrue(domain.is_addressable((508, 1020)))
        self.assertTrue(domain.is_addressable((507, 1019)))
        self.assertTrue(domain.is_addressable((509, 1019)))
        self.assertFalse(domain.is_addressable((508, 1019)))
        self.assertEqual(domain.nearest_addressable_in_bounds((507, 1020)), (506, 1020))
        self.assertEqual(domain.nearest_addressable_in_bounds((0, 1023)), (0, 1022))
        self.assertEqual(domain.nearest_addressable_in_bounds((511, 0)), (510, 0))
        for coordinate in ((-5, 0), (999, 999), (0, 5000)):
            with self.subTest(coordinate=coordinate):
                with self.assertRaises(SelectorResolutionError):
                    domain.nearest_addressable_in_bounds(coordinate)

    def test_coordinate_domain_local_bounds_clamp_to_edges(self) -> None:
        """Builds one canonical local bounds window without duplicating live-tool edge clamping logic."""

        domain = WorldMapCoordinateDomain.puzzles_and_conquest()

        self.assertEqual(
            domain.local_bounds_around((2, 1022), radius=6),
            WorldMapBounds(min_x=0, min_y=1016, max_x=8, max_y=1023),
        )
        with self.assertRaises(SelectorResolutionError):
            domain.local_bounds_around((2, 1022), radius=-1)

    def test_resolve_plan_fails_when_current_viewport_origin_is_outside_domain(self) -> None:
        """Rejects impossible viewport OCR coordinates instead of clamping them to a plausible kingdom edge."""

        service = WorldMapSearchService(screen_flows=self.flows)

        with self.assertRaises(SelectorResolutionError):
            service.resolve_plan(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    checkpoint_spacing=10,
                ),
                _make_world_map_observation(999, 999),
            )

    def test_resolve_plan_fails_when_explicit_origin_is_outside_domain(self) -> None:
        """Rejects invalid caller coordinates instead of silently routing from the nearest map edge."""

        service = WorldMapSearchService(screen_flows=self.flows)

        with self.assertRaises(SelectorResolutionError):
            service.resolve_plan(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.explicit_coordinate((512, 0)),
                    checkpoint_spacing=10,
                ),
                _make_world_map_observation(0, 0),
            )
