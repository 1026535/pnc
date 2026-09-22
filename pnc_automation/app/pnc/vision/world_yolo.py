"""Qualified World-map YOLO candidates confined to a central scene region."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    SpatialObjectSourceKind,
)
from pnc_automation.app.pnc.vision.world_yolo_qualification import (
    WORLD_YOLO_QUALIFICATION,
    WorldYoloQualification,
)
from pnc_automation.core.vision.detection.protocol import ObjectDetector
from pnc_automation.core.vision.detection.yolo_onnx import YoloDetection, YoloOnnxDetector


WORLD_YOLO_ROI_VERSION = "v19_center_20260922"
_ROI_LEFT = 0.20
_ROI_TOP = 0.22
_ROI_RIGHT = 0.80
_ROI_BOTTOM = 0.72


class WorldYoloExclusion(StrEnum):
    """Why a raw model box is not eligible for a World spatial observation."""

    OUTSIDE_ROI = "outside_roi"
    BELOW_THRESHOLD = "below_threshold"
    UNQUALIFIED_CLASS = "unqualified_class"
    HUD_OVERLAP = "hud_overlap"


@dataclass(frozen=True, slots=True)
class WorldYoloRejectedDetection:
    """One raw box and all reasons it remains diagnostic only."""

    detection: YoloDetection
    reasons: tuple[WorldYoloExclusion, ...]


@dataclass(frozen=True, slots=True)
class WorldYoloResult:
    """Full-frame inference result, including the restricted published subset."""

    roi: Bounds
    roi_version: str
    raw_detections: tuple[YoloDetection, ...]
    objects: tuple[DetectedSpatialObject, ...]
    rejected: tuple[WorldYoloRejectedDetection, ...]


def world_yolo_roi_bounds(image_size: tuple[int, int]) -> Bounds:
    """Materialize the conservative center rectangle in source pixels."""

    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("World YOLO image dimensions must be positive.")
    left = math.ceil(width * _ROI_LEFT)
    top = math.ceil(height * _ROI_TOP)
    right = math.floor(width * _ROI_RIGHT)
    bottom = math.floor(height * _ROI_BOTTOM)
    if right <= left or bottom <= top:
        raise ValueError("World YOLO ROI is empty at this image size.")
    return Bounds(left, top, right - left, bottom - top)


@dataclass(frozen=True, slots=True)
class WorldYoloProducer:
    """Turns only explicitly qualified interior detections into World objects."""

    detector: ObjectDetector
    qualification: WorldYoloQualification = WORLD_YOLO_QUALIFICATION

    def __post_init__(self) -> None:
        """Bind the producer to the reviewed model identity and exact class IDs."""

        if self.detector.model_sha256 != self.qualification.model_sha256:
            raise ValueError("World YOLO model SHA-256 differs from the qualified export.")
        if self.detector.class_names != self.qualification.class_names:
            raise ValueError("World YOLO class IDs differ from the qualified export.")
        if self.qualification.roi_version != WORLD_YOLO_ROI_VERSION:
            raise ValueError("World YOLO qualification was reviewed for a different ROI version.")

    def observe(
        self,
        image: Image.Image,
        *,
        hud_bounds: tuple[Bounds, ...] = (),
    ) -> WorldYoloResult:
        """Infer on the original frame, then enforce class, ROI and visible HUD gates."""

        roi = world_yolo_roi_bounds(image.size)
        raw = self.detector.detect(image)
        objects: list[DetectedSpatialObject] = []
        rejected: list[WorldYoloRejectedDetection] = []
        for index, detection in enumerate(raw):
            reasons: list[WorldYoloExclusion] = []
            if not roi.contains_bounds(detection.bounds):
                reasons.append(WorldYoloExclusion.OUTSIDE_ROI)
            if detection.confidence < self.qualification.confidence_threshold:
                reasons.append(WorldYoloExclusion.BELOW_THRESHOLD)
            if detection.label not in self.qualification.qualified_class_map:
                reasons.append(WorldYoloExclusion.UNQUALIFIED_CLASS)
            if any(_intersects(detection.bounds, bounds) for bounds in hud_bounds):
                reasons.append(WorldYoloExclusion.HUD_OVERLAP)
            if reasons:
                rejected.append(WorldYoloRejectedDetection(detection, tuple(reasons)))
                continue
            objects.append(
                DetectedSpatialObject(
                    kind=self.qualification.qualified_class_map[detection.label],
                    bounds=detection.bounds,
                    source_kind=SpatialObjectSourceKind.YOLO,
                    metadata={
                        "model_sha256": self.detector.model_sha256,
                        "confidence": detection.confidence,
                        "confidence_threshold": self.qualification.confidence_threshold,
                        "nms_iou_threshold": self.qualification.nms_iou_threshold,
                        "class_id": detection.class_id,
                        "detection_index": index,
                        "roi_version": WORLD_YOLO_ROI_VERSION,
                        "qualification_review": self.qualification.review_ref,
                    },
                )
            )
        return WorldYoloResult(
            roi=roi,
            roi_version=WORLD_YOLO_ROI_VERSION,
            raw_detections=raw,
            objects=tuple(objects),
            rejected=tuple(rejected),
        )


def _intersects(left: Bounds, right: Bounds) -> bool:
    """Return whether two half-open pixel rectangles overlap."""

    return (
        left.x < right.x + right.width
        and right.x < left.x + left.width
        and left.y < right.y + right.height
        and right.y < left.y + left.height
    )


def load_world_yolo_producer(
    model_path: Path,
    *,
    qualification: WorldYoloQualification = WORLD_YOLO_QUALIFICATION,
) -> WorldYoloProducer:
    """Load a local export using the training owner's reviewed inference contract."""

    detector = YoloOnnxDetector(
        model_path,
        confidence_threshold=qualification.confidence_threshold,
        nms_iou_threshold=qualification.nms_iou_threshold,
    )
    return WorldYoloProducer(detector, qualification)
