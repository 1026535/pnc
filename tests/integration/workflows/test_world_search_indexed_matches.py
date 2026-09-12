"""World search indexed matches: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_index import WorldMapCastleQuery
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchStopPolicy,
    WorldMapSearchStopReason,
)

from tests.support.pnc.spatial import make_spatial_object
from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchIndexedMatchesTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search indexed matches."""

    def test_execute_search_accumulates_indexed_matches_across_checkpoints(self) -> None:
        """Uses one canonical checkpointed search loop that resolves matches from accumulated indexed survey state."""

        service, _observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(
                    0,
                    0,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.RESOURCE_NODE,
                            name_text="Food Farm A",
                            metadata={"resource_type": "food"},
                            confirmed_world_coordinate=(0, 0),
                        ),
                    ),
                ),
                _make_world_map_observation(
                    10,
                    0,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.RESOURCE_NODE,
                            name_text="Food Farm B",
                            metadata={"resource_type": "food"},
                            confirmed_world_coordinate=(10, 0),
                        ),
                    ),
                ),
            ]
        )

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                    metadata_key="resource_type",
                    metadata_value="food",
                ),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
                stop_policy=WorldMapSearchStopPolicy(max_matches=2),
            ),
            label_prefix="resource_search",
            start_observation=_make_world_map_observation(
                0,
                0,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm A",
                        metadata={"resource_type": "food"},
                        confirmed_world_coordinate=(0, 0),
                    ),
                ),
            ),
        )

        self.assertEqual(result.stop_reason, WorldMapSearchStopReason.MATCH_LIMIT_REACHED)
        self.assertEqual([match.key.coordinate for match in result.matches], [(0, 0), (10, 0)])
        self.assertEqual(len(result.visited_checkpoints), 2)
        self.assertEqual(len(result.survey_index.sightings), 2)
        self.assertEqual(len(_observer.labels), 2)

    def test_execute_search_matches_player_name_from_visible_castle_label_without_profile_inspection(self) -> None:
        """Uses the visible map-side castle label directly instead of opening lord profile for player-name matching."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(
                    0,
                    0,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.CASTLE,
                            name_text="Alice",
                            kingdom="K1",
                            confirmed_world_coordinate=(0, 0),
                        ),
                    ),
                ),
            ]
        )

        result = service.execute_search(
            _search_request(
                matcher=WorldMapCastleQuery(player_name="Alice", kingdom="K1"),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                checkpoint_spacing=10,
                stop_policy=WorldMapSearchStopPolicy(stop_on_first_confirmed_match=True),
            ),
            label_prefix="castle_search_label",
            start_observation=_make_world_map_observation(
                0,
                0,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.CASTLE,
                        name_text="Alice",
                        kingdom="K1",
                        confirmed_world_coordinate=(0, 0),
                    ),
                ),
            ),
        )

        self.assertEqual(result.stop_reason, WorldMapSearchStopReason.FIRST_CONFIRMED_MATCH)
        self.assertFalse(result.castle_enrichment_used)
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].object_.name_text, "Alice")
        self.assertEqual(observer.observations, [])
