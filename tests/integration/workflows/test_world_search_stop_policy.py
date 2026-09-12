"""World search stop policy: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.navigation.world_map_search import (
    ObservationBackedWorldMapCastleInspector,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchStopPolicy,
    WorldMapSearchStopReason,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.spatial import make_spatial_object
from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchStopPolicyTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search stop policy."""

    def test_stop_policy_prioritizes_first_confirmed_match_when_enabled(self) -> None:
        """Stops on the first confirmed match before consulting later match-count limits."""

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
                checkpoint_spacing=10,
                stop_policy=WorldMapSearchStopPolicy(max_matches=1, stop_on_first_confirmed_match=True),
            ),
            label_prefix="resource_search_match_limit_precedence",
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

        self.assertEqual(result.stop_reason, WorldMapSearchStopReason.FIRST_CONFIRMED_MATCH)

    def test_castle_inspector_fails_fast_when_no_focus_move_is_planned_before_target_is_visible(self) -> None:
        """Surfaces a focus-planning mismatch instead of silently skipping a still-hidden castle candidate."""

        service, _observer = self._build_runtime_service(observations=[])
        candidate = service.survey_recorder.ingest_capture(
            type(
                "Capture",
                (),
                {
                    "observation": _make_world_map_observation(
                        11,
                        10,
                        objects=(
                            make_spatial_object(
                                SpatialObjectKind.CASTLE,
                                name_text="Candidate",
                                confirmed_world_coordinate=(11, 10),
                            ),
                        ),
                    )
                },
            )()
        )[0]
        inspector = ObservationBackedWorldMapCastleInspector(
            screen_flows=self.flows,
            action_executor=service.action_executor,
            observation_service=service.observation_service,
            survey_recorder=service.survey_recorder,
            movement_step_budget=1,
        )

        with self.assertRaises(SelectorResolutionError):
            inspector._focus_candidate(
                _make_world_map_observation(10, 10),
                candidate,
                navigator=self.flows.world_map_navigator,
                label_prefix="hidden_candidate_focus",
                runtime_state={},
            )
