"""Evaluate YOLO candidates without changing authoritative observations or actions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import math
import statistics
from time import perf_counter
from types import MappingProxyType
from typing import Protocol

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    DetectedSpatialObject, Observation, SpatialObjectKind, SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.detection.yolo_onnx import YoloDetection


class ObjectDetector(Protocol):
    """A loaded local model supplies pixel-space candidates and its class catalog."""

    class_names: tuple[str, ...]
    model_sha256: str

    def detect(self, image: Image.Image) -> tuple[YoloDetection, ...]: ...


@dataclass(frozen=True, slots=True)
class YoloShadowReport:
    """Diagnostic output only; candidates are never installed in Observation."""

    model_sha256: str
    frame_sha256: str
    screen_type: ScreenType
    detections: tuple[YoloDetection, ...]
    candidates: tuple[DetectedSpatialObject, ...]
    elapsed_ms: float
    candidate_gate: str


@dataclass(frozen=True, slots=True)
class YoloShadowEvaluation:
    """Aggregate whether shadow detections add validated PNC vision evidence."""

    frame_count: int
    unique_frame_count: int
    frames_with_detections: int
    detection_count: int
    candidate_count: int
    detection_labels: tuple[tuple[str, int], ...]
    candidate_gates: tuple[tuple[str, int], ...]
    latency_min_ms: float
    latency_median_ms: float
    latency_p95_ms: float
    latency_max_ms: float
    assessment: str
    assessment_reason: str

    def to_document(self) -> dict[str, object]:
        """Return a stable, JSON-ready assessment document."""

        return {
            "frame_count": self.frame_count,
            "unique_frame_count": self.unique_frame_count,
            "frames_with_detections": self.frames_with_detections,
            "detection_count": self.detection_count,
            "candidate_count": self.candidate_count,
            "detection_labels": dict(self.detection_labels),
            "candidate_gates": dict(self.candidate_gates),
            "latency_ms": {
                "min": self.latency_min_ms,
                "median": self.latency_median_ms,
                "p95": self.latency_p95_ms,
                "max": self.latency_max_ms,
            },
            "authoritative_observation_changed": False,
            "assessment": self.assessment,
            "assessment_reason": self.assessment_reason,
        }


def evaluate_yolo_shadow(reports: Sequence[YoloShadowReport]) -> YoloShadowEvaluation:
    """Summarize shadow evidence without promoting it into current observations."""

    if not reports:
        raise ValueError("At least one YOLO shadow report is required for evaluation.")
    labels = Counter(detection.label for report in reports for detection in report.detections)
    gates = Counter(report.candidate_gate for report in reports)
    candidate_count = sum(len(report.candidates) for report in reports)
    detection_count = sum(len(report.detections) for report in reports)
    if candidate_count:
        assessment = "unvalidated_shadow_signal"
        reason = (
            "Mapped PNC candidates were produced in shadow mode, but box-level ground truth "
            "is required before they can improve authoritative vision."
        )
    elif detection_count:
        assessment = "no_measured_pnc_improvement"
        reason = (
            "The model produced generic boxes, but none became a mapped PNC candidate or "
            "changed the authoritative observation."
        )
    else:
        assessment = "no_measured_pnc_improvement"
        reason = (
            "The model produced no retained boxes and did not change the authoritative observation."
        )
    latencies = sorted(report.elapsed_ms for report in reports)
    return YoloShadowEvaluation(
        frame_count=len(reports),
        unique_frame_count=len({report.frame_sha256 for report in reports}),
        frames_with_detections=sum(bool(report.detections) for report in reports),
        detection_count=detection_count,
        candidate_count=candidate_count,
        detection_labels=tuple(sorted(labels.items())),
        candidate_gates=tuple(sorted(gates.items())),
        latency_min_ms=min(latencies),
        latency_median_ms=statistics.median(latencies),
        latency_p95_ms=latencies[math.ceil(len(latencies) * 0.95) - 1],
        latency_max_ms=max(latencies),
        assessment=assessment,
        assessment_reason=reason,
    )


@dataclass(frozen=True, slots=True)
class YoloShadowObserver:
    """Compare explicit PNC class mappings on an already recognized spatial frame."""

    detector: ObjectDetector
    class_map: Mapping[str, SpatialObjectKind] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject guessed labels and malformed mapping values before inference."""
        for label, kind in self.class_map.items():
            if label not in self.detector.class_names:
                raise ValueError(f"Class mapping label is absent from the model: {label}")
            if not isinstance(kind, SpatialObjectKind):
                raise ValueError("Class mappings must contain SpatialObjectKind values.")
        # Keep caller mutation from changing the semantics of an existing observer.
        object.__setattr__(self, "class_map", MappingProxyType(dict(self.class_map)))

    def observe(self, capture: CapturedScreenshot, observation: Observation) -> YoloShadowReport:
        """Run the model on the exact captured frame; leave the current state intact."""
        if observation.image_size != capture.image.size:
            raise ValueError("Shadow observation and screenshot dimensions differ.")
        frame_bytes = capture.payload if capture.payload is not None else capture.image.tobytes()
        fingerprint = hashlib.sha256(frame_bytes).hexdigest()
        if observation.frame_fingerprint != fingerprint:
            raise ValueError("Shadow observation must belong to the same captured frame.")
        started = perf_counter()
        detections = self.detector.detect(capture.image)
        elapsed_ms = (perf_counter() - started) * 1000
        gate = self._candidate_gate(observation)
        candidates = ()
        if gate == "eligible_shadow_only":
            candidates = tuple(
                DetectedSpatialObject(
                    kind=self.class_map[item.label], bounds=item.bounds,
                    metadata={"source": "yolo_shadow", "confidence": item.confidence,
                              "model_sha256": self.detector.model_sha256, "class_id": item.class_id},
                )
                for item in detections if item.label in self.class_map
            )
        return YoloShadowReport(
            self.detector.model_sha256, fingerprint, observation.screen_type,
            detections, candidates, elapsed_ms, gate,
        )

    def _candidate_gate(self, observation: Observation) -> str:
        """Only an explicit class map and known unobstructed spatial state qualify."""
        if observation.blocking_popup:
            return "blocking_popup"
        surface = observation.spatial_surface
        expected = {
            ScreenType.PNC_WORLD_MAP: SpatialSurfaceType.WORLD_MAP,
            ScreenType.PNC_HOME_CITY: SpatialSurfaceType.HOME_CITY_SURFACE,
        }
        if surface is None or expected.get(observation.screen_type) != surface.surface_type:
            return "unsupported_spatial_state"
        if not self.class_map:
            return "no_pnc_class_mapping"
        return "eligible_shadow_only"
