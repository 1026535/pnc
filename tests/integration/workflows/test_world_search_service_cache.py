"""Offline integration of world search service cache."""

from __future__ import annotations

import unittest

from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures


class WorldSearchPreviewTests(WorldMapRuntimeFixtures, unittest.TestCase):

    def test_search_service_caches_runtime_coordinate_mover_for_live_tuning(self) -> None:
        """Reuses one runtime coordinate mover so live helpers can tune granularity on the shared instance."""

        service, _observer = self._build_runtime_service(observations=[])

        first = service.coordinate_mover_for_runtime()
        first.max_axis_delta_per_leg = 5
        second = service.coordinate_mover_for_runtime()

        self.assertIs(first, second)
        self.assertEqual(second.max_axis_delta_per_leg, 5)
