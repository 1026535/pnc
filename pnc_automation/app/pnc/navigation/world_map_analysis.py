"""Canonical P2 viewport-analysis work contracts for world-map sweep/search flows."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from enum import StrEnum
from threading import Lock
from typing import Protocol

from pnc_automation.app.pnc.domain.observation import Observation, SpatialSurfaceType
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import is_integer_pair
from pnc_automation.app.pnc.navigation.world_map_proof import (
    WorldMapProofStrength,
    WorldMapViewportProof,
)
from pnc_automation.app.pnc.navigation.world_map_sweep import WorldMapCoverageWindow, WorldMapProjectedFrame
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.runtime.observation_artifacts import ObservationArtifactSelection
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot


class WorldMapScreenshotObservationBuilder(Protocol):
    """Builds one rich P2 observation from an existing P1 screenshot without recapture."""

    def __call__(
        self,
        screenshot: CapturedScreenshot,
        request: ObservationRequest,
    ) -> Observation:
        """Returns the rich observation built from the provided screenshot."""


class WorldMapViewportAnalysisTreatmentKind(StrEnum):
    """Defines how much rich analysis P2 should perform for one proven viewport."""

    INVENTORY_ONLY = "inventory_only"
    CHECKPOINT_SEARCH = "checkpoint_search"


@dataclass(frozen=True, slots=True)
class WorldMapActualSample:
    """Canonical exact sample captured during route execution with planned and proven coordinates separated."""

    route_index: int
    planned_coordinate: tuple[int, int]
    actual_coordinate: tuple[int, int]
    proof: WorldMapViewportProof | None
    screenshot: CapturedScreenshot
    coverage_window: WorldMapCoverageWindow | None = None
    projected_frame: WorldMapProjectedFrame | None = None

    def __post_init__(self) -> None:
        """Rejects samples whose route, proof, screenshot, or projection identity disagree."""

        if self.route_index < 0:
            raise SelectorResolutionError("World-map actual samples require a non-negative route_index.")
        if not is_integer_pair(self.planned_coordinate) or not is_integer_pair(self.actual_coordinate):
            raise SelectorResolutionError(
                "World-map actual samples require integer planned and actual coordinates.",
                planned_coordinate=self.planned_coordinate,
                actual_coordinate=self.actual_coordinate,
            )
        if self.proof is None:
            raise SelectorResolutionError("World-map actual samples require exact P1 proof.")
        _require_exact_screenshot_proof(
            proof=self.proof,
            screenshot=self.screenshot,
            coordinate=self.actual_coordinate,
        )
        if self.projected_frame is not None and self.projected_frame.estimated_viewport_center != self.actual_coordinate:
            raise SelectorResolutionError(
                "World-map actual samples must keep projected-frame metadata anchored to the actual coordinate.",
                actual_coordinate=self.actual_coordinate,
                projected_coordinate=self.projected_frame.estimated_viewport_center,
            )

    def to_document(self) -> dict[str, object]:
        """Exports the route-progress and exact-sample identity without embedding screenshot payloads."""

        return {
            "route_index": self.route_index,
            "planned_coordinate": [self.planned_coordinate[0], self.planned_coordinate[1]],
            "actual_coordinate": [self.actual_coordinate[0], self.actual_coordinate[1]],
            "proof_strength": None if self.proof is None else self.proof.strength.value,
            "screenshot_artifact_path": None if self.screenshot.artifact_path is None else str(self.screenshot.artifact_path),
            "has_projected_frame": self.projected_frame is not None,
            "has_coverage_window": self.coverage_window is not None,
        }


@dataclass(frozen=True, slots=True)
class WorldMapViewportAnalysisWorkItem:
    """Immutable P2 work request containing a P1 screenshot and coordinate facts, never an observation."""

    route_index: int
    checkpoint_coordinate: tuple[int, int]
    screenshot: CapturedScreenshot
    proof: WorldMapViewportProof | None
    label: str
    treatment_kind: WorldMapViewportAnalysisTreatmentKind = WorldMapViewportAnalysisTreatmentKind.CHECKPOINT_SEARCH
    artifact_selection: ObservationArtifactSelection | None = None
    projected_frame: WorldMapProjectedFrame | None = None
    actual_sample: WorldMapActualSample | None = None

    def __post_init__(self) -> None:
        """Rejects malformed work items before workers or coordinator consume them."""

        if self.route_index < 0:
            raise SelectorResolutionError("World-map P2 work items require a non-negative route_index.")
        if not is_integer_pair(self.checkpoint_coordinate):
            raise SelectorResolutionError(
                "World-map P2 work items require an integer checkpoint coordinate.",
                checkpoint_coordinate=self.checkpoint_coordinate,
            )
        if self.label.strip() == "":
            raise SelectorResolutionError("World-map P2 work items require a non-blank label.")
        if self.actual_sample is not None:
            self._require_matching_actual_sample()
        if self.treatment_kind == WorldMapViewportAnalysisTreatmentKind.CHECKPOINT_SEARCH:
            self._require_exact_checkpoint_proof()
            if self.projected_frame is not None:
                raise SelectorResolutionError("Exact checkpoint P2 work must not carry projected-frame metadata.")
            if self.actual_sample is not None:
                raise SelectorResolutionError("Exact checkpoint P2 work must not carry production sample metadata.")
            return
        if self.treatment_kind != WorldMapViewportAnalysisTreatmentKind.INVENTORY_ONLY:
            raise SelectorResolutionError(
                "Unsupported world-map P2 treatment kind.",
                treatment_kind=self.treatment_kind.value,
            )
        self._require_exact_checkpoint_proof()
        if self.projected_frame is not None and self.projected_frame.estimated_viewport_center != self.checkpoint_coordinate:
            raise SelectorResolutionError(
                "Projected P2 work must stay anchored to its projected viewport coordinate.",
                checkpoint_coordinate=self.checkpoint_coordinate,
                projected_coordinate=self.projected_frame.estimated_viewport_center,
            )

    def _require_exact_checkpoint_proof(self) -> None:
        """Requires exact screenshot identity for checkpoint-analysis work."""

        if self.proof is None:
            raise SelectorResolutionError("World-map P2 analysis requires exact P1 coordinate proof.")
        _require_exact_screenshot_proof(
            proof=self.proof,
            screenshot=self.screenshot,
            coordinate=self.checkpoint_coordinate,
        )

    def _require_matching_actual_sample(self) -> None:
        """Validates production sample metadata against the public work-item identity."""

        assert self.actual_sample is not None
        if self.actual_sample.route_index != self.route_index:
            raise SelectorResolutionError(
                "World-map P2 work item route index must match its actual sample.",
                route_index=self.route_index,
                sample_route_index=self.actual_sample.route_index,
            )
        if self.actual_sample.actual_coordinate != self.checkpoint_coordinate:
            raise SelectorResolutionError(
                "World-map P2 work item coordinate must match its actual sample.",
                checkpoint_coordinate=self.checkpoint_coordinate,
                sample_actual_coordinate=self.actual_sample.actual_coordinate,
            )
        if self.actual_sample.screenshot is not self.screenshot:
            raise SelectorResolutionError(
                "World-map P2 work item must share the exact screenshot object carried by its actual sample."
            )
        if self.actual_sample.proof is not self.proof:
            raise SelectorResolutionError(
                "World-map P2 work item must share the exact proof object carried by its actual sample."
            )


@dataclass(frozen=True, slots=True)
class WorldMapViewportAnalysisResult:
    """Immutable P2 analysis result; applying it to survey state remains coordinator-owned."""

    work_item: WorldMapViewportAnalysisWorkItem
    observation: Observation
    detected_object_count: int
    elapsed_ms: float

    def __post_init__(self) -> None:
        """Rejects P2 results that cannot be applied deterministically."""

        if self.elapsed_ms < 0:
            raise SelectorResolutionError("World-map P2 analysis elapsed_ms must be non-negative.")
        surface = self.observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        if surface.viewport.coordinate != self.work_item.checkpoint_coordinate:
            raise SelectorResolutionError(
                "World-map P2 analysis result must preserve the checkpoint coordinate.",
                checkpoint_coordinate=self.work_item.checkpoint_coordinate,
                result_coordinate=surface.viewport.coordinate,
        )


@dataclass(frozen=True, slots=True)
class WorldMapViewportAnalysisTelemetryRecord:
    """Captures one P2 queue item lifecycle in monotonic-clock milliseconds."""

    route_index: int
    submission_order: int
    submitted_at_ms: float
    worker_started_at_ms: float | None
    worker_finished_at_ms: float | None
    result_released_at_ms: float | None
    failed: bool = False
    failure_message: str | None = None

    @property
    def queue_wait_ms(self) -> float | None:
        """Returns the worker wait time after submission when both timestamps are known."""

        if self.worker_started_at_ms is None:
            return None
        return self.worker_started_at_ms - self.submitted_at_ms

    @property
    def worker_elapsed_ms(self) -> float | None:
        """Returns worker runtime when both worker timestamps are known."""

        if self.worker_started_at_ms is None or self.worker_finished_at_ms is None:
            return None
        return self.worker_finished_at_ms - self.worker_started_at_ms

    @property
    def release_elapsed_ms(self) -> float | None:
        """Returns total elapsed time until the coordinator released the result."""

        if self.result_released_at_ms is None:
            return None
        return self.result_released_at_ms - self.submitted_at_ms

    def to_document(self) -> dict[str, object]:
        """Exports queue telemetry as one JSON-ready profile row."""

        return {
            "route_index": self.route_index,
            "submission_order": self.submission_order,
            "queue_wait_ms": None if self.queue_wait_ms is None else round(self.queue_wait_ms, 2),
            "worker_elapsed_ms": None if self.worker_elapsed_ms is None else round(self.worker_elapsed_ms, 2),
            "release_elapsed_ms": None if self.release_elapsed_ms is None else round(self.release_elapsed_ms, 2),
            "failed": self.failed,
            "failure_message": self.failure_message,
        }


@dataclass(slots=True)
class _WorldMapViewportAnalysisTelemetryEntry:
    """Mutable internal queue telemetry entry guarded by the queue lock."""

    route_index: int
    submission_order: int
    submitted_at_ms: float
    worker_started_at_ms: float | None = None
    worker_finished_at_ms: float | None = None
    result_released_at_ms: float | None = None
    failed: bool = False
    failure_message: str | None = None

    def snapshot(self) -> WorldMapViewportAnalysisTelemetryRecord:
        """Returns an immutable public copy of the queue lifecycle entry."""

        return WorldMapViewportAnalysisTelemetryRecord(
            route_index=self.route_index,
            submission_order=self.submission_order,
            submitted_at_ms=self.submitted_at_ms,
            worker_started_at_ms=self.worker_started_at_ms,
            worker_finished_at_ms=self.worker_finished_at_ms,
            result_released_at_ms=self.result_released_at_ms,
            failed=self.failed,
            failure_message=self.failure_message,
        )


@dataclass(slots=True)
class _WorldMapViewportPendingAnalysis:
    """Pairs one submitted future with its route-order and telemetry identity."""

    route_index: int
    submission_order: int
    future: Future[WorldMapViewportAnalysisResult]


@dataclass(slots=True)
class WorldMapViewportAnalyzer:
    """Builds immutable rich P2 observations from P1 screenshots without recapturing."""

    observation_builder: WorldMapScreenshotObservationBuilder | None = None

    @staticmethod
    def request_for_work_item(work_item: WorldMapViewportAnalysisWorkItem) -> ObservationRequest:
        """Maps a P2 treatment kind to its one canonical observation request."""

        if work_item.treatment_kind == WorldMapViewportAnalysisTreatmentKind.CHECKPOINT_SEARCH:
            return ObservationRequest.world_map_checkpoint_analysis(
                expected_coordinate=work_item.checkpoint_coordinate,
            )
        if work_item.treatment_kind == WorldMapViewportAnalysisTreatmentKind.INVENTORY_ONLY:
            return ObservationRequest.world_map_inventory_analysis(
                expected_coordinate=work_item.checkpoint_coordinate,
            )
        raise SelectorResolutionError(
            "Unsupported world-map P2 treatment kind.",
            treatment_kind=work_item.treatment_kind.value,
        )

    def analyze(self, work_item: WorldMapViewportAnalysisWorkItem) -> WorldMapViewportAnalysisResult:
        """Runs rich OCR/element identification on the P1 screenshot and returns coordinator-owned output."""

        if self.observation_builder is None:
            raise SelectorResolutionError("World-map P2 analysis requires a screenshot observation builder.")
        started_at = time.perf_counter()
        request = self.request_for_work_item(work_item)
        if work_item.artifact_selection is not None:
            request = replace(request, artifact_selection=work_item.artifact_selection)
        observation = self.observation_builder(
            work_item.screenshot,
            request,
        )
        surface = observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        return WorldMapViewportAnalysisResult(
            work_item=work_item,
            observation=observation,
            detected_object_count=len(surface.objects),
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
        )


@dataclass(slots=True)
class WorldMapViewportAnalysisQueue:
    """Runs bounded P2 work while preserving deterministic route-order result application."""

    analyzer: Callable[[WorldMapViewportAnalysisWorkItem], WorldMapViewportAnalysisResult]
    max_pending: int
    max_workers: int = 1
    _executor: ThreadPoolExecutor = field(init=False, repr=False)
    _pending: list[_WorldMapViewportPendingAnalysis] = field(default_factory=list, init=False, repr=False)
    _telemetry_entries: dict[int, _WorldMapViewportAnalysisTelemetryEntry] = field(default_factory=dict, init=False, repr=False)
    _submitted_route_indices: set[int] = field(default_factory=set, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    peak_depth: int = field(default=0, init=False)
    submission_count: int = field(default=0, init=False)
    backpressure_block_count: int = field(default=0, init=False)
    backpressure_block_elapsed_ms: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        """Creates the bounded worker pool after validating queue limits."""

        if self.max_pending <= 0:
            raise SelectorResolutionError("World-map P2 queues require a positive max_pending value.")
        if self.max_workers != 1:
            raise SelectorResolutionError(
                "World-map P2 queues currently require max_workers=1 until OCR builders are proven worker-safe.",
                max_workers=self.max_workers,
            )
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="world-map-p2")

    def submit(self, work_item: WorldMapViewportAnalysisWorkItem) -> None:
        """Submits one immutable P2 work item or fails fast when the bounded queue is full."""

        if len(self._pending) >= self.max_pending:
            raise SelectorResolutionError(
                "World-map P2 analysis queue exceeded its bounded pending limit.",
                max_pending=self.max_pending,
                pending=len(self._pending),
            )
        if work_item.route_index in self._submitted_route_indices:
            raise SelectorResolutionError(
                "World-map P2 queue route indices must be unique within one search.",
                route_index=work_item.route_index,
            )
        submission_order = self.submission_count
        entry = _WorldMapViewportAnalysisTelemetryEntry(
            route_index=work_item.route_index,
            submission_order=submission_order,
            submitted_at_ms=_monotonic_ms(),
        )
        self._telemetry_entries[submission_order] = entry
        future = self._executor.submit(self._analyze_with_telemetry, work_item, submission_order)
        self._pending.append(
            _WorldMapViewportPendingAnalysis(
                route_index=work_item.route_index,
                submission_order=submission_order,
                future=future,
            )
        )
        self._pending.sort(key=lambda pending: pending.route_index)
        self._submitted_route_indices.add(work_item.route_index)
        self.submission_count += 1
        self.peak_depth = max(self.peak_depth, len(self._pending))

    @property
    def pending_count(self) -> int:
        """Returns the number of submitted results not yet consumed by the coordinator."""

        return len(self._pending)

    @property
    def telemetry_records(self) -> tuple[WorldMapViewportAnalysisTelemetryRecord, ...]:
        """Returns immutable queue lifecycle telemetry in submission order."""

        return tuple(
            self._telemetry_entries[index].snapshot()
            for index in sorted(self._telemetry_entries)
        )

    @property
    def first_failure(self) -> WorldMapViewportAnalysisTelemetryRecord | None:
        """Returns the first failed queue telemetry row when one worker failed."""

        for record in self.telemetry_records:
            if record.failed:
                return record
        return None

    def drain_ready(self) -> tuple[WorldMapViewportAnalysisResult, ...]:
        """Returns the completed route-order prefix without blocking on later P2 work."""

        results: list[WorldMapViewportAnalysisResult] = []
        while self._pending and self._pending[0].future.done():
            pending = self._pending.pop(0)
            self._mark_released(pending.submission_order)
            results.append(pending.future.result())
        return tuple(results)

    def drain_next(self, *, blocking_reason: str | None = None) -> WorldMapViewportAnalysisResult:
        """Blocks for and returns the oldest pending result to provide bounded backpressure."""

        if not self._pending:
            raise SelectorResolutionError("World-map P2 queue has no pending result to drain.")
        pending = self._pending.pop(0)
        started_at = time.perf_counter()
        try:
            return pending.future.result()
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            self._mark_released(pending.submission_order)
            if blocking_reason == "backpressure":
                self.backpressure_block_count += 1
                self.backpressure_block_elapsed_ms += elapsed_ms

    def drain_all(self) -> tuple[WorldMapViewportAnalysisResult, ...]:
        """Returns all submitted P2 results in deterministic route-index order, propagating the first failure."""

        ordered = sorted(self._pending, key=lambda pending: pending.route_index)
        self._pending = []
        results: list[WorldMapViewportAnalysisResult] = []
        try:
            for pending in ordered:
                try:
                    results.append(pending.future.result())
                finally:
                    self._mark_released(pending.submission_order)
        finally:
            for pending in ordered:
                pending.future.cancel()
        return tuple(results)

    def close(self) -> None:
        """Shuts down the worker pool after pending work has been drained or cancelled."""

        self._executor.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> "WorldMapViewportAnalysisQueue":
        """Returns the queue for context-manager use in tests and runtime coordinators."""

        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Closes the queue when leaving a context-manager scope."""

        del exc_type, exc, traceback
        self.close()

    def _analyze_with_telemetry(
        self,
        work_item: WorldMapViewportAnalysisWorkItem,
        submission_order: int,
    ) -> WorldMapViewportAnalysisResult:
        """Runs the analyzer while recording worker lifecycle timings."""

        self._update_telemetry(submission_order, worker_started_at_ms=_monotonic_ms())
        try:
            return self.analyzer(work_item)
        except Exception as error:
            self._update_telemetry(
                submission_order,
                worker_finished_at_ms=_monotonic_ms(),
                failed=True,
                failure_message=str(error),
            )
            raise
        finally:
            self._update_telemetry(submission_order, worker_finished_at_ms=_monotonic_ms())

    def _mark_released(self, submission_order: int) -> None:
        """Records when a result leaves the queue for coordinator-owned application."""

        self._update_telemetry(submission_order, result_released_at_ms=_monotonic_ms())

    def _update_telemetry(self, submission_order: int, **changes: object) -> None:
        """Applies one telemetry update while preserving unrelated fields."""

        with self._lock:
            entry = self._telemetry_entries[submission_order]
            for field_name, value in changes.items():
                setattr(entry, field_name, value)


