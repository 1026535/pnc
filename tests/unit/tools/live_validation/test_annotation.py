"""Tester-annotation exchange binding tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.developmental_control import MeasuredControlProof
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tools.live_validation.annotation import AnnotationExchange
from tools.live_validation.evidence import frame_ref_dict, sha256_file

from tests.unit.tools.live_validation.helpers import (
    home_observation,
    write_frame_file,
)


def _exchange(directory: Path, **kwargs) -> AnnotationExchange:
    clock = {"t": 0.0}
    return AnnotationExchange(
        directory,
        timeout_seconds=kwargs.pop("timeout_seconds", 5.0),
        poll_seconds=1.0,
        sleep=lambda seconds: clock.__setitem__("t", clock["t"] + seconds),
        now=lambda: clock["t"],
        **kwargs,
    )


def _response(request, **overrides) -> dict:
    payload = {
        "request_id": request.request_id,
        "case_id": request.case_id,
        "control_name": request.control_name,
        "foreground_target": request.foreground_target,
        "artifact_path": str(request.artifact_path),
        "artifact_sha256": request.artifact_sha256,
        "frame": request.frame,
        "bounds": {"x": 100, "y": 800, "width": 200, "height": 60},
        "action_point": {"x": 200, "y": 830},
        "task_owned_foreground": True,
        "visual_reason": "bottom-left back affordance inside the panel frame",
        "intended_effect": "nonspending_state_change",
    }
    payload.update(overrides)
    return payload


class AnnotationExchangeTests(unittest.TestCase):
    def test_prepare_binds_request_to_the_persisted_frame(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            artifact = write_frame_file(tmp, "frame.png")
            observation = home_observation(
                artifact_path=artifact,
                sequence=4,
                screen_type=ScreenType.PNC_WATCHTOWER,
            )
            request = _exchange(tmp / "exchange").prepare(
                case_id="v44_bank_return_home",
                control_name="return_home",
                foreground_target=HomeCityObjectId.BANK,
                observation=observation,
            )
            doc = json.loads(request.request_path.read_text(encoding="utf-8"))
            artifact_sha = sha256_file(artifact)
        self.assertEqual("v44_bank_return_home-annotate-001", doc["request_id"])
        self.assertEqual(artifact_sha, doc["artifact_sha256"])
        self.assertEqual(frame_ref_dict(observation.frame_ref), doc["frame"])
        self.assertEqual("fp-4", doc["frame_fingerprint"])
        self.assertEqual([540, 960], doc["image_size"])
        self.assertEqual(ScreenType.PNC_WATCHTOWER.value, doc["screen_type"])
        self.assertTrue(request.response_path.name.endswith(".response.json"))

    def test_prepare_rejects_unprovenanced_frames(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            artifact = write_frame_file(tmp, "frame.png")
            bare = home_observation(artifact_path=artifact)
            object.__setattr__(bare, "frame_ref", None)
            with self.assertRaises(ValueError):
                _exchange(tmp / "exchange").prepare(
                    case_id="v44_bank_return_home",
                    control_name="return_home",
                    foreground_target=HomeCityObjectId.BANK,
                    observation=bare,
                )

    def test_valid_response_produces_a_typed_proof(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            artifact = write_frame_file(tmp, "frame.png")
            observation = home_observation(artifact_path=artifact)
            exchange = _exchange(tmp / "exchange")
            request = exchange.prepare(
                case_id="v44_bank_return_home",
                control_name="return_home",
                foreground_target=HomeCityObjectId.BANK,
                observation=observation,
            )
            request.response_path.write_text(
                json.dumps(_response(request)), encoding="utf-8"
            )
            proof = exchange.await_proof(
                request, observation, foreground_target=HomeCityObjectId.BANK
            )
        self.assertIsInstance(proof, MeasuredControlProof)
        self.assertEqual("return_home", proof.control_name)
        self.assertIs(HomeCityObjectId.BANK, proof.foreground_target)
        self.assertTrue(proof.task_owned_foreground)
        self.assertEqual((200, 830), proof.action_point)
        self.assertIs(WorkflowEffect.NONSPENDING_STATE_CHANGE, proof.intended_effect)
        self.assertEqual(observation.frame_ref, proof.frame_ref)

    def test_wrong_artifact_hash_is_rejected_not_returned(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            artifact = write_frame_file(tmp, "frame.png")
            observation = home_observation(artifact_path=artifact)
            exchange = _exchange(tmp / "exchange")
            request = exchange.prepare(
                case_id="v44_bank_return_home",
                control_name="return_home",
                foreground_target=HomeCityObjectId.BANK,
                observation=observation,
            )
            request.response_path.write_text(
                json.dumps(_response(request, artifact_sha256="f" * 64)),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                exchange.await_proof(
                    request, observation, foreground_target=HomeCityObjectId.BANK
                )

    def test_action_point_outside_bounds_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            artifact = write_frame_file(tmp, "frame.png")
            observation = home_observation(artifact_path=artifact)
            exchange = _exchange(tmp / "exchange")
            request = exchange.prepare(
                case_id="v44_bank_return_home",
                control_name="return_home",
                foreground_target=HomeCityObjectId.BANK,
                observation=observation,
            )
            request.response_path.write_text(
                json.dumps(_response(request, action_point={"x": 9999, "y": 9999})),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                exchange.await_proof(
                    request, observation, foreground_target=HomeCityObjectId.BANK
                )

    def test_timeout_returns_none(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            artifact = write_frame_file(tmp, "frame.png")
            observation = home_observation(artifact_path=artifact)
            exchange = _exchange(tmp / "exchange")
            request = exchange.prepare(
                case_id="v44_bank_return_home",
                control_name="return_home",
                foreground_target=HomeCityObjectId.BANK,
                observation=observation,
            )
            self.assertIsNone(
                exchange.await_proof(
                    request, observation, foreground_target=HomeCityObjectId.BANK
                )
            )


if __name__ == "__main__":
    unittest.main()
