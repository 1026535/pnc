"""Interface shared by production and diagnostic object-detection consumers."""

from __future__ import annotations

from typing import Protocol

from PIL import Image

from pnc_automation.core.vision.detection.yolo_onnx import YoloDetection


class ObjectDetector(Protocol):
    """A loaded local model with a fixed class catalog and pixel-space output."""

    class_names: tuple[str, ...]
    model_sha256: str

    def detect(self, image: Image.Image) -> tuple[YoloDetection, ...]: ...
