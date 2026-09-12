"""Coordinate search target."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Bounds
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    _build_world_map_search_button_element,
)



class CoordinateSearchTargetTests(unittest.TestCase):
    """Proves coordinate search target."""

    def test_world_map_search_button_target_stays_inside_widened_live_coordinate_crop(self) -> None:
        """Targets the magnifier inside the widened coordinate crop instead of tapping a map object to its left."""

        search_button = _build_world_map_search_button_element(
            image=Image.new("RGB", (900, 1600), (0, 0, 0)),
            coordinate_bounds=Bounds(x=307, y=112, width=270, height=88),
        )

        self.assertEqual(search_button.action_point, (342, 156))
