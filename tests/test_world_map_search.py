"""World-map search planning and execution tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, KeyEventAction
from pnc_automation.app.pnc.domain.observation import (
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldMapNavigator
from pnc_automation.app.pnc.navigation.world_map_index import WorldMapCastleQuery
from pnc_automation.app.pnc.navigation.world_map_search import (
    ObservationBackedWorldMapCastleInspector,
    WorldMapBounds,
    WorldMapCastleProfileQuery,
    WorldMapCoordinateDomain,
    WorldMapCoordinateMover,
    WorldMapCoordinateNavigator,
    WorldMapEdge,
    WorldMapMapCorner,
    WorldMapMovementPreferences,
    WorldMapMovementToolKind,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchService,
    WorldMapSearchStopPolicy,
    WorldMapSearchStopReason,
    adapt_world_map_search_matcher,
)
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.pnc.persistence.world_map_survey_debug_store import WorldMapSurveyDebugStore
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from tests.test_support import (
    FakeObservationService,
    FakeSession,
    build_logger,
    make_observation,
    make_spatial_object,
    make_spatial_surface,
)


class WorldMapSearchTests(unittest.TestCase):
    """Validates canonical world-map search planning, indexing, and castle enrichment."""

    def setUp(self) -> None:
        """Builds the shared flow planner, action executor, and temp artifact root."""

        self.flows = ScreenFlowPlanner()
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)

    def test_resolve_plan_uses_self_territory_origin_for_row_major_radius_search(self) -> None:
        """Defaults origin resolution to My Territory and produces a deterministic row-major bounded route."""

        service = WorldMapSearchService(screen_flows=self.flows)
        observation = _make_world_map_observation(
            100,
            100,
            objects=(
                make_spatial_object(
                    SpatialObjectKind.CASTLE,
                    name_text="My Territory",
                    relationship=SpatialObjectRelationship.SELF,
                    estimated_world_coordinate=(100, 100),
                ),
            ),
        )

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.CASTLE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                boundary=WorldMapSearchBoundary.radius_from_origin(10),
                checkpoint_spacing=10,
            ),
            observation,
        )

        self.assertEqual(plan.origin_coordinate, (100, 100))
        self.assertEqual(
            [checkpoint.coordinate for checkpoint in plan.route],
            [
                (90, 90),
                (100, 90),
                (110, 90),
                (90, 100),
                (100, 100),
                (110, 100),
                (90, 110),
                (100, 110),
                (110, 110),
            ],
        )

    def test_resolve_plan_builds_expanding_ring_route_from_explicit_origin(self) -> None:
        """Produces the deterministic expanding-ring order around an explicit center coordinate."""

        service = WorldMapSearchService(screen_flows=self.flows)
        observation = _make_world_map_observation(100, 100)

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.MONSTER),
                pattern=WorldMapSearchPattern.expanding_ring(),
                origin=WorldMapSearchOrigin.explicit_coordinate((100, 100)),
                boundary=WorldMapSearchBoundary.radius_from_origin(10),
                checkpoint_spacing=10,
            ),
            observation,
        )

        self.assertEqual(
            [checkpoint.coordinate for checkpoint in plan.route],
            [
                (100, 100),
                (90, 90),
                (100, 90),
                (110, 90),
                (110, 100),
                (110, 110),
                (100, 110),
                (90, 110),
                (90, 100),
            ],
        )

    def test_resolve_plan_builds_edge_band_route_from_full_map_bounds(self) -> None:
        """Restricts edge-band sweeps to the requested map edges while ordering checkpoints from the resolved origin."""

        service = WorldMapSearchService(screen_flows=self.flows)
        observation = _make_world_map_observation(0, 0)

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.edge_band_sweep(),
                origin=WorldMapSearchOrigin.map_edge_reference(WorldMapEdge.LEFT),
                boundary=WorldMapSearchBoundary.edge_band(
                    map_bounds=WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=20),
                    band_width_units=5,
                    edges=(WorldMapEdge.LEFT, WorldMapEdge.TOP),
                ),
                checkpoint_spacing=10,
            ),
            observation,
        )

        self.assertEqual(
            [checkpoint.coordinate for checkpoint in plan.route],
            [(0, 10), (0, 0), (0, 20), (10, 0), (20, 0)],
        )

    def test_coordinate_domain_models_addressable_coordinate_pairs_not_axes(self) -> None:
        """Treats every integer axis value as usable while rejecting impossible x/y pair parity."""

        domain = WorldMapCoordinateDomain.puzzles_and_conquest()

        self.assertTrue(domain.is_addressable((506, 1020)))
        self.assertTrue(domain.is_addressable((508, 1020)))
        self.assertTrue(domain.is_addressable((507, 1019)))
        self.assertTrue(domain.is_addressable((509, 1019)))
        self.assertFalse(domain.is_addressable((508, 1019)))
        self.assertEqual(domain.nearest_addressable((507, 1020)), (506, 1020))
        self.assertEqual(domain.nearest_addressable((0, 1023)), (0, 1022))
        self.assertEqual(domain.nearest_addressable((511, 0)), (511, 1))

    def test_row_major_route_uses_addressable_neighbors_on_one_world_map_row(self) -> None:
        """Skips impossible coordinate pairs while preserving valid same-row integer neighbors."""

        service = WorldMapSearchService(screen_flows=self.flows)
        observation = _make_world_map_observation(507, 1019)

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(507, 1019), max_coordinate=(511, 1019)),
                checkpoint_spacing=1,
            ),
            observation,
        )

        self.assertEqual(
            [checkpoint.coordinate for checkpoint in plan.route],
            [(507, 1019), (509, 1019), (511, 1019)],
        )

    def test_row_major_route_fails_when_rectangle_contains_no_addressable_pair(self) -> None:
        """Fails fast instead of snapping a no-tile rectangle outside its requested boundary."""

        service = WorldMapSearchService(screen_flows=self.flows)

        with self.assertRaises(SelectorResolutionError):
            service.resolve_plan(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.explicit_coordinate((508, 1019)),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(508, 1019), max_coordinate=(508, 1019)),
                    checkpoint_spacing=1,
                ),
                _make_world_map_observation(508, 1018),
            )

    def test_full_map_corner_origin_snaps_to_addressable_coordinate_pair(self) -> None:
        """Resolves impossible map-corner pairs to the closest real world-map coordinate pair."""

        service = WorldMapSearchService(screen_flows=self.flows)
        domain = WorldMapCoordinateDomain.puzzles_and_conquest()

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.map_corner(WorldMapMapCorner.UPPER_RIGHT),
                boundary=WorldMapSearchBoundary.full_map(domain.bounds),
                checkpoint_spacing=1024,
            ),
            _make_world_map_observation(0, 0),
        )

        self.assertEqual(plan.origin_coordinate, (511, 1))
        self.assertIn((511, 1), [checkpoint.coordinate for checkpoint in plan.route])
        self.assertIn((0, 1022), [checkpoint.coordinate for checkpoint in plan.route])
        self.assertTrue(all(domain.is_addressable(checkpoint.coordinate) for checkpoint in plan.route))

    def test_coordinate_mover_normalizes_unaddressable_target_before_planning(self) -> None:
        """Lets direct movement callers target raw magnifier coordinates while planning against the corrected tile."""

        mover = WorldMapCoordinateMover(
            observation_service=None,
            action_executor=None,
            navigator=WorldMapNavigator(focus_tolerance=0),
        )
        observation = _make_world_map_observation(506, 1020)

        result = mover.move_to_coordinate(
            observation,
            target_coordinate=(507, 1020),
            label_prefix="normalized_direct_move",
        )

        self.assertIs(result, observation)

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
        """Fails fast when a request requires coordinate-jump movement in a runtime that only supports swipes."""

        service = WorldMapSearchService(screen_flows=self.flows)

        with self.assertRaises(SelectorResolutionError):
            service.resolve_plan(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.COORDINATE_JUMP,)),
                ),
                _make_world_map_observation(0, 0),
            )

    def test_execute_search_fails_coordinate_jump_with_live_status_banner(self) -> None:
        """Surfaces the magnifier invalid-coordinate banner instead of retrying into a generic world-map parse error."""

        service, observer = self._build_runtime_service(
            observations=[
                make_observation(
                    ScreenType.UNKNOWN,
                    visible_ids=(UiElementId.PNC_STATUS_BANNER,),
                    visible_texts={UiElementId.PNC_STATUS_BANNER: "Invalid coordinates"},
                ),
            ]
        )
        service.coordinate_navigator = _FakeCoordinateJumpNavigator()

        with self.assertRaises(SelectorResolutionError) as error:
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.COORDINATE_JUMP,)),
                ),
                label_prefix="coordinate_jump_invalid",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["target_coordinate"], (10, 0))
        self.assertEqual(error.exception.details["status_banner"], "Invalid coordinates")
        self.assertEqual(observer.requests, [ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP)])

    def test_execute_search_accumulates_indexed_matches_across_checkpoints(self) -> None:
        """Uses one canonical checkpointed search loop that resolves matches from accumulated indexed survey state."""

        service, _observer = self._build_runtime_service(
            observations=[
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
        self.assertEqual(len(_observer.labels), 1)

    def test_execute_search_matches_player_name_from_visible_castle_label_without_profile_inspection(self) -> None:
        """Uses the visible map-side castle label directly instead of opening lord profile for player-name matching."""

        service, observer = self._build_runtime_service(observations=[])

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

    def test_execute_search_classifies_zero_delta_reactively_after_swipe(self) -> None:
        """Classifies an interior stall only after the attempted swipe reports no coordinate movement."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0),
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
                label_prefix="zero_delta_reactive",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["classification"], "interior_stall")
        self.assertEqual(observer.labels, ["zero_delta_reactive_move_0_0_post_action_1"])

    def test_execute_search_does_not_run_screen_flow_world_map_readiness_per_checkpoint(self) -> None:
        """Keeps checkpoint traversal inside the world-map surface after the caller supplies the entry proof."""

        flows = _CountingScreenFlowPlanner()
        observer = FakeObservationService(
            observations=[
                _make_world_map_observation(10, 0),
            ]
        )
        session = FakeSession()
        recorder = WorldMapSurveyRecorder(
            observation_service=observer,
            debug_store=WorldMapSurveyDebugStore(root=Path(self.temp_directory.name)),
        )
        service = WorldMapSearchService(
            screen_flows=flows,
            observation_service=observer,
            action_executor=ObservedActionExecutor(
                selector_registry=build_default_selector_registry(),
                action_executor=ActionExecutor(
                    session=session,
                    stable_click_delay_ms=0,
                    post_action_observe_delay_ms=0,
                    chat_stable_click_delay_ms=0,
                    chat_post_action_observe_delay_ms=0,
                    logger=build_logger(),
                    sleep=lambda _: None,
                ),
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            survey_recorder=recorder,
        )

        service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
            ),
            label_prefix="no_checkpoint_readiness",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(flows.ensure_world_map_ready_calls, 0)

    def test_execute_search_fails_fast_when_start_observation_is_not_proven_world_map(self) -> None:
        """Requires callers to enter and prove world map before invoking the reusable search engine."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0),
            ]
        )

        with self.assertRaises(SelectorResolutionError):
            service.execute_search(
                _search_request(
                    matcher=WorldMapCastleQuery(player_name="Alice"),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    checkpoint_spacing=10,
                ),
                label_prefix="castle_search_requires_world_map",
                start_observation=make_observation(ScreenType.PNC_HOME_CITY),
            )

        self.assertEqual(len(observer.observations), 1)

    def test_castle_inspector_ensure_world_map_closes_popup_before_reentering_world_map(self) -> None:
        """Uses the shared popup-dismissal flow before attempting world-map recovery during castle inspection."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(10, 0),
            ]
        )
        inspector = ObservationBackedWorldMapCastleInspector(
            screen_flows=self.flows,
            action_executor=service.action_executor,
            observation_service=observer,
            survey_recorder=service.survey_recorder,
        )

        result = inspector._ensure_world_map(
            make_observation(
                ScreenType.PNC_POPUP,
                visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                blocking_popup=True,
            ),
            label_prefix="popup_return_world",
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)

    def test_castle_inspector_ensure_world_map_recovers_unknown_world_map_chrome_before_proving_surface(self) -> None:
        """Uses the shared unknown-screen recovery flow before proving a world-map observation for castle inspection."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(12, 34),
            ]
        )
        inspector = ObservationBackedWorldMapCastleInspector(
            screen_flows=self.flows,
            action_executor=service.action_executor,
            observation_service=observer,
            survey_recorder=service.survey_recorder,
        )

        result = inspector._ensure_world_map(
            make_observation(
                ScreenType.UNKNOWN,
                visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,),
            ),
            label_prefix="unknown_return_world",
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(observer.requests, [ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP)])

    def test_stop_policy_prioritizes_first_confirmed_match_when_enabled(self) -> None:
        """Stops on the first confirmed match before consulting later match-count limits."""

        service, _observer = self._build_runtime_service(observations=[])

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

    def test_castle_profile_validation_query_opens_lord_profile_then_fails_fast_as_unimplemented(self) -> None:
        """Reaches lord profile for the dedicated profile-validation path before failing with the intentional unimplemented error."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(
                    0,
                    0,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.CASTLE,
                            name_text="UnknownCastle",
                            kingdom="K1",
                            confirmed_world_coordinate=(0, 0),
                            action_point=(77, 88),
                        ),
                    ),
                ),
                make_observation(
                    ScreenType.PNC_PLAYER_TERRITORY,
                    visible_ids=(
                        UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                        UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
                    ),
                ),
                make_observation(
                    ScreenType.PNC_PLAYER_PROFILE,
                    profile_player_name="Alice",
                    visible_ids=(
                        UiElementId.PNC_PLAYER_PROFILE_HEADER,
                        UiElementId.PNC_PLAYER_PROFILE_NAME_LABEL,
                    ),
                ),
                make_observation(
                    ScreenType.PNC_PLAYER_TERRITORY,
                    visible_ids=(
                        UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                        UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
                    ),
                ),
                _make_world_map_observation(0, 0),
            ]
        )
        inspector = ObservationBackedWorldMapCastleInspector(
            screen_flows=self.flows,
            action_executor=service.action_executor,
            observation_service=service.observation_service,
            survey_recorder=service.survey_recorder,
            movement_step_budget=1,
        )
        capture = service.survey_recorder.capture_checkpoint("visible_candidate")
        candidate = capture.updated_sightings[0]
        current = capture.capture.observation

        with self.assertRaises(SelectorResolutionError) as error:
            inspector.inspect_candidates(
                matcher=adapt_world_map_search_matcher(
                    WorldMapCastleProfileQuery(
                        castle=WorldMapCastleQuery(player_name="Alice", kingdom="K1"),
                    )
                ),
                candidates=(candidate,),
                current_observation=current,
                label_prefix="inspect_visible_candidate",
            )

        self.assertIn("gear validation is not implemented", str(error.exception).lower())
        self.assertEqual(observer.observations, [])

    def test_player_name_castle_enrichment_ranking_excludes_self_castles(self) -> None:
        """Does not inspect self-territory castles when resolving a remote player-name search."""
        service, _observer = self._build_runtime_service(observations=[])
        capture = service.survey_recorder.ingest_capture(
            type(
                "Capture",
                (),
                {
                    "observation": _make_world_map_observation(
                        0,
                        0,
                        objects=(
                            make_spatial_object(
                                SpatialObjectKind.CASTLE,
                                name_text="My Territory",
                                relationship=SpatialObjectRelationship.SELF,
                                confirmed_world_coordinate=(0, 0),
                            ),
                            make_spatial_object(
                                SpatialObjectKind.CASTLE,
                                name_text="UnknownCastle",
                                kingdom="K1",
                                confirmed_world_coordinate=(10, 0),
                            ),
                        ),
                    )
                },
            )()
        )
        self.assertEqual(len(capture), 2)
        self_sighting = next(sighting for sighting in capture if sighting.object_.relationship == SpatialObjectRelationship.SELF)
        other_sighting = next(sighting for sighting in capture if sighting.object_.relationship != SpatialObjectRelationship.SELF)
        matcher = adapt_world_map_search_matcher(
            WorldMapCastleProfileQuery(
                castle=WorldMapCastleQuery(player_name="Alice"),
            )
        )

        self.assertEqual(matcher.rank_castle_candidate(self_sighting), -1)
        self.assertGreaterEqual(matcher.rank_castle_candidate(other_sighting), 0)

    def _build_runtime_service(self, *, observations: list[object]) -> tuple[WorldMapSearchService, FakeObservationService]:
        """Builds one fully wired search service backed by fake observation and action services."""

        service, observer, _session = self._build_runtime_service_bundle(observations=observations)
        return service, observer

    def _build_runtime_service_bundle(
        self,
        *,
        observations: list[object],
    ) -> tuple[WorldMapSearchService, FakeObservationService, FakeSession]:
        """Builds one fully wired search service plus the fake session used to execute its actions."""

        observer = FakeObservationService(observations=observations)
        session = FakeSession()
        recorder = WorldMapSurveyRecorder(
            observation_service=observer,
            debug_store=WorldMapSurveyDebugStore(root=Path(self.temp_directory.name)),
        )
        service = WorldMapSearchService(
            screen_flows=self.flows,
            observation_service=observer,
            action_executor=ObservedActionExecutor(
                selector_registry=build_default_selector_registry(),
                action_executor=ActionExecutor(
                    session=session,
                    stable_click_delay_ms=0,
                    post_action_observe_delay_ms=0,
                    chat_stable_click_delay_ms=0,
                    chat_post_action_observe_delay_ms=0,
                    logger=build_logger(),
                    sleep=lambda _: None,
                ),
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            survey_recorder=recorder,
        )
        return service, observer, session


class _CountingScreenFlowPlanner(ScreenFlowPlanner):
    """Tracks root world-map readiness calls while preserving normal screen-flow behavior."""

    def __init__(self) -> None:
        """Initializes the counter and base planner dependencies."""

        super().__init__()
        self.ensure_world_map_ready_calls = 0

    def ensure_world_map_ready(self, observation: object) -> list[object]:
        """Counts calls to the root readiness seam."""

        self.ensure_world_map_ready_calls += 1
        return super().ensure_world_map_ready(observation)


class _FakeCoordinateJumpNavigator(WorldMapCoordinateNavigator):
    """Plans one synthetic coordinate jump action for search error-handling tests."""

    def is_supported(self) -> bool:
        """Returns that the fake coordinate-jump primitive is available."""

        return True

    def plan_jump(self, *, target: tuple[int, int], current_observation: Observation) -> list[ActionRequest]:
        """Returns one observed action that requests a narrow world-map follow-up."""

        del target, current_observation
        return [
            KeyEventAction(
                key_code="KEYCODE_ENTER",
                observe_after=True,
                follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
            )
        ]


def _search_request(
    *,
    matcher: object,
    pattern: WorldMapSearchPattern,
    checkpoint_spacing: int,
    origin: WorldMapSearchOrigin | None = None,
    boundary: WorldMapSearchBoundary | None = None,
    movement_preferences: WorldMapMovementPreferences | None = None,
    stop_policy: WorldMapSearchStopPolicy | None = None,
) -> object:
    """Builds one search request with concise defaults for tests."""

    from pnc_automation.app.pnc.navigation.world_map_search import WorldMapSearchRequest

    return WorldMapSearchRequest(
        matcher=matcher,
        stop_policy=WorldMapSearchStopPolicy() if stop_policy is None else stop_policy,
        pattern=pattern,
        checkpoint_spacing=checkpoint_spacing,
        origin=origin,
        boundary=boundary,
        movement_preferences=WorldMapMovementPreferences() if movement_preferences is None else movement_preferences,
    )


def _make_world_map_observation(
    x: int,
    y: int,
    *,
    objects: tuple[object, ...] = (),
) -> object:
    """Builds one synthetic world-map observation with the requested viewport and objects."""

    return make_observation(
        ScreenType.PNC_WORLD_MAP,
        visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_SEARCH_BUTTON),
        spatial_surface=make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=x,
            y=y,
            objects=objects,
        ),
    )


if __name__ == "__main__":
    unittest.main()