def _require_exact_screenshot_proof(
    *,
    proof: WorldMapViewportProof,
    screenshot: CapturedScreenshot,
    coordinate: tuple[int, int],
) -> None:
    """Validates exact proof metadata against one screenshot and expected coordinate."""

    if proof.strength != WorldMapProofStrength.EXACT:
        raise SelectorResolutionError(
            "World-map P2 analysis requires exact P1 coordinate proof.",
            proof_strength=proof.strength.value,
        )
    if proof.coordinate != coordinate:
        raise SelectorResolutionError(
            "World-map P2 work must stay anchored to the P1-proven coordinate.",
            checkpoint_coordinate=coordinate,
            proof_coordinate=proof.coordinate,
        )
    if screenshot.captured_at != proof.captured_at:
        raise SelectorResolutionError(
            "World-map P2 work requires the exact screenshot whose movement facts P1 proved.",
            screenshot_captured_at=screenshot.captured_at.isoformat(),
            proof_captured_at=proof.captured_at.isoformat(),
        )
    if screenshot.artifact_path != proof.artifact_path:
        raise SelectorResolutionError(
            "World-map P2 screenshot artifact identity must match the P1 proof.",
            screenshot_artifact_path=screenshot.artifact_path,
            proof_artifact_path=proof.artifact_path,
        )


def _monotonic_ms() -> float:
    """Returns the monotonic clock in milliseconds for queue telemetry."""

    return time.perf_counter() * 1000.0
