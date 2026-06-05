"""World-map search planning and execution tests."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, ActionTimingProfile, KeyEventAction, TapPointAction
from pnc_automation.app.pnc.domain.observation import (
    Observation,
    ObservedTextFieldState,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldCoordinate, WorldMapNavigator
from pnc_automation.app.pnc.navigation.world_map_overview_projection import project_world_coordinate_to_overview_point
from pnc_automation.app.pnc.navigation.world_map_index import WorldMapCastleQuery
from pnc_automation.app.pnc.navigation.world_map_search import (
    ObservationBackedWorldMapCastleInspector,
    TraversalStridePolicy,
    WorldMapBounds,
    WorldMapCastleProfileQuery,
    WorldMapCoordinateDomain,
    WorldMapCoordinateDialogState,
    WorldMapCoordinateJumpPlan,
    WorldMapCoordinateMover,
    WorldMapCoordinateNavigator,
    WorldMapMapCorner,
    WorldMapMovementPolicy,
    WorldMapMovementPreferences,
    WorldMapMovementToolKind,
    WorldMapOverviewNavigator,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchPatternKind,
    WorldMapSearchService,
    WorldMapSearchStopPolicy,
    WorldMapSearchStopReason,
    WorldMapTraversalCorner,
    _resolve_cardinal_sweep_leg_target,
    adapt_world_map_search_matcher,
    all_of_world_map_search,
    any_of_world_map_search,
    world_map_movement_trace_document,
)
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.pnc.persistence.world_map_survey_debug_store import WorldMapSurveyDebugStore
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.runtime.observation_artifacts import ObservationArtifactKind, observation_artifact_selection
from pnc_automation.core.errors import SelectorResolutionError
from tests.test_support import (
    FakeObservationService,
    FakeSession,
    build_logger,
    make_observation,
    make_visible,
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

    def test_resolve_plan_builds_perimeter_route_from_full_map_bounds(self) -> None:
        """Builds one explicit perimeter traversal around the requested bounds."""

        service = WorldMapSearchService(screen_flows=self.flows)
        observation = _make_world_map_observation(0, 0)

        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.perimeter_ring_sweep(start_corner=WorldMapTraversalCorner.UPPER_LEFT),
                origin=WorldMapSearchOrigin.map_corner(WorldMapMapCorner.UPPER_LEFT),
                boundary=WorldMapSearchBoundary.full_map(
                    WorldMapBounds(min_x=0, min_y=0, max_x=20, max_y=20),
                ),
                checkpoint_spacing=10,
            ),
            observation,
        )

        self.assertEqual(
            [checkpoint.coordinate for checkpoint in plan.route],
            [(0, 0), (10, 0), (20, 0), (20, 10), (20, 20), (10, 20), (0, 20), (0, 10)],
        )

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

    def test_coordinate_mover_fails_when_direct_target_is_outside_domain(self) -> None:
        """Rejects direct movement targets outside the kingdom coordinate domain."""

        mover = WorldMapCoordinateMover(
            observation_service=None,
            action_executor=None,
            navigator=WorldMapNavigator(focus_tolerance=0),
        )

        with self.assertRaises(SelectorResolutionError):
            mover.move_to_coordinate(
                _make_world_map_observation(0, 0),
                target_coordinate=(0, 5000),
                label_prefix="invalid_direct_move",
            )

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

        self.assertEqual(plan.origin_coordinate, (510, 0))
        self.assertIn((510, 0), [checkpoint.coordinate for checkpoint in plan.route])
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

    def test_coordinate_mover_can_cap_one_axis_delta_per_observed_leg(self) -> None:
        """Lets callers configure coordinate granularity instead of always targeting the full remaining axis delta."""

        leg_target = _resolve_cardinal_sweep_leg_target(
            current=_make_world_map_observation(100, 200),
            target_coordinate=(109, 200),
            focus_tolerance=1,
            max_axis_delta_per_leg=4,
        )

        self.assertIsNotNone(leg_target)
        assert leg_target is not None
        self.assertEqual((leg_target.x, leg_target.y), (104, 200))

    def test_coordinate_mover_rejects_granularity_that_is_not_above_focus_tolerance(self) -> None:
        """Fails fast when granularity would collapse capped legs into the navigator's in-tolerance no-op band."""

        with self.assertRaises(SelectorResolutionError) as error:
            WorldMapCoordinateMover(
                observation_service=None,
                action_executor=None,
                navigator=WorldMapNavigator(focus_tolerance=1),
                movement_policy=WorldMapMovementPolicy(traverse_max_axis_delta_per_leg=1),
            )

        self.assertIn("must be greater than the navigator focus_tolerance", str(error.exception))
        self.assertEqual(error.exception.details["field_name"], "traverse_max_axis_delta_per_leg")
        self.assertEqual(error.exception.details["value"], 1)
        self.assertEqual(error.exception.details["focus_tolerance"], 1)

    def test_world_map_navigation_swipes_use_dedicated_movement_follow_up_and_timing(self) -> None:
        """Uses the dedicated movement pacing/follow-up contract so world-map swipes can be tuned independently."""

        actions = self.flows.world_map_navigator.plan_focus_coordinate(
            _make_world_map_observation(100, 100),
            WorldCoordinate(x=110, y=100),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].timing_profile, ActionTimingProfile.WORLD_MAP_MOVEMENT)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_movement_follow_up())

    def test_coordinate_mover_records_json_ready_step_traces_in_runtime_state(self) -> None:
        """Persists direct-movement timing and coordinate details in shared runtime state for live comparison tools."""

        service, observer, _session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(10, 0),
            ]
        )
        mover = service.coordinate_mover_for_runtime()
        mover.max_axis_delta_per_leg = 10
        runtime_state: dict[str, object] = {}

        end = mover.move_to_coordinate(
            _make_world_map_observation(0, 0),
            target_coordinate=(10, 0),
            label_prefix="trace_capture",
            runtime_state=runtime_state,
        )

        document = world_map_movement_trace_document(runtime_state)
        self.assertEqual(end.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate, (10, 0))
        self.assertEqual(len(document["step_traces"]), 1)
        trace = document["step_traces"][0]
        self.assertEqual(trace["before_coordinate"], [0, 0])
        self.assertEqual(trace["leg_target"], [10, 0])
        self.assertEqual(trace["after_coordinate"], [10, 0])
        self.assertEqual(trace["requested_coordinate"], [10, 0])
        self.assertEqual(trace["normalized_target_coordinate"], [10, 0])
        self.assertEqual(trace["max_axis_delta_per_leg"], 10)
        self.assertEqual(trace["gesture_primitive"], "swipe")
        self.assertEqual(trace["classification"], "moved")
        self.assertGreaterEqual(trace["action_elapsed_ms"], 0.0)
        self.assertGreaterEqual(trace["prove_elapsed_ms"], 0.0)
        self.assertEqual(observer.requests, [ObservationRequest.world_map_movement_follow_up()])

    def test_move_to_checkpoint_uses_checkpoint_analysis_scope_on_final_landing_without_recapture(self) -> None:
        """Uses the richer checkpoint-analysis observation on the final leg instead of proof then recapturing the same viewport."""

        service, observer, _session = self._build_runtime_service_bundle(
            observations=[
                _make_world_map_observation(10, 0),
            ]
        )
        start = _make_world_map_observation(0, 0)
        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
            ),
            start,
        )

        end = service.move_to_checkpoint(
            start,
            plan=plan,
            step=plan.execution_plan.steps[0],
            label_prefix="checkpoint_analysis_arrival",
            runtime_state={},
        )

        self.assertEqual(end.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate, (10, 0))
        self.assertEqual(observer.requests, [ObservationRequest.world_map_checkpoint_analysis()])

    def test_resolved_plan_caches_route_for_compatibility_consumers(self) -> None:
        """Materializes the compatibility route once so auxiliary readers do not keep rebuilding it."""

        service = WorldMapSearchService(screen_flows=self.flows)
        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(20, 0)),
                checkpoint_spacing=10,
            ),
            _make_world_map_observation(0, 0),
        )

        self.assertIs(plan.route, plan.route)

    def test_move_to_checkpoint_persists_failure_artifact_and_logs_failed_swipe_leg(self) -> None:
        """Captures one failure screenshot and one explicit failed-leg diagnostic when swipe proof refresh exhausts."""

        logger, records = _build_recording_logger("world_map_search_failed_leg")
        service, observer, _session = self._build_runtime_service_bundle(
            observations=[
                make_observation(ScreenType.PNC_WORLD_MAP),
                make_observation(ScreenType.PNC_WORLD_MAP),
                make_observation(ScreenType.PNC_WORLD_MAP),
                _make_world_map_observation(0, 0),
            ],
            logger=logger,
        )
        start = _make_world_map_observation(0, 0)
        plan = service.resolve_plan(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
            ),
            start,
        )
        runtime_state: dict[str, object] = {}

        with self.assertRaises(SelectorResolutionError):
            service.move_to_checkpoint(
                start,
                plan=plan,
                step=plan.execution_plan.steps[0],
                label_prefix="checkpoint_failure",
                runtime_state=runtime_state,
            )
        service.flush_runtime_diagnostics(runtime_state=runtime_state)

        screenshot_selection = observation_artifact_selection(ObservationArtifactKind.SCREENSHOT)
        self.assertEqual(observer.artifact_selections[0], screenshot_selection)
        self.assertEqual(observer.artifact_selections[-1], screenshot_selection)
        self.assertTrue(observer.labels[-1].endswith("checkpoint_failure_failure_0"))
        failure_records = [record for record in records if record.msg == "World-map movement step failed."]
        self.assertEqual(len(failure_records), 1)
        self.assertEqual(failure_records[0].step_index, 0)

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

    def test_search_service_caches_runtime_coordinate_mover_for_live_tuning(self) -> None:
        """Reuses one runtime coordinate mover so live helpers can tune granularity on the shared instance."""

        service, _observer = self._build_runtime_service(observations=[])

        first = service.coordinate_mover_for_runtime()
        first.max_axis_delta_per_leg = 5
        second = service.coordinate_mover_for_runtime()

        self.assertIs(first, second)
        self.assertEqual(second.max_axis_delta_per_leg, 5)

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
        """Fails fast when a request requires a placeholder movement primitive in a swipe-only runtime."""

        service = WorldMapSearchService(screen_flows=self.flows)
        service.coordinate_navigator.supported = False
        service.overview_navigator.movement_supported = False

        for movement_tool in (WorldMapMovementToolKind.COORDINATE_JUMP, WorldMapMovementToolKind.OVERVIEW_SEED):
            with self.subTest(movement_tool=movement_tool):
                with self.assertRaises(SelectorResolutionError):
                    service.resolve_plan(
                        _search_request(
                            matcher=SpatialObjectQuery(
                                surface_type=SpatialSurfaceType.WORLD_MAP,
                                kind=SpatialObjectKind.RESOURCE_NODE,
                            ),
                            pattern=WorldMapSearchPattern.row_major_sweep(),
                            origin=WorldMapSearchOrigin.current_viewport(),
                            boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
                            checkpoint_spacing=10,
                            movement_preferences=WorldMapMovementPreferences((movement_tool,)),
                        ),
                        _make_world_map_observation(0, 0),
                    )

    def test_coordinate_navigator_plan_jump_rejects_out_of_domain_target(self) -> None:
        """Fails fast before typing when the raw target lies outside the world-map domain."""

        navigator = WorldMapCoordinateNavigator()

        with self.assertRaises(SelectorResolutionError):
            navigator.plan_jump(
                target=(512, 1),
                current_observation=_make_world_map_observation(10, 10),
            )

    def test_coordinate_navigator_plan_jump_normalizes_targets_and_commits_each_numeric_field(self) -> None:
        """Uses one canonical selector sequence and commits each edited field before submit."""

        navigator = WorldMapCoordinateNavigator()

        plan = navigator.plan_jump(
            target=(511, 0),
            current_observation=_make_world_map_observation(10, 10),
        )

        self.assertEqual(plan.normalized_target_coordinate, (510, 0))
        self.assertIsInstance(plan.open_action, ActionRequest)
        self.assertEqual(
            [type(action).__name__ for action in plan.fill_actions],
            ["InputTextAction", "KeyEventAction", "InputTextAction", "KeyEventAction"],
        )
        self.assertEqual(
            [getattr(action, "selector_id", None) for action in plan.fill_actions if hasattr(action, "selector_id")],
            [
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
            ],
        )
        self.assertTrue(all(action.key_code == "KEYCODE_ENTER" for action in plan.fill_actions if isinstance(action, KeyEventAction)))

    def test_coordinate_navigator_requires_committed_dialog_values_before_submit(self) -> None:
        """Proves the filled dialog state from committed K/X/Y values before pressing Go."""

        navigator = WorldMapCoordinateNavigator()
        plan = navigator.plan_jump(
            target=(511, 2),
            current_observation=_make_world_map_observation(10, 10),
        )
        initial_state = navigator.require_dialog_state(_make_coordinate_dialog_observation(157, 10, 10))
        current_state = navigator.require_pre_submit_state(
            _make_coordinate_dialog_observation(157, 510, 2),
            plan=plan,
            initial_state=initial_state,
        )

        self.assertEqual(current_state, WorldMapCoordinateDialogState(kingdom=157, coordinate=(510, 2)))

    def test_overview_parse_support_does_not_enable_overview_seed(self) -> None:
        """Keeps parse-only overview support separate from overview-seed movement selection."""

        service = WorldMapSearchService(screen_flows=self.flows)
        service.overview_navigator = WorldMapOverviewNavigator(bounds_parsing_supported=True, movement_supported=False)

        with self.assertRaises(SelectorResolutionError):
            service.resolve_plan(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.OVERVIEW_SEED,)),
                ),
                _make_world_map_observation(0, 0),
            )

    def test_overview_navigator_parses_bounds_and_corner_marker_context(self) -> None:
        """Projects known-corner overview marker fixtures back into the world-map coordinate domain."""

        navigator = WorldMapOverviewNavigator()

        upper_left = navigator.parse_context(_make_world_map_overview_observation(marker_point=(20, 40)))
        lower_right = navigator.parse_context(_make_world_map_overview_observation(marker_point=(179, 159)))

        self.assertEqual(navigator.resolve_world_bounds(_make_world_map_overview_observation(marker_point=(100, 100))), WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023))
        self.assertEqual(upper_left.current_viewport_coordinate, (0, 0))
        self.assertEqual(lower_right.current_viewport_coordinate, (511, 1023))

    def test_overview_navigator_open_follow_up_carries_current_coordinate_hint(self) -> None:
        """Carries the current world coordinate into the overview follow-up so live marker detection can prefer the expected cluster."""

        navigator = WorldMapOverviewNavigator()
        observation = _make_world_map_observation(256, 512)

        actions = navigator.plan_open(observation)

        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.world_map_overview_follow_up(expected_coordinate=(256, 512)),
        )

    def test_overview_navigator_open_follow_up_keeps_coordinate_hint_optional(self) -> None:
        """Keeps overview opening usable when the map surface is proven but its coordinate bar is temporarily unreadable."""

        navigator = WorldMapOverviewNavigator()
        observation = _make_world_map_observation(0, 0, coordinate_addressable=False)

        actions = navigator.plan_open(observation)

        self.assertEqual(actions[0].follow_up_request, ObservationRequest.world_map_overview_follow_up())

    def test_coordinate_jump_plan_does_not_require_current_coordinate_for_non_noop_move(self) -> None:
        """Keeps coordinate-dialog planning available when the world map is proven but the viewport coordinate is unavailable."""

        navigator = WorldMapCoordinateNavigator()

        plan = navigator.plan_jump(
            target=(10, 0),
            current_observation=_make_world_map_observation(0, 0, coordinate_addressable=False),
        )

        self.assertTrue(plan.requires_execution)
        self.assertIsNotNone(plan.open_action)

    def test_overview_navigator_projects_interior_marker_and_recenter_click(self) -> None:
        """Uses the same marker calibration for interior parse evidence and click-to-recenter planning."""

        navigator = WorldMapOverviewNavigator()
        marker_point = _overview_marker_point_for_coordinate((256, 512))
        context = navigator.parse_context(_make_world_map_overview_observation(marker_point=marker_point))
        actions = navigator.plan_recenter(
            _make_world_map_overview_observation(marker_point=marker_point),
            target_coordinate=(256, 512),
        )

        self.assertLessEqual(abs(context.current_viewport_coordinate[0] - 256), 1)
        self.assertLessEqual(abs(context.current_viewport_coordinate[1] - 512), 4)
        self.assertIsInstance(actions[0], TapPointAction)

    def test_overview_navigator_recenter_uses_dedicated_click_region(self) -> None:
        """Projects recenter clicks through the reviewed click region instead of the tighter marker-projection region."""

        navigator = WorldMapOverviewNavigator()
        observation = _make_world_map_overview_observation(
            marker_point=(100, 100),
            recenter_region_bounds=(0, 0, 200, 200),
        )

        actions = navigator.plan_recenter(observation, target_coordinate=(511, 0))

        self.assertEqual((actions[0].x, actions[0].y), (199, 0))

    def test_overview_navigator_resolves_bounds_without_marker(self) -> None:
        """Keeps parse-only overview bounds support independent from temporary marker-detection failures."""

        navigator = WorldMapOverviewNavigator()

        bounds = navigator.resolve_world_bounds(_make_world_map_overview_observation(marker_point=None))

        self.assertEqual(bounds, WorldMapBounds(min_x=0, min_y=0, max_x=511, max_y=1023))

    def test_overview_navigator_context_requires_marker(self) -> None:
        """Fails marker-aware context parsing when the viewport marker is absent from the overview evidence."""

        navigator = WorldMapOverviewNavigator()

        with self.assertRaises(SelectorResolutionError):
            navigator.parse_context(_make_world_map_overview_observation(marker_point=None))

    def test_overview_navigator_distinguishes_close_recenter_and_kingdom_list_exit_paths(self) -> None:
        """Keeps the three reviewed overview exits on distinct declarative plans."""

        navigator = WorldMapOverviewNavigator()
        observation = _make_world_map_overview_observation(marker_point=(100, 100))

        close_actions = navigator.plan_close_in_place(observation)
        kingdom_list_actions = navigator.plan_open_kingdom_list(observation)

        self.assertEqual(close_actions[0].selector_id, UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON)
        self.assertEqual(kingdom_list_actions[0].selector_id, UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON)

    def test_overview_close_and_kingdom_list_paths_do_not_require_marker_parse(self) -> None:
        """Keeps non-recenter overview exits usable even when marker parsing evidence is temporarily absent."""

        navigator = WorldMapOverviewNavigator()
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP_OVERVIEW,
            visible_ids=(
                UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON,
                UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON,
            ),
        )

        close_actions = navigator.plan_close_in_place(observation)
        kingdom_list_actions = navigator.plan_open_kingdom_list(observation)

        self.assertEqual(close_actions[0].selector_id, UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON)
        self.assertEqual(kingdom_list_actions[0].selector_id, UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON)

    def test_execute_search_fails_coordinate_jump_with_live_status_banner(self) -> None:
        """Surfaces the magnifier invalid-coordinate banner instead of retrying into a generic world-map parse error."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_coordinate_dialog_observation(157, 10, 0),
                _make_coordinate_dialog_observation(157, 10, 0, status_banner_text="Invalid coordinates"),
                _make_coordinate_dialog_observation(157, 10, 0, status_banner_text="Invalid coordinates"),
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
        self.assertEqual(
            observer.requests,
            [
                ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ObservationRequest.world_map_coordinate_jump_follow_up(),
                ObservationRequest.full_runtime_default(),
            ],
        )
        self.assertTrue(observer.labels[-1].endswith("coordinate_jump_invalid_move_0_failure"))

    def test_execute_search_fails_no_action_coordinate_jump_when_not_at_target(self) -> None:
        """Verifies a no-op coordinate jump before treating the current viewport as the checkpoint."""

        service, _observer = self._build_runtime_service(observations=[])
        service.coordinate_navigator = _NoActionCoordinateJumpNavigator()

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
                label_prefix="coordinate_jump_no_action_wrong",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["target_coordinate"], (10, 0))
        self.assertEqual(error.exception.details["current_coordinate"], (0, 0))

    def test_execute_search_fails_coordinate_jump_that_lands_at_wrong_coordinate(self) -> None:
        """Rejects coordinate-dialog movement when the resulting viewport proves a different coordinate."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_coordinate_dialog_observation(157, 10, 0),
                _make_world_map_observation(8, 0),
                _make_world_map_observation(8, 0),
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
                label_prefix="coordinate_jump_wrong_landing",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["target_coordinate"], (10, 0))
        self.assertEqual(error.exception.details["current_coordinate"], (8, 0))
        self.assertEqual(observer.artifact_selections[-1], observation_artifact_selection(ObservationArtifactKind.SCREENSHOT))
        self.assertTrue(observer.labels[-1].endswith("coordinate_jump_wrong_landing_move_0_failure"))

    def test_execute_search_fails_coordinate_jump_when_landing_lacks_world_map_surface(self) -> None:
        """Requires a proven world-map surface before checkpoint ingestion after coordinate-dialog movement."""

        service, _observer = self._build_runtime_service(
            observations=[
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_coordinate_dialog_observation(157, 10, 0),
                make_observation(ScreenType.PNC_WORLD_MAP),
                make_observation(ScreenType.PNC_WORLD_MAP),
                make_observation(ScreenType.PNC_WORLD_MAP),
            ]
        )
        service.coordinate_navigator = _FakeCoordinateJumpNavigator()

        with self.assertRaises(SelectorResolutionError):
            service.execute_search(
                _search_request(
                    matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                    checkpoint_spacing=10,
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.COORDINATE_JUMP,)),
                ),
                label_prefix="coordinate_jump_missing_surface",
                start_observation=_make_world_map_observation(0, 0),
            )

    def test_execute_search_accepts_coordinate_jump_landing_at_normalized_target(self) -> None:
        """Verifies coordinate-jump landings against the normalized in-domain checkpoint coordinate."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_coordinate_dialog_observation(157, 0, 0),
                _make_coordinate_dialog_observation(157, 510, 0),
                _make_world_map_observation(510, 0),
            ]
        )
        service.coordinate_navigator = _FakeCoordinateJumpNavigator()

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.explicit_coordinate((511, 0)),
                checkpoint_spacing=10,
                movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.COORDINATE_JUMP,)),
            ),
            label_prefix="coordinate_jump_normalized_landing",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(result.visited_checkpoints[0].coordinate, (510, 0))
        self.assertEqual(
            observer.artifact_selections,
            [
                frozenset(),
                frozenset(),
                observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
            ],
        )

    def test_execute_search_moves_with_overview_seed_and_verifies_landing(self) -> None:
        """Executes the full overview open-plus-recenter flow and proves the landed world-map coordinate."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_overview_observation(marker_point=_overview_marker_point_for_coordinate((0, 0))),
                _make_world_map_observation(10, 0),
            ]
        )

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
                movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.OVERVIEW_SEED,)),
            ),
            label_prefix="overview_seed_move",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual(result.visited_checkpoints[0].coordinate, (10, 0))
        self.assertEqual(
            observer.requests,
            [
                ObservationRequest.world_map_overview_follow_up(expected_coordinate=(0, 0)),
                ObservationRequest.world_map_overview_exit_follow_up(),
            ],
        )
        self.assertEqual(
            observer.artifact_selections,
            [
                frozenset(),
                observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
            ],
        )

    def test_execute_search_rejects_overview_seed_when_landing_is_wrong(self) -> None:
        """Fails overview-assisted movement when the returned world-map viewport proves the wrong landing coordinate."""

        service, _observer = self._build_runtime_service(
            observations=[
                _make_world_map_overview_observation(marker_point=_overview_marker_point_for_coordinate((0, 0))),
                _make_world_map_observation(8, 0),
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
                    movement_preferences=WorldMapMovementPreferences((WorldMapMovementToolKind.OVERVIEW_SEED,)),
                ),
                label_prefix="overview_seed_wrong_landing",
                start_observation=_make_world_map_observation(0, 0),
            )

        self.assertEqual(error.exception.details["target_coordinate"], (10, 0))
        self.assertEqual(error.exception.details["current_coordinate"], (8, 0))

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

    def test_execute_search_recovers_from_one_interior_stall_before_reaching_the_checkpoint(self) -> None:
        """Lets the shared mover widen one stagnant swipe attempt instead of aborting before the next calibrated retry."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 0),
            ]
        )

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(10, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
            ),
            label_prefix="one_stall_then_success",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual([checkpoint.coordinate for checkpoint in result.visited_checkpoints], [(10, 0)])
        self.assertEqual(
            observer.labels,
            [
                "one_stall_then_success_move_0_0_post_action_1",
                "one_stall_then_success_move_0_1_post_action_1",
            ],
        )

    def test_execute_search_reports_bounded_interior_stall_retry_exhaustion_with_swipe_diagnostics(self) -> None:
        """Fails once the shared mover exhausts stagnant retries and preserves the exact swipe evidence for live diagnosis."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0, artifact_path=Path("artifacts/stall_1.png")),
                _make_world_map_observation(0, 0, artifact_path=Path("artifacts/stall_2.png")),
                _make_world_map_observation(0, 0, artifact_path=Path("artifacts/stall_3.png")),
                _make_world_map_observation(0, 0, artifact_path=Path("artifacts/stall_failure.png")),
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
        self.assertEqual(error.exception.details["artifact_path"], str(Path("artifacts/stall_3.png")))
        self.assertEqual(len(error.exception.details["swipe_points"]), 4)
        self.assertIn("stagnant_retry_failure", error.exception.details)
        self.assertEqual(
            observer.labels,
            [
                "zero_delta_reactive_move_0_0_post_action_1",
                "zero_delta_reactive_move_0_1_post_action_1",
                "zero_delta_reactive_move_0_2_post_action_1",
                "zero_delta_reactive_move_0_failure_3",
            ],
        )

    def test_execute_search_supports_explicitly_larger_coordinate_focus_budget_for_long_sweeps(self) -> None:
        """Allows long-running sweep traversal to keep advancing past the default bounded leg budget when configured."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(10, 0),
                _make_world_map_observation(20, 0),
                _make_world_map_observation(30, 0),
                _make_world_map_observation(40, 0),
                _make_world_map_observation(50, 0),
                _make_world_map_observation(60, 0),
                _make_world_map_observation(70, 0),
                _make_world_map_observation(80, 0),
                _make_world_map_observation(90, 0),
            ]
        )
        service.movement_step_budget = 10

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(90, 0), max_coordinate=(90, 0)),
                checkpoint_spacing=10,
            ),
            label_prefix="extended_coordinate_focus_budget",
            start_observation=_make_world_map_observation(0, 0),
        )

        self.assertEqual([checkpoint.coordinate for checkpoint in result.visited_checkpoints], [(90, 0)])
        self.assertEqual(len(observer.labels), 9)
        self.assertEqual(service.coordinate_mover_for_runtime().movement_step_budget, 10)

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

    def test_all_of_profile_validation_matcher_inspects_eligible_castle_candidates(self) -> None:
        """Preserves castle-inspection behavior when profile validation is composed with map-side constraints."""

        service, observer = self._build_runtime_service(
            observations=[
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
        service.castle_inspector = ObservationBackedWorldMapCastleInspector(
            screen_flows=self.flows,
            action_executor=service.action_executor,
            observation_service=service.observation_service,
            survey_recorder=service.survey_recorder,
            movement_step_budget=1,
        )

        with self.assertRaises(SelectorResolutionError) as error:
            service.execute_search(
                _search_request(
                    matcher=all_of_world_map_search(
                        WorldMapCastleQuery(kingdom="K1"),
                        WorldMapCastleProfileQuery(
                            castle=WorldMapCastleQuery(player_name="Alice", kingdom="K1"),
                        ),
                    ),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    checkpoint_spacing=10,
                ),
                label_prefix="composed_profile_validation",
                start_observation=_make_world_map_observation(
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
            )

        self.assertIn("gear validation is not implemented", str(error.exception).lower())
        self.assertEqual(observer.observations, [])

    def test_any_of_profile_validation_matcher_ranks_candidates_from_profile_child(self) -> None:
        """Lets disjunctive profile-validation matchers advertise and rank castle candidates."""

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
                                name_text="UnknownCastle",
                                kingdom="K1",
                                confirmed_world_coordinate=(0, 0),
                            ),
                        ),
                    )
                },
            )()
        )
        matcher = any_of_world_map_search(
            SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.MONSTER),
            WorldMapCastleProfileQuery(
                castle=WorldMapCastleQuery(player_name="Alice", kingdom="K1"),
            ),
        )

        self.assertTrue(matcher.supports_castle_enrichment())
        self.assertGreaterEqual(matcher.rank_castle_candidate(capture[0]), 0)

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
        logger: logging.LoggerAdapter | None = None,
    ) -> tuple[WorldMapSearchService, FakeObservationService, FakeSession]:
        """Builds one fully wired search service plus the fake session used to execute its actions."""

        runtime_logger = build_logger() if logger is None else logger
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
                    logger=runtime_logger,
                    sleep=lambda _: None,
                ),
                logger=runtime_logger,
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

    def plan_jump(self, *, target: tuple[int, int], current_observation: Observation) -> WorldMapCoordinateJumpPlan:
        """Returns one synthetic staged jump plan for search error-handling tests."""

        del current_observation
        return WorldMapCoordinateJumpPlan(
            normalized_target_coordinate=target,
            open_action=KeyEventAction(
                key_code="KEYCODE_ENTER",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            ),
            fill_actions=(
                KeyEventAction(
                    key_code="KEYCODE_ENTER",
                    observe_after=True,
                    follow_up_request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
                ),
            ),
            submit_action=KeyEventAction(
                key_code="KEYCODE_ENTER",
                observe_after=True,
                follow_up_request=ObservationRequest.world_map_coordinate_jump_follow_up(),
            ),
        )


class _NoActionCoordinateJumpNavigator(WorldMapCoordinateNavigator):
    """Models a supported coordinate-jump runtime that reports the target is already focused."""

    def is_supported(self) -> bool:
        """Returns that the fake coordinate-jump primitive is available."""

        return True

    def plan_jump(self, *, target: tuple[int, int], current_observation: Observation) -> WorldMapCoordinateJumpPlan:
        """Returns a no-op plan so the search service must verify the current viewport."""

        del current_observation
        return WorldMapCoordinateJumpPlan(normalized_target_coordinate=target)


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
        traversal_stride_policy=TraversalStridePolicy.symmetric(checkpoint_spacing),
        origin=origin,
        boundary=boundary,
        movement_preferences=WorldMapMovementPreferences() if movement_preferences is None else movement_preferences,
    )


def _make_world_map_observation(
    x: int,
    y: int,
    *,
    objects: tuple[object, ...] = (),
    coordinate_addressable: bool = True,
    artifact_path: Path | None = None,
) -> object:
    """Builds one synthetic world-map observation with the requested viewport and objects."""

    if coordinate_addressable:
        spatial_surface = make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=x,
            y=y,
            objects=objects,
            metadata={"coordinate_text": f"X:{x} Y:{y}"},
        )
    else:
        spatial_surface = SpatialSurfaceObservation(
            surface_type=SpatialSurfaceType.WORLD_MAP,
            viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
            objects=objects,
        )
    return make_observation(
        ScreenType.PNC_WORLD_MAP,
        visible_ids=(
            UiElementId.PNC_WORLD_HOME_NAV,
            UiElementId.PNC_WORLD_SEARCH_BUTTON,
            UiElementId.PNC_WORLD_EXPAND_BUTTON,
        ),
        spatial_surface=spatial_surface,
        artifact_path=artifact_path,
    )


def _make_coordinate_dialog_observation(
    kingdom: int,
    x: int,
    y: int,
    *,
    status_banner_text: str | None = None,
) -> Observation:
    """Builds one synthetic coordinate-dialog observation with committed field state."""

    visible_ids = [
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_KEYBOARD_OK_BUTTON,
    ]
    if status_banner_text is not None:
        visible_ids.append(UiElementId.PNC_STATUS_BANNER)
    visible_texts = {} if status_banner_text is None else {UiElementId.PNC_STATUS_BANNER: status_banner_text}
    return make_observation(
        ScreenType.PNC_WORLD_COORDINATE_DIALOG,
        visible_ids=tuple(visible_ids),
        visible_texts=visible_texts,
        text_field_states={
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD: ObservedTextFieldState(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
                text=str(kingdom),
                empty=False,
            ),
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD: ObservedTextFieldState(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                text=str(x),
                empty=False,
            ),
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD: ObservedTextFieldState(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
                text=str(y),
                empty=False,
            ),
        },
    )


def _make_world_map_overview_observation(
    *,
    marker_point: tuple[int, int] | None,
    header_text: str = "K:157 Shadow Realm",
    recenter_region_bounds: tuple[int, int, int, int] = (10, 30, 180, 140),
) -> Observation:
    """Builds one synthetic overview observation with a map region and viewport marker."""

    visible_elements = {
        UiElementId.PNC_WORLD_OVERVIEW_HEADER: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_HEADER,
            x=20,
            y=10,
            width=120,
            height=20,
            extracted_text=header_text,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON,
            x=180,
            y=10,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON,
            x=20,
            y=180,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_LEGEND_BUTTON: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_LEGEND_BUTTON,
            x=90,
            y=180,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_VISIBILITY_BUTTON: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_VISIBILITY_BUTTON,
            x=150,
            y=180,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION,
            x=20,
            y=40,
            width=160,
            height=120,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_RECENTER_REGION: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_RECENTER_REGION,
            x=recenter_region_bounds[0],
            y=recenter_region_bounds[1],
            width=recenter_region_bounds[2],
            height=recenter_region_bounds[3],
        ),
    }
    if marker_point is not None:
        visible_elements[UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER] = make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER,
            x=marker_point[0],
            y=marker_point[1],
            width=6,
            height=6,
            action_point=marker_point,
        )
    return Observation(
        screen_type=ScreenType.PNC_WORLD_MAP_OVERVIEW,
        visible_elements=visible_elements,
        image_size=(200, 200),
    )


def _overview_marker_point_for_coordinate(coordinate: tuple[int, int]) -> tuple[int, int]:
    """Returns the synthetic overview marker point for one world coordinate in the shared test fixture."""

    return project_world_coordinate_to_overview_point(
        coordinate=coordinate,
        bounds=WorldMapCoordinateDomain.puzzles_and_conquest().bounds,
        map_region_bounds=make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION,
            x=20,
            y=40,
            width=160,
            height=120,
        ).bounds,
    )


def _build_recording_logger(name: str) -> tuple[logging.LoggerAdapter, list[logging.LogRecord]]:
    """Builds one in-memory logger adapter plus the structured records it emits."""

    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(f"pnc_automation.tests.{name}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(_ListHandler())
    return logging.LoggerAdapter(logger, extra={}), records


if __name__ == "__main__":
    unittest.main()
