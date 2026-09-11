"""Object detection services backed by explicit, typed model contracts."""

from pnc_automation.core.vision.detection.yolo_onnx import (
    YoloDetection,
    YoloOnnxContractError,
    YoloOnnxDetector,
)

__all__ = ["YoloDetection", "YoloOnnxContractError", "YoloOnnxDetector"]
