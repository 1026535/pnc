"""Offline contract and geometry tests for the strict YOLO ONNX adapter."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from pnc_automation.core.vision.detection.yolo_onnx import YoloOnnxContractError, YoloOnnxDetector
from pnc_automation.core.vision.image.models import Bounds


class _FakeValueInfo:
    def __init__(self, name: str, shape: list[int], value_type: str = "tensor(float)") -> None:
        self.name = name
        self.shape = shape
        self.type = value_type


class _FakeMeta:
    def __init__(self, metadata: dict[str, str]) -> None:
        self.custom_metadata_map = metadata


class _FakeSessionOptions:
    intra_op_num_threads: int | None = None


class _FakeSession:
    def __init__(
        self,
        output: np.ndarray,
        *,
        input_shape: list[int] | None = None,
        output_shape: list[int] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.output = output
        self.input_shape = input_shape or [1, 3, 8, 8]
        self.output_shape = output_shape or [1, len(output[0]), 6]
        self.metadata = metadata or {
            "end2end": "True",
            "task": "detect",
            "names": "{0: 'alpha', 1: 'beta'}",
        }
        self.feed: dict[str, np.ndarray] | None = None

    def get_modelmeta(self) -> _FakeMeta:
        return _FakeMeta(self.metadata)

    def get_inputs(self) -> list[_FakeValueInfo]:
        return [_FakeValueInfo("images", self.input_shape)]

    def get_outputs(self) -> list[_FakeValueInfo]:
        return [_FakeValueInfo("output0", self.output_shape)]

    def run(self, output_names: list[str], feed: dict[str, np.ndarray]) -> list[np.ndarray]:
        self.feed = feed
        return [self.output]


_EMBEDDED_NMS_METADATA = {
    "end2end": "False",
    "task": "detect",
    "names": "{0: 'alpha', 1: 'beta'}",
    "args": "{'nms': True}",
}


class _FakeOrt(types.SimpleNamespace):
    def __init__(self, session: _FakeSession) -> None:
        super().__init__()
        self.session = session
        self.options: _FakeSessionOptions | None = None

        def session_options() -> _FakeSessionOptions:
            self.options = _FakeSessionOptions()
            return self.options

        def inference_session(
            path: str,
            *,
            sess_options: _FakeSessionOptions,
            providers: list[str],
        ) -> _FakeSession:
            del path
            self.options = sess_options
            self.providers = providers
            return self.session

        self.SessionOptions = session_options
        self.InferenceSession = inference_session


class YoloOnnxDetectorTests(unittest.TestCase):
    def _detector(
        self,
        session: _FakeSession,
        *,
        confidence_threshold: float = 0.35,
        nms_iou_threshold: float = 0.7,
    ) -> tuple[YoloOnnxDetector, _FakeOrt, tempfile.TemporaryDirectory[str]]:
        temp_dir = tempfile.TemporaryDirectory()
        model_path = Path(temp_dir.name) / "model.onnx"
        model_path.write_bytes(b"fake model")
        fake_ort = _FakeOrt(session)
        with patch.dict(sys.modules, {"onnxruntime": fake_ort}):
            detector = YoloOnnxDetector(
                model_path,
                confidence_threshold=confidence_threshold,
                nms_iou_threshold=nms_iou_threshold,
            )
        return detector, fake_ort, temp_dir

    def test_rectangular_letterbox_inverse_clips_and_stably_sorts(self) -> None:
        output = np.array(
            [
                [
                    [0.0, 2.0, 8.0, 6.0, 0.80, 0.0],
                    [1.0, 3.0, 9.0, 6.0, 0.80, 1.0],
                    [0.0, 0.0, 1.0, 1.0, 0.90, 1.0],
                    [5.9, 3.0, 5.1, 4.0, 0.95, 0.0],
                    [0.0, 0.0, 8.0, 8.0, 0.20, 0.0],
                ]
            ],
            dtype=np.float32,
        )
        session = _FakeSession(output)
        detector, fake_ort, temp_dir = self._detector(session)
        self.addCleanup(temp_dir.cleanup)

        detections = detector.detect(Image.new("RGB", (8, 4), (10, 20, 30)))

        self.assertEqual(detector.input_size, (8, 8))
        self.assertEqual(detector.class_names, ("alpha", "beta"))
        self.assertEqual([d.class_id for d in detections], [0, 1])
        self.assertEqual(
            [d.bounds for d in detections],
            [Bounds(x=0, y=0, width=8, height=4), Bounds(x=1, y=1, width=7, height=3)],
        )
        self.assertAlmostEqual(detections[0].confidence, 0.8)
        self.assertAlmostEqual(detections[1].confidence, 0.8)
        assert session.feed is not None
        tensor = session.feed["images"]
        self.assertEqual(tensor.shape, (1, 3, 8, 8))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertTrue(np.all(tensor[:, :, :2, :] == np.float32(114 / 255)))
        self.assertEqual(fake_ort.options.intra_op_num_threads, 2)
        self.assertEqual(fake_ort.providers, ["CPUExecutionProvider"])

    def test_hash_matches_loaded_model_bytes(self) -> None:
        session = _FakeSession(np.zeros((1, 1, 6), dtype=np.float32))
        detector, _, temp_dir = self._detector(session)
        self.addCleanup(temp_dir.cleanup)
        expected = hashlib.sha256(b"fake model").hexdigest()
        self.assertEqual(detector.model_sha256, expected)

    def test_nonfinite_output_is_rejected_even_below_threshold(self) -> None:
        output = np.array([[[np.nan, 0, 1, 1, 0.1, 0]]], dtype=np.float32)
        session = _FakeSession(output)
        detector, _, temp_dir = self._detector(session)
        self.addCleanup(temp_dir.cleanup)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            detector.detect(Image.new("RGB", (8, 8)))

    def test_score_range_and_retained_class_contract_are_rejected(self) -> None:
        for row, message in (
            ([[0, 0, 2, 2, 1.1, 0]], r"outside \[0, 1\]"),
            ([[0, 0, 2, 2, 0.9, 0.5]], "non-integral class id"),
            ([[0, 0, 2, 2, 0.9, 2]], "outside the model class range"),
        ):
            session = _FakeSession(np.array([row], dtype=np.float32))
            detector, _, temp_dir = self._detector(session)
            self.addCleanup(temp_dir.cleanup)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                detector.detect(Image.new("RGB", (8, 8)))

    def test_low_confidence_row_does_not_require_valid_class_id(self) -> None:
        output = np.array([[[0, 0, 2, 2, 0.1, 99]]], dtype=np.float32)
        session = _FakeSession(output)
        detector, _, temp_dir = self._detector(session)
        self.addCleanup(temp_dir.cleanup)
        self.assertEqual(detector.detect(Image.new("RGB", (8, 8))), ())

    def test_embedded_nms_export_metadata_is_accepted(self) -> None:
        accepted = (
            {"end2end": "True", "task": "detect", "names": "{0: 'a'}"},
            {"end2end": "True", "task": "detect", "names": "{0: 'a'}", "args": "{'nms': False}"},
            {"end2end": "False", "task": "detect", "names": "{0: 'a'}", "args": "{'nms': True}"},
            {
                "end2end": "False",
                "task": "detect",
                "names": "{0: 'a'}",
                "args": "{'data': None, 'batch': 1, 'nms': True, 'dynamic': False, 'simplify': False}",
            },
        )
        for metadata in accepted:
            session = _FakeSession(np.zeros((1, 1, 6), dtype=np.float32), metadata=metadata)
            with tempfile.TemporaryDirectory() as temp_dir:
                model_path = Path(temp_dir) / "model.onnx"
                model_path.write_bytes(b"fake model")
                with patch.dict(sys.modules, {"onnxruntime": _FakeOrt(session)}):
                    with self.subTest(metadata=metadata):
                        detector = YoloOnnxDetector(model_path)
                        self.assertEqual(detector.class_names, ("a",))

    def test_embedded_nms_export_metadata_is_rejected_without_nms(self) -> None:
        rejected = (
            {"end2end": "False", "task": "detect", "names": "{0: 'a'}"},
            {"end2end": "False", "task": "detect", "names": "{0: 'a'}", "args": "not-a-literal"},
            {"end2end": "False", "task": "detect", "names": "{0: 'a'}", "args": "['nms', True]"},
            {"end2end": "False", "task": "detect", "names": "{0: 'a'}", "args": "{'nms': False}"},
            {"end2end": "False", "task": "detect", "names": "{0: 'a'}", "args": "{'batch': 1}"},
            {"end2end": "False", "task": "detect", "names": "{0: 'a'}", "args": "{'nms': 1}"},
            {"task": "detect", "names": "{0: 'a'}", "args": "{'nms': True}"},
            {"end2end": "yes", "task": "detect", "names": "{0: 'a'}", "args": "{'nms': True}"},
        )
        for metadata in rejected:
            session = _FakeSession(np.zeros((1, 1, 6), dtype=np.float32), metadata=metadata)
            with tempfile.TemporaryDirectory() as temp_dir:
                model_path = Path(temp_dir) / "model.onnx"
                model_path.write_bytes(b"fake model")
                with patch.dict(sys.modules, {"onnxruntime": _FakeOrt(session)}):
                    with self.subTest(metadata=metadata):
                        with self.assertRaises(YoloOnnxContractError):
                            YoloOnnxDetector(model_path)

    def test_class_aware_nms_suppresses_only_same_class_duplicates(self) -> None:
        output = np.array(
            [
                [
                    [2.0, 1.0, 6.0, 5.0, 0.60, 0.0],
                    [1.0, 1.0, 5.0, 5.0, 0.90, 0.0],
                    [1.0, 1.0, 5.0, 5.0, 0.80, 0.0],
                    [1.0, 1.0, 5.0, 5.0, 0.70, 1.0],
                    [1.0, 1.0, 5.0, 6.0, 0.50, 0.0],
                ]
            ],
            dtype=np.float32,
        )
        session = _FakeSession(output, metadata=_EMBEDDED_NMS_METADATA)
        detector, _, temp_dir = self._detector(session)
        self.addCleanup(temp_dir.cleanup)

        detections = detector.detect(Image.new("RGB", (8, 8)))

        self.assertEqual([d.class_id for d in detections], [0, 1, 0])
        self.assertEqual(
            [d.bounds for d in detections],
            [Bounds(x=1, y=1, width=4, height=4)] * 2 + [Bounds(x=2, y=1, width=4, height=4)],
        )
        self.assertEqual([round(d.confidence, 2) for d in detections], [0.9, 0.7, 0.6])

    def test_nms_iou_threshold_parameter_controls_suppression(self) -> None:
        output = np.array(
            [
                [
                    [1.0, 1.0, 5.0, 5.0, 0.90, 0.0],
                    [2.0, 1.0, 6.0, 5.0, 0.60, 0.0],
                ]
            ],
            dtype=np.float32,
        )
        kept_session = _FakeSession(output, metadata=_EMBEDDED_NMS_METADATA)
        kept_detector, _, kept_dir = self._detector(kept_session, nms_iou_threshold=0.7)
        self.addCleanup(kept_dir.cleanup)
        self.assertEqual(len(kept_detector.detect(Image.new("RGB", (8, 8)))), 2)

        suppressed_session = _FakeSession(output, metadata=_EMBEDDED_NMS_METADATA)
        suppressed_detector, _, suppressed_dir = self._detector(
            suppressed_session, nms_iou_threshold=0.5
        )
        self.addCleanup(suppressed_dir.cleanup)
        detections = suppressed_detector.detect(Image.new("RGB", (8, 8)))
        self.assertEqual(len(detections), 1)
        self.assertAlmostEqual(detections[0].confidence, 0.9)

    def test_end_to_end_export_preserves_its_original_detection_rows(self) -> None:
        output = np.array([[[1, 1, 5, 5, 0.9, 0], [1, 1, 5, 5, 0.8, 0]]], dtype=np.float32)
        detector, _, temp_dir = self._detector(_FakeSession(output))
        self.addCleanup(temp_dir.cleanup)

        self.assertEqual(len(detector.detect(Image.new("RGB", (8, 8)))), 2)

    def test_nms_iou_threshold_is_validated(self) -> None:
        for bad_value in (True, -0.1, 1.1, float("nan"), "0.7"):
            with tempfile.TemporaryDirectory() as temp_dir:
                model_path = Path(temp_dir) / "model.onnx"
                model_path.write_bytes(b"fake model")
                with self.subTest(bad_value=bad_value):
                    with self.assertRaises(ValueError):
                        YoloOnnxDetector(model_path, nms_iou_threshold=bad_value)

    def test_full_class_id_order_maps_stable_labels(self) -> None:
        names = (
            "{0: 'monster', 1: 'farm', 2: 'castle', 3: 'hell_fortress', 4: 'border_stone',"
            " 5: 'castle_away_marker', 6: 'alliance_fort', 7: 'gate_of_the_abyss',"
            " 8: 'alliance_warehouse', 9: 'alliance_infirmary', 10: 'treasure_goblin',"
            " 11: 'lumber_camp', 12: 'iron_mine', 13: 'gold_mine', 14: 'diamond_mine',"
            " 15: 'alliance_farm', 16: 'alliance_lumber_camp'}"
        )
        metadata = {
            "end2end": "False",
            "task": "detect",
            "names": names,
            "args": "{'nms': True}",
        }
        output = np.array(
            [[[0.0, 0.0, 2.0, 2.0, 0.9, 16.0], [4.0, 4.0, 6.0, 6.0, 0.8, 2.0]]],
            dtype=np.float32,
        )
        session = _FakeSession(output, metadata=metadata)
        detector, _, temp_dir = self._detector(session)
        self.addCleanup(temp_dir.cleanup)

        detections = detector.detect(Image.new("RGB", (8, 8)))

        self.assertEqual(len(detector.class_names), 17)
        self.assertEqual(detector.class_names[16], "alliance_lumber_camp")
        self.assertEqual(
            [(d.class_id, d.label) for d in detections],
            [(16, "alliance_lumber_camp"), (2, "castle")],
        )

    def test_metadata_and_static_contract_are_strict(self) -> None:
        cases = (
            ({"end2end": "False", "task": "detect", "names": "{0: 'a'}"}, None, None),
            (
                {"end2end": "False", "task": "detect", "names": "{0: 'a'}", "args": "{'nms': True}"},
                [1, 3, "dynamic", 8],
                None,
            ),
            ({"end2end": "True", "task": "classify", "names": "{0: 'a'}"}, None, None),
            ({"end2end": "True", "task": "detect", "names": "{1: 'a'}"}, None, None),
            ({"end2end": "True", "task": "detect", "names": "{}"}, None, None),
            ({"end2end": "True", "task": "detect", "names": "{0: '  '}"}, None, None),
            ({"end2end": "True", "task": "detect", "names": "{0: 'a', 1: 'a'}"}, None, None),
            (None, [1, 3, "dynamic", 8], None),
            (None, None, [1, 4, 5]),
        )
        for metadata, input_shape, output_shape in cases:
            session = _FakeSession(
                np.zeros((1, 1, 6), dtype=np.float32),
                metadata=metadata,
                input_shape=input_shape,
                output_shape=output_shape,
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                model_path = Path(temp_dir) / "model.onnx"
                model_path.write_bytes(b"fake model")
                with patch.dict(sys.modules, {"onnxruntime": _FakeOrt(session)}):
                    with self.subTest(metadata=metadata, input_shape=input_shape, output_shape=output_shape):
                        with self.assertRaises(YoloOnnxContractError):
                            YoloOnnxDetector(model_path)


if __name__ == "__main__":
    unittest.main()
