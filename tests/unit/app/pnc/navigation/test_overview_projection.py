"""Overview projection."""

from __future__ import annotations

import unittest

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapCoordinateDomain
from pnc_automation.app.pnc.navigation.world_map_overview_projection import (
    project_overview_marker_to_world_coordinate,
    project_world_coordinate_to_overview_point,
)
from pnc_automation.app.pnc.domain.observation import Bounds



class OverviewProjectionTests(unittest.TestCase):
    """Proves overview projection."""

    def test_overview_projection_keeps_bottom_right_edge_inside_click_region(self) -> None:
        """Maps inclusive world edges to the final in-bounds overview pixel and rejects the next pixel outside it."""

        bounds = WorldMapCoordinateDomain.puzzles_and_conquest().bounds
        map_region_bounds = Bounds(x=0, y=0, width=200, height=200)

        marker_point = project_world_coordinate_to_overview_point(
            coordinate=(511, 1023),
            bounds=bounds,
            map_region_bounds=map_region_bounds,
        )

        self.assertEqual(marker_point, (199, 199))
        self.assertEqual(
            project_overview_marker_to_world_coordinate(
                marker_point=marker_point,
                map_region_bounds=map_region_bounds,
                bounds=bounds,
            ),
            (511, 1023),
        )
        with self.assertRaises(SelectorResolutionError):
            project_overview_marker_to_world_coordinate(
                marker_point=(200, 200),
                map_region_bounds=map_region_bounds,
                bounds=bounds,
            )
