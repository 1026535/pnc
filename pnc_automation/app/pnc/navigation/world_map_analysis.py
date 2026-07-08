"""Canonical P2 viewport-analysis work contracts for world-map sweep/search flows."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from pnc_automation.app.pnc.domain.observation import Observation, SpatialSurfaceType
from pnc_automation.app.pnc.navigation.world_map_proof import (
    WorldMapProofStrength,
    WorldMapViewportProof,
)
from pnc_automation.app.pnc.navigation.world_map_sweep import WorldMapProjectedFrame
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

    def __post_init__(self) -> None:
        """Rejects malformed work items before workers or coordinator consume them."""

        if self.route_index < 0:
            raise SelectorResolutionError("World-map P2 work items require a non-negative route_index.")
        if self.label.strip() == "":
            raise SelectorResolutionError("World-map P2 work items require a non-blank label.")
        if self.treatment_kind == WorldMapViewportAnalysisTreatmentKind.CHECKPOINT_SEARCH:
            self._require_exact_checkpoint_proof()
            if self.projected_frame is not None:
                raise SelectorResolutionError("Exact checkpoint P2 work must not carry projected-frame metadata.")
            return
        if self.treatment_kind != WorldMapViewportAnalysisTreatmentKind.INVENTORY_ONLY:
            raise SelectorResolutionError(
                "Unsupported world-map P2 treatment kind.",
                treatment_kind=self.treatment_kind.value,
            )
        if self.proof is not None:
            self._require_matching_proof()
        if self.projected_frame is not None and self.projected_frame.estimated_viewport_center != self.checkpoint_coordinate:
            raise SelectorResolutionError(
                "Projected P2 work must stay anchored to its projected viewport coordinate.",
                checkpoint_coordinate=self.checkpoint_coordinate,
                projected_coordinate=self.projected_frame.estimated_viewport_center,
            )

    def _require_exact_checkpoint_proof(self) -> None:
        """Requires exact screenshot identity for checkpoint-analysis work."""

        if self.proof is None:
            raise SelectorResolutionError("World-map P2 checkpoint analysis requires exact P1 coordinate proof.")
        self._require_matching_proof()

    def _require_matching_proof(self) -> None:
        """Validates optional proof metadata against the work item screenshot and coordinate."""

        assert self.proof is not None
        if self.proof.strength != WorldMapProofStrength.EXACT:
            raise SelectorResolutionError(
                "World-map P2 checkpoint analysis requires exact P1 coordinate proof.",
                proof_strength=self.proof.strength.value,
            )
        if self.proof.coordinate != self.checkpoint_coordinate:
            raise SelectorResolutionError(
                "World-map P2 work must stay anchored to the P1-proven checkpoint coordinate.",
                checkpoint_coordinate=self.checkpoint_coordinate,
                proof_coordinate=self.proof.coordinate,
            )
        if self.screenshot.captured_at != self.proof.captured_at:
            raise SelectorResolutionError(
                "World-map P2 work requires the exact screenshot whose movement facts P1 proved.",
                screenshot_captured_at=self.screenshot.captured_at.isoformat(),
                proof_captured_at=self.proof.captured_at.isoformat(),
            )
        if self.screenshot.artifact_path != self.proof.artifact_path:
            raise SelectorResolutionError(
                "World-map P2 screenshot artifact identity must match the P1 proof.",
                screenshot_artifact_path=self.screenshot.artifact_path,
                proof_artifact_path=self.proof.artifact_path,
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


@dataclass(slots=True)
class WorldMapViewportAnalyzer:
    """Builds immutable rich P2 observations from P1 screenshots without recapturing."""

    observation_builder: WorldMapScreenshotObservationBuilder | None = None

    def analyze(self, work_item: WorldMapViewportAnalysisWorkItem) -> WorldMapViewportAnalysisResult:
        """Runs rich OCR/element identification on the P1 screenshot and returns coordinator-owned output."""

        if self.observation_builder is None:
            raise SelectorResolutionError("World-map P2 analysis requires a screenshot observation builder.")
        started_at = time.perf_counter()
        observation = self.observation_builder(
            work_item.screenshot,
            ObservationRequest.world_map_checkpoint_analysis(
                expected_coordinate=work_item.checkpoint_coordinate,
            ),
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
    _pending: list[tuple[int, Future[WorldMapViewportAnalysisResult]]] = field(default_factory=list, init=False, repr=False)
    peak_depth: int = field(default=0, init=False)
    submission_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        """Creates the bounded worker pool after validating queue limits."""

        if self.max_pending <= 0:
            raise SelectorResolutionError("World-map P2 queues require a positive max_pending value.")
        if self.max_workers <= 0:
            raise SelectorResolutionError("World-map P2 queues require a positive max_workers value.")
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="world-map-p2")

    def submit(self, work_item: WorldMapViewportAnalysisWorkItem) -> None:
        """Submits one immutable P2 work item or fails fast when the bounded queue is full."""

        if len(self._pending) >= self.max_pending:
            raise SelectorResolutionError(
                "World-map P2 analysis queue exceeded its bounded pending limit.",
                max_pending=self.max_pending,
                pending=len(self._pending),
            )
        future = self._executor.submit(self.analyzer, work_item)
        self._pending.append((work_item.route_index, future))
        self.submission_count += 1
        self.peak_depth = max(self.peak_depth, len(self._pending))

    @property
    def pending_count(self) -> int:
        """Returns the number of submitted results not yet consumed by the coordinator."""

        return len(self._pending)

    def drain_ready(self) -> tuple[WorldMapViewportAnalysisResult, ...]:
        """Returns the completed route-order prefix without blocking on later P2 work."""

        results: list[WorldMapViewportAnalysisResult] = []
        while self._pending and self._pending[0][1].done():
            _route_index, future = self._pending.pop(0)
            results.append(future.result())
        return tuple(results)

    def drain_next(self) -> WorldMapViewportAnalysisResult:
        """Blocks for and returns the oldest pending result to provide bounded backpressure."""

        if not self._pending:
            raise SelectorResolutionError("World-map P2 queue has no pending result to drain.")
        _route_index, future = self._pending.pop(0)
        return future.result()

    def drain_all(self) -> tuple[WorldMapViewportAnalysisResult, ...]:
        """Returns all submitted P2 results in deterministic route-index order, propagating the first failure."""

        ordered = sorted(self._pending, key=lambda pending: pending[0])
        self._pending = []
        results: list[WorldMapViewportAnalysisResult] = []
        try:
            for _route_index, future in ordered:
                results.append(future.result())
        finally:
            for _route_index, future in ordered:
                future.cancel()
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
