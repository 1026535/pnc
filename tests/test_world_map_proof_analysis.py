"""Focused coverage for canonical world-map P1 proof and P2 analysis contracts."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.world_map_analysis import (
    WorldMapViewportAnalysisQueue,
    WorldMapViewportAnalysisTreatmentKind,
    WorldMapViewportAnalysisWorkItem,
    WorldMapViewportAnalyzer,
)
from pnc_automation.app.pnc.navigation.world_map_proof import (
    WorldMapProofStrength,
    WorldMapViewportProof,
    require_exact_world_map_proof,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.errors import SelectorResolutionError
from tests.test_support import FakeObservationService, make_observation, make_spatial_object, make_spatial_surface


class WorldMapProofAnalysisTests(unittest.TestCase):
    """Validates that P1/P2 stay typed, bounded, and non-mutating."""

    def test_p1_exact_proof_uses_existing_world_map_surface_without_refresh(self) -> None:
        """Builds exact P1 proof directly from an already-parsed world-map observation."""

        observer = FakeObservationService(observations=[])
        observation = _world_map_observation(10, 20)

        proof = require_exact_world_map_proof(
            observation_service=observer,
            observation=observation,
            label_prefix="proof",
        )

        self.assertEqual(proof.strength, WorldMapProofStrength.EXACT)
        self.assertEqual(proof.coordinate, (10, 20))
        self.assertEqual(observer.requests, [])

    def test_p1_refresh_stays_on_movement_proof_request(self) -> None:
        """Retries UNKNOWN world-map frames with the narrow movement-proof request only."""

        refreshed = _world_map_observation(0, 0)
        observer = FakeObservationService(observations=[refreshed])
        proof = require_exact_world_map_proof(
            observation_service=observer,
            observation=make_observation(ScreenType.UNKNOWN),
            label_prefix="proof",
        )

        self.assertEqual(proof.coordinate, (0, 0))
        self.assertEqual(observer.requests, [ObservationRequest.world_map_movement_proof_follow_up()])

    def test_p2_work_item_requires_exact_p1_checkpoint_coordinate(self) -> None:
        """Fails fast instead of letting P2 analyze a viewport detached from its P1 proof."""

        capture = _p1_capture((10, 0))
        proof = WorldMapViewportProof.from_capture(capture)

        with self.assertRaises(SelectorResolutionError):
            WorldMapViewportAnalysisWorkItem(
                route_index=0,
                checkpoint_coordinate=(20, 0),
                screenshot=capture.screenshot,
                proof=proof,
                label="bad",
            )

    def test_p2_analyzer_builds_rich_observation_from_exact_p1_screenshot(self) -> None:
        """Passes only the exact P1 screenshot into the rich P2 observation builder."""

        capture = _p1_capture((10, 0))
        received: list[tuple[object, ObservationRequest]] = []

        def build_observation(screenshot: object, request: ObservationRequest):
            """Records the P2 input and returns one independently built rich observation."""

            received.append((screenshot, request))
            return _world_map_observation(
                10,
                0,
                objects=(make_spatial_object(SpatialObjectKind.MONSTER, estimated_world_coordinate=(12, 0)),),
            )

        work_item = _p2_work_item(route_index=7, coordinate=(10, 0), capture=capture)
        result = WorldMapViewportAnalyzer(observation_builder=build_observation).analyze(work_item)

        self.assertFalse(hasattr(work_item, "observation"))
        self.assertIs(received[0][0], capture.screenshot)
        self.assertEqual(received[0][1].expected_world_coordinate, (10, 0))
        self.assertEqual(result.detected_object_count, 1)

    def test_p2_inventory_work_item_requires_exact_sample_proof(self) -> None:
        """Rejects inventory-only P2 work detached from an exact P1 screenshot proof."""

        capture = _p1_capture((10, 0))

        with self.assertRaises(SelectorResolutionError):
            WorldMapViewportAnalysisWorkItem(
                route_index=0,
                checkpoint_coordinate=(10, 0),
                screenshot=capture.screenshot,
                proof=None,
                label="inventory_without_proof",
                treatment_kind=WorldMapViewportAnalysisTreatmentKind.INVENTORY_ONLY,
            )

    def test_p2_analyzer_maps_inventory_treatment_to_inventory_request(self) -> None:
        """Uses the canonical inventory request instead of checkpoint-search treatment."""

        capture = _p1_capture((10, 0))
        received: list[ObservationRequest] = []

        def build_observation(_screenshot: object, request: ObservationRequest):
            """Records the request kind selected by the analyzer."""

            received.append(request)
            return _world_map_observation(10, 0)

        work_item = _p2_work_item(
            route_index=0,
            coordinate=(10, 0),
            capture=capture,
            treatment_kind=WorldMapViewportAnalysisTreatmentKind.INVENTORY_ONLY,
        )
        WorldMapViewportAnalyzer(observation_builder=build_observation).analyze(work_item)

        self.assertEqual(received[0], ObservationRequest.world_map_inventory_analysis(expected_coordinate=(10, 0)))

    def test_p2_work_item_rejects_screenshot_from_a_different_capture(self) -> None:
        """Prevents P2 from analyzing a screenshot different from the one P1 proved."""

        capture = _p1_capture((10, 0))
        other_capture = _p1_capture((10, 0))

        with self.assertRaises(SelectorResolutionError):
            WorldMapViewportAnalysisWorkItem(
                route_index=0,
                checkpoint_coordinate=(10, 0),
                screenshot=other_capture.screenshot,
                proof=WorldMapViewportProof.from_capture(capture),
                label="mismatch",
            )

    def test_p2_queue_is_bounded_and_drains_in_route_order(self) -> None:
        """Preserves deterministic coordinator application order for asynchronous P2 work."""

        first = _p2_work_item(route_index=2, coordinate=(20, 0))
        second = _p2_work_item(route_index=1, coordinate=(10, 0))

        analyzer = WorldMapViewportAnalyzer(observation_builder=_build_rich_p2_observation)
        with WorldMapViewportAnalysisQueue(analyzer=analyzer.analyze, max_pending=2) as queue:
            queue.submit(first)
            queue.submit(second)
            results = queue.drain_all()

        self.assertEqual([result.work_item.route_index for result in results], [1, 2])
        self.assertEqual(queue.peak_depth, 2)

    def test_p2_queue_ready_and_next_drains_use_route_order_for_out_of_order_submissions(self) -> None:
        """Keeps every drain method on the same route-order coordinator contract."""

        analyzer = WorldMapViewportAnalyzer(observation_builder=_build_rich_p2_observation)
        with WorldMapViewportAnalysisQueue(analyzer=analyzer.analyze, max_pending=2) as queue:
            queue.submit(_p2_work_item(route_index=2, coordinate=(20, 0)))
            queue.submit(_p2_work_item(route_index=1, coordinate=(10, 0)))
            self.assertEqual(queue.drain_next().work_item.route_index, 1)
            self.assertEqual([result.work_item.route_index for result in queue.drain_ready()], [2])

    def test_p2_queue_rejects_multiple_workers_until_builders_are_worker_safe(self) -> None:
        """Keeps the lazy OCR/builder ownership invariant explicit."""

        analyzer = WorldMapViewportAnalyzer(observation_builder=_build_rich_p2_observation)
        with self.assertRaises(SelectorResolutionError):
            WorldMapViewportAnalysisQueue(analyzer=analyzer.analyze, max_pending=2, max_workers=2)

    def test_p2_queue_fails_fast_when_pending_limit_is_exceeded(self) -> None:
        """Rejects unbounded P2 backlog before movement can outrun analysis."""

        analyzer = WorldMapViewportAnalyzer(observation_builder=_build_rich_p2_observation)
        with WorldMapViewportAnalysisQueue(analyzer=analyzer.analyze, max_pending=1) as queue:
            queue.submit(_p2_work_item(route_index=0, coordinate=(0, 0)))
            with self.assertRaises(SelectorResolutionError):
                queue.submit(_p2_work_item(route_index=1, coordinate=(10, 0)))


def _world_map_observation(
    x: int,
    y: int,
    *,
    objects: tuple[object, ...] = (),
):
    """Builds one coordinate-addressed world-map observation for P1/P2 tests."""

    return make_observation(
        ScreenType.PNC_WORLD_MAP,
        spatial_surface=make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=x,
            y=y,
            objects=objects,
        ),
    )


def _p1_capture(coordinate: tuple[int, int]):
    """Builds one minimal P1 observation paired with its exact synthetic screenshot."""

    observer = FakeObservationService(observations=[_world_map_observation(*coordinate)])
    return observer.capture_observation(
        "p1",
        request=ObservationRequest.world_map_movement_proof_follow_up(),
        artifact_selection=frozenset(),
    )


def _build_rich_p2_observation(_screenshot: object, request: ObservationRequest):
    """Builds one deterministic rich P2 observation at the P1-proven coordinate."""

    if request.expected_world_coordinate is None:
        raise AssertionError("P2 requests must carry the P1-proven coordinate.")
    return _world_map_observation(*request.expected_world_coordinate)


def _p2_work_item(
    *,
    route_index: int,
    coordinate: tuple[int, int],
    capture: object | None = None,
    treatment_kind: WorldMapViewportAnalysisTreatmentKind = WorldMapViewportAnalysisTreatmentKind.CHECKPOINT_SEARCH,
) -> WorldMapViewportAnalysisWorkItem:
    """Builds one exact P1-backed P2 work item."""

    active_capture = _p1_capture(coordinate) if capture is None else capture
    proof = WorldMapViewportProof.from_capture(active_capture)
    return WorldMapViewportAnalysisWorkItem(
        route_index=route_index,
        checkpoint_coordinate=coordinate,
        screenshot=active_capture.screenshot,
        proof=proof,
        label=f"checkpoint_{route_index}",
        treatment_kind=treatment_kind,
    )


if __name__ == "__main__":
    unittest.main()
