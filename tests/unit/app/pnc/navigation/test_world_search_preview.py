"""World search preview."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchPatternKind,
    WorldMapSearchService,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchPreviewTests(WorldMapSearchFixtures, unittest.TestCase):
    """Proves world search preview."""

    def test_preview_rejects_nonpositive_limits_before_plan_resolution(self) -> None:
        """Keeps the direct service contract on the same pure limit validator."""

        service = WorldMapSearchService(screen_flows=self.flows)
        with patch.object(WorldMapSearchService, "resolve_plan") as resolve_plan:
            with self.assertRaises(SelectorResolutionError):
                service.preview_route(None, None, head=0, tail=1)  # type: ignore[arg-type]

        resolve_plan.assert_not_called()

    def test_preview_route_reports_segments_and_head_tail_checkpoints(self) -> None:
        """Exposes one dry-run route preview so live sweeps can be audited before execution."""

        service = WorldMapSearchService(screen_flows=self.flows)
        preview = service.preview_route(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.serpentine_row_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(20, 20)),
                checkpoint_spacing=10,
            ),
            _make_world_map_observation(0, 0),
            head=2,
            tail=2,
        )

        self.assertEqual(preview["pattern"], WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP.value)
        self.assertEqual(preview["checkpoint_count"], 9)
        self.assertEqual(preview["head_checkpoints"][0]["coordinate"], [0, 0])
        self.assertEqual(preview["tail_checkpoints"][-1]["coordinate"], [20, 20])
        self.assertEqual(preview["segments"][1]["intent"], "local_traverse")
