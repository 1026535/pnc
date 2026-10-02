"""World search preview."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search_contracts import (
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
)
from pnc_automation.app.pnc.navigation.world_map_search_planning import (
    format_world_map_route_preview,
    validate_world_map_preview_limits,
)
from pnc_automation.app.pnc.navigation.world_map_traversal import WorldMapSearchPatternKind
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.resolve_search_plan import _resolve_search_plan
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchPreviewTests(unittest.TestCase):
    """Proves world search preview."""

    def test_preview_rejects_nonpositive_limits(self) -> None:
        """Keeps the pure route-preview limit validator on the same canonical contract."""

        with self.assertRaises(SelectorResolutionError):
            validate_world_map_preview_limits(head=0, tail=1)

    def test_preview_route_reports_segments_and_head_tail_checkpoints(self) -> None:
        """Exposes one dry-run route preview so live sweeps can be audited before execution."""

        plan = _resolve_search_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.serpentine_row_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(20, 20)),
                checkpoint_spacing=10,
            ),
            _make_world_map_observation(0, 0),
        )
        preview = format_world_map_route_preview(plan, head=2, tail=2)

        self.assertEqual(preview["pattern"], WorldMapSearchPatternKind.SERPENTINE_ROW_SWEEP.value)
        self.assertEqual(preview["checkpoint_count"], 9)
        self.assertEqual(preview["head_checkpoints"][0]["coordinate"], [0, 0])
        self.assertEqual(preview["tail_checkpoints"][-1]["coordinate"], [20, 20])
        self.assertEqual(preview["segments"][1]["intent"], "local_traverse")
