"""Strict ONNX Runtime adapter for Ultralytics YOLO end-to-end exports."""

from __future__ import annotations

import ast
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from pnc_automation.core.vision.image.models import Bounds


class YoloOnnxContractError(ValueError):
    """Raised when an ONNX model does not satisfy the detector contract."""


@dataclass(frozen=True, slots=True)
class YoloDetection:
    """One source-image-space detection emitted by :class:`YoloOnnxDetector`."""

    class_id: int
    label: str
    confidence: float
    bounds: Bounds


class YoloOnnxDetector:
    """Runs one strict Ultralytics YOLO end-to-end ONNX detection model.

    The model must have one static ``float32`` input shaped ``[1, 3, H, W]``
    and one static ``float32`` output shaped ``[1, N, 6]``. Output rows are
    ``xyxy, confidence, class_id`` in the letterboxed input coordinate space.
    """

    __slots__ = (
        "_class_names",
        "_input_name",
        "_input_size",
        "_model_sha256",
        "_output_name",
        "_output_count",
        "_confidence_threshold",
        "_session",
        "_source_model_path",
    )

    def __init__(
        self,
        model_path: Path,
        *,
        confidence_threshold: float = 0.35,
        num_threads: int = 2,
    ) -> None:
        """Load and validate one model without downloading or selecting alternatives."""

        if not isinstance(model_path, Path):
            raise TypeError("model_path must be a pathlib.Path")
        if not model_path.is_file():
            raise FileNotFoundError(f"YOLO ONNX model does not exist: {model_path}")
        if not isinstance(confidence_threshold, (float, int)) or isinstance(confidence_threshold, bool):
            raise ValueError("confidence_threshold must be a finite number between 0.0 and 1.0")
        if not math.isfinite(float(confidence_threshold)) or not 0.0 <= float(confidence_threshold) <= 1.0:
            raise ValueError("confidence_threshold must be a finite number between 0.0 and 1.0")
        if not isinstance(num_threads, int) or isinstance(num_threads, bool) or num_threads <= 0:
            raise ValueError("num_threads must be a positive integer")

        # Import only when a detector is constructed. Importing the vision
        # package itself must remain possible on systems without ORT installed.
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("onnxruntime is required for YOLO ONNX detection") from exc

        self._source_model_path = model_path
        self._model_sha256 = _sha256_file(model_path)
        self._confidence_threshold = float(confidence_threshold)

        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = num_threads
        self._session = ort.InferenceSession(
            str(model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )

        self._class_names = _parse_model_metadata(self._session)
        input_name, input_height, input_width = _validate_input_contract(self._session)
        output_name, output_count = _validate_output_contract(self._session)
        self._input_name = input_name
        self._output_name = output_name
        self._output_count = output_count
        # Public image-size APIs use Pillow's (width, height) order. The ORT
        # tensor contract above remains explicit as [1, 3, height, width].
        self._input_size = (input_width, input_height)

    @property
    def class_names(self) -> tuple[str, ...]:
        """Returns model class labels in their contiguous class-id order."""

        return self._class_names

    @property
    def model_sha256(self) -> str:
        """Returns the SHA-256 digest of the exact model file loaded by ORT."""

        return self._model_sha256

    @property
    def input_size(self) -> tuple[int, int]:
        """Returns the model input size as ``(width, height)``."""

        return self._input_size

    def detect(self, image: Image.Image) -> tuple[YoloDetection, ...]:
        """Detect objects in one PIL image and return stable confidence order."""

        if not isinstance(image, Image.Image):
            raise TypeError("image must be a PIL.Image.Image")
        source_width, source_height = image.size
        if source_width <= 0 or source_height <= 0:
            raise ValueError("image must have positive width and height")

        tensor, scale, pad_left, pad_top = _letterbox_rgb(image, self._input_size)
        raw_outputs = self._session.run([self._output_name], {self._input_name: tensor})
        if not isinstance(raw_outputs, (list, tuple)) or len(raw_outputs) != 1:
            raise RuntimeError("YOLO ONNX inference returned an unexpected output count")

        output = np.asarray(raw_outputs[0])
        expected_shape = (1, self._output_count, 6)
        if output.shape != expected_shape:
            raise RuntimeError(
                f"YOLO ONNX inference returned shape {output.shape}; expected {expected_shape}"
            )
        if not np.issubdtype(output.dtype, np.floating):
            raise RuntimeError("YOLO ONNX inference output must contain floating-point values")
        if not np.isfinite(output).all():
            raise ValueError("YOLO ONNX inference returned non-finite detection values")

        rows = output[0]
        detections: list[tuple[int, YoloDetection]] = []
        for row_index, row in enumerate(rows):
            x1, y1, x2, y2, confidence_value, class_value = (float(value) for value in row)
            if not 0.0 <= confidence_value <= 1.0:
                raise ValueError(
                    f"YOLO ONNX inference returned confidence outside [0, 1] at row {row_index}"
                )
            if confidence_value < self._confidence_threshold:
                continue
            if not class_value.is_integer():
                raise ValueError(
                    f"YOLO ONNX retained row {row_index} has a non-integral class id {class_value}"
                )
            class_id = int(class_value)
            if class_id < 0 or class_id >= len(self._class_names):
                raise ValueError(
                    f"YOLO ONNX retained row {row_index} has class id {class_id} outside the model class range"
                )

            bounds = _source_bounds(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                scale=scale,
                pad_left=pad_left,
                pad_top=pad_top,
                source_width=source_width,
                source_height=source_height,
            )
            if bounds is None:
                continue
            detections.append(
                (
                    row_index,
                    YoloDetection(
                        class_id=class_id,
                        label=self._class_names[class_id],
                        confidence=confidence_value,
                        bounds=bounds,
                    ),
                )
            )

        # Python's sort is stable, so equal-confidence rows retain model order.
        detections.sort(key=lambda item: -item[1].confidence)
        return tuple(detection for _, detection in detections)


def _sha256_file(path: Path) -> str:
    """Hash a model without loading the whole artifact into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_model_metadata(session: Any) -> tuple[str, ...]:
    """Validate the exact metadata contract and parse names safely."""

    model_meta = session.get_modelmeta()
    metadata = getattr(model_meta, "custom_metadata_map", None)
    if not isinstance(metadata, dict):
        raise YoloOnnxContractError("YOLO ONNX model metadata must expose custom_metadata_map")
    if metadata.get("end2end") != "True":
        raise YoloOnnxContractError("YOLO ONNX model metadata must declare end2end=True")
    if metadata.get("task") != "detect":
        raise YoloOnnxContractError("YOLO ONNX model metadata must declare task=detect")

    raw_names = metadata.get("names")
    if not isinstance(raw_names, str):
        raise YoloOnnxContractError("YOLO ONNX model metadata must contain names as a Python literal dict")
    try:
        names = ast.literal_eval(raw_names)
    except (SyntaxError, ValueError, TypeError) as exc:
        raise YoloOnnxContractError("YOLO ONNX model metadata names is not a valid Python literal") from exc
    if (
        not isinstance(names, dict)
        or not names
        or any(
            type(key) is not int
            or not isinstance(value, str)
            or not value.strip()
            for key, value in names.items()
        )
        or len(set(names.values())) != len(names)
    ):
        raise YoloOnnxContractError("YOLO ONNX metadata names must be a dict[int, str]")
    expected_ids = set(range(len(names)))
    if set(names) != expected_ids:
        raise YoloOnnxContractError("YOLO ONNX metadata names must use contiguous class ids starting at zero")
    return tuple(names[class_id] for class_id in range(len(names)))


def _validate_input_contract(session: Any) -> tuple[str, int, int]:
    """Validate and return input name, height, and width."""

    inputs = session.get_inputs()
    if len(inputs) != 1:
        raise YoloOnnxContractError("YOLO ONNX model must expose exactly one input")
    model_input = inputs[0]
    input_name = getattr(model_input, "name", None)
    input_type = getattr(model_input, "type", None)
    input_shape = getattr(model_input, "shape", None)
    if not isinstance(input_name, str) or not input_name:
        raise YoloOnnxContractError("YOLO ONNX input must have a non-empty name")
    if input_type != "tensor(float)":
        raise YoloOnnxContractError("YOLO ONNX input must have type tensor(float)")
    if not _is_static_positive_shape(input_shape, 4) or tuple(input_shape[:2]) != (1, 3):
        raise YoloOnnxContractError("YOLO ONNX input must have static shape [1, 3, H, W]")
    input_height, input_width = input_shape[2], input_shape[3]
    return input_name, input_height, input_width


def _validate_output_contract(session: Any) -> tuple[str, int]:
    """Validate and return output name and detection row count."""

    outputs = session.get_outputs()
    if len(outputs) != 1:
        raise YoloOnnxContractError("YOLO ONNX model must expose exactly one output")
    model_output = outputs[0]
    output_name = getattr(model_output, "name", None)
    output_type = getattr(model_output, "type", None)
    output_shape = getattr(model_output, "shape", None)
    if not isinstance(output_name, str) or not output_name:
        raise YoloOnnxContractError("YOLO ONNX output must have a non-empty name")
    if output_type != "tensor(float)":
        raise YoloOnnxContractError("YOLO ONNX output must have type tensor(float)")
    if not _is_static_positive_shape(output_shape, 3) or output_shape[0] != 1 or output_shape[2] != 6:
        raise YoloOnnxContractError("YOLO ONNX output must have static shape [1, N, 6]")
    return output_name, output_shape[1]


def _is_static_positive_shape(shape: Any, rank: int) -> bool:
    """Return whether a runtime shape is a concrete positive integer tuple."""

    if not isinstance(shape, (list, tuple)) or len(shape) != rank:
        return False
    return all(type(dimension) is int and dimension > 0 for dimension in shape)


def _letterbox_rgb(
    image: Image.Image,
    input_size: tuple[int, int],
) -> tuple[np.ndarray, float, int, int]:
    """Build a centered RGB letterbox tensor and return its geometric transform."""

    input_width, input_height = input_size
    source_width, source_height = image.size
    scale = min(input_width / source_width, input_height / source_height)
    resized_width = max(1, int(round(source_width * scale)))
    resized_height = max(1, int(round(source_height * scale)))
    rgb = np.asarray(image.convert("RGB"))
    resized = cv2.resize(rgb, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((input_height, input_width, 3), 114, dtype=np.uint8)
    pad_left = (input_width - resized_width) // 2
    pad_top = (input_height - resized_height) // 2
    canvas[pad_top : pad_top + resized_height, pad_left : pad_left + resized_width] = resized
    tensor = np.transpose(canvas, (2, 0, 1))[None].astype(np.float32) / 255.0
    return tensor, scale, pad_left, pad_top


def _source_bounds(
    *,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    scale: float,
    pad_left: int,
    pad_top: int,
    source_width: int,
    source_height: int,
) -> Bounds | None:
    """Invert one box, clamp it to the source image, and reject empty boxes."""

    if x2 <= x1 or y2 <= y1:
        return None
    source_x1 = (x1 - pad_left) / scale
    source_y1 = (y1 - pad_top) / scale
    source_x2 = (x2 - pad_left) / scale
    source_y2 = (y2 - pad_top) / scale
    left = max(0, min(source_width, math.floor(source_x1)))
    top = max(0, min(source_height, math.floor(source_y1)))
    right = max(0, min(source_width, math.ceil(source_x2)))
    bottom = max(0, min(source_height, math.ceil(source_y2)))
    if right <= left or bottom <= top:
        return None
    return Bounds(x=left, y=top, width=right - left, height=bottom - top)
