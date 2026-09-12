"""World search movement proof: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapMovementToolKind,
    WorldMapSearchBoundary,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    WorldMapSearchService,
    WorldMapSearchStopReason,
    world_map_search_execution_profile_document,
    world_map_movement_trace_document,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.domain.observation_policy import (
    ObservationArtifactKind,
    observation_artifact_selection,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.observations import make_observation
from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.build_recording_logger import _build_recording_logger
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchMovementProofTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search movement proof."""

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
        self.assertGreaterEqual(trace["action_follow_up_observe_elapsed_ms"], 0.0)
        self.assertGreaterEqual(trace["action_executor_overhead_elapsed_ms"], 0.0)
        self.assertLessEqual(trace["action_follow_up_observe_elapsed_ms"], trace["action_elapsed_ms"])
        self.assertEqual(trace["action_follow_up_observation_count"], 1)
        self.assertGreaterEqual(trace["prove_elapsed_ms"], 0.0)
        self.assertEqual(observer.requests, [ObservationRequest.world_map_movement_follow_up()])

    def test_move_to_checkpoint_uses_movement_proof_scope_on_final_landing(self) -> None:
        """Keeps the mover on the narrow P1 proof contract instead of hiding rich checkpoint analysis inside movement."""

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
        self.assertEqual(observer.requests, [ObservationRequest.world_map_movement_proof_follow_up()])

    def test_execute_search_records_json_ready_execution_profile_in_runtime_state_and_result(self) -> None:
        """Captures canonical per-checkpoint benchmark timings without bypassing survey ingestion or matching."""

        service, _observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(0, 0),
                _make_world_map_observation(10, 0),
            ]
        )
        runtime_state: dict[str, object] = {}

        result = service.execute_search(
            _search_request(
                matcher=SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.RESOURCE_NODE),
                pattern=WorldMapSearchPattern.row_major_sweep(),
                origin=WorldMapSearchOrigin.current_viewport(),
                boundary=WorldMapSearchBoundary.rectangle(min_coordinate=(0, 0), max_coordinate=(10, 0)),
                checkpoint_spacing=10,
            ),
            label_prefix="execution_profile_capture",
            start_observation=_make_world_map_observation(0, 0),
            runtime_state=runtime_state,
        )

        document = world_map_search_execution_profile_document(runtime_state)
        self.assertIsNotNone(result.execution_profile)
        assert result.execution_profile is not None
        self.assertEqual(document["movement_tool"], WorldMapMovementToolKind.SWIPE.value)
        self.assertEqual(document["stop_reason"], WorldMapSearchStopReason.BOUNDARY_EXHAUSTED.value)
        self.assertEqual(len(document["checkpoint_profiles"]), 2)
        self.assertEqual(document["checkpoint_profiles"][0]["checkpoint_coordinate"], [0, 0])
        self.assertEqual(document["checkpoint_profiles"][1]["checkpoint_coordinate"], [10, 0])
        self.assertEqual(document["checkpoint_profiles"][0]["action_family"], "local_direct")
        self.assertEqual(document["checkpoint_profiles"][1]["action_family"], "local_direct")
        self.assertEqual(document["checkpoint_profiles"][0]["status"], "completed")
        self.assertIsNone(document["checkpoint_profiles"][0]["failure_stage"])
        self.assertGreaterEqual(document["plan_elapsed_ms"], 0.0)
        self.assertGreaterEqual(document["persist_summary_elapsed_ms"], 0.0)
        self.assertGreaterEqual(document["total_elapsed_ms"], 0.0)
        self.assertGreaterEqual(document["stage_totals"]["move_elapsed_ms"], 0.0)
        self.assertGreaterEqual(result.execution_profile.total_elapsed_ms, 0.0)

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
        self.assertEqual(observer.artifact_selections[0], frozenset())
        self.assertEqual(observer.artifact_selections[-1], screenshot_selection)
        self.assertTrue(observer.labels[-1].endswith("checkpoint_failure_failure_0"))
        failure_records = [record for record in records if record.msg == "World-map movement step failed."]
        self.assertEqual(len(failure_records), 1)
        self.assertEqual(failure_records[0].step_index, 0)
