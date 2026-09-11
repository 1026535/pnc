"""Evaluate YOLO candidates without changing authoritative observations or actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
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
        fingerprint = hashlib.sha256(capture.payload if capture.payload is not None else capture.image.tobytes()).hexdigest()
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
