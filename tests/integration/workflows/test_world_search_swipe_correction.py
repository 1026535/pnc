"""World search swipe correction: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchStopPolicy,
    WorldMapSearchStopReason,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object
from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchSwipeCorrectionTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search swipe correction."""

    def test_execute_search_recovers_when_one_post_swipe_world_map_observation_lacks_surface(self) -> None:
        """Refreshes one transient world-map parse miss during traversal instead of failing or re-entering world map."""

        service, _observer = self._build_runtime_service(
            observations=[
                make_observation(ScreenType.PNC_WORLD_MAP),
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
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
                stop_policy=WorldMapSearchStopPolicy(stop_on_first_confirmed_match=True),
            ),
            label_prefix="resource_search_surface_refresh",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(result.stop_reason, WorldMapSearchStopReason.FIRST_CONFIRMED_MATCH)
        self.assertEqual([match.key.coordinate for match in result.matches], [(10, 0)])

    def test_execute_search_uses_cardinal_sweep_movement_for_diagonal_checkpoint_travel(self) -> None:
        """Decomposes search checkpoint travel into cardinal legs instead of relying on diagonal world-map swipes."""

        service, observer, session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(10, 0),
                _make_world_map_observation(10, 10),
            ]
        )

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 10), max_coordinate=(10, 10)),
                checkpoint_spacing=10,
            ),
            label_prefix="cardinal_checkpoint_move",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(result.stop_reason, WorldMapSearchStopReason.BOUNDARY_EXHAUSTED)
        self.assertEqual(len(session.swipes), 2)
        self.assertEqual(len(observer.labels), 2)

    def test_execute_search_corrects_horizontal_orthogonal_drift_with_vertical_leg(self) -> None:
        """Corrects vertical drift after a successful horizontal cardinal move before finishing the checkpoint."""

        service, _observer, session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(6, 9),
                _make_world_map_observation(6, 0),
                _make_world_map_observation(10, 0),
            ]
        )

        service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
            ),
            label_prefix="horizontal_drift_correction",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(len(session.swipes), 3)
        self.assertNotEqual(session.swipes[0][0], session.swipes[0][2])
        self.assertEqual(session.swipes[1][0], session.swipes[1][2])

    def test_execute_search_corrects_vertical_orthogonal_drift_with_horizontal_leg(self) -> None:
        """Corrects horizontal drift after a successful vertical cardinal move before finishing the checkpoint."""

        service, _observer, session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(6, 9),
                _make_world_map_observation(0, 9),
                _make_world_map_observation(0, 20),
            ]
        )

        service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 20), max_coordinate=(0, 20)),
                checkpoint_spacing=20,
            ),
            label_prefix="vertical_drift_correction",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(len(session.swipes), 3)
        self.assertEqual(session.swipes[0][0], session.swipes[0][2])
        self.assertNotEqual(session.swipes[1][0], session.swipes[1][2])

    def test_execute_search_fails_fast_on_wrong_sign_primary_axis_movement(self) -> None:
        """Fails the shared production movement path when a cardinal swipe moves the primary axis backward."""

        service, _observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(-4, 0),
            ]
        )

        with self.assertRaises(SelectorResolutionError) as error:
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                ),
                label_prefix="wrong_sign_primary",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["classification"], "unexpected_delta")
