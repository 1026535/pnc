"""Bounded tester-annotation exchange for measured control proof.

Machine geometry and provenance never establish that a foreground rectangle is
a named control. A tester attests the control on one persisted frame by writing
a JSON response next to the runner's request file; the runner binds the
response to that frame's artifact hash and session identity before building a
``MeasuredControlProof``. A missing or stale response blocks the case — the
frame age is never extended to wait.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from pnc_automation.app.automation.engine.developmental_control import MeasuredControlProof
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.core.vision.image.models import Bounds

from tools.live_validation.evidence import frame_ref_dict, sha256_file


@dataclass(frozen=True, slots=True)
class AnnotationRequest:
    """One published annotation request bound to a single persisted frame."""

    request_id: str
    case_id: str
    control_name: str
    artifact_path: Path
    artifact_sha256: str
    frame_fingerprint: str
    image_size: tuple[int, int]
    screen_type: str
    frame: dict[str, object]
    issued_at: datetime
    request_path: Path
    response_path: Path


class AnnotationExchange:
    """File-based request/response exchange under one run-local directory."""

    def __init__(
        self,
        directory: Path,
        *,
        timeout_seconds: float = 300.0,
        poll_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._timeout_seconds = timeout_seconds
        self._poll_seconds = poll_seconds
        self._sleep = sleep
        self._now = now
        self._issued = 0

    def prepare(
        self, *, case_id: str, control_name: str, observation: Observation
    ) -> AnnotationRequest:
        """Writes one request file bound to the current persisted frame."""

        if (
            observation.artifact_path is None
            or observation.frame_ref is None
            or observation.image_size is None
            or observation.frame_fingerprint is None
        ):
            raise ValueError(
                "Annotation requests require a persisted, measured, provenanced frame."
            )
        self._issued += 1
        request_id = f"{case_id}-annotate-{self._issued:03d}"
        request_path = self._directory / f"{request_id}.request.json"
        request = AnnotationRequest(
            request_id=request_id,
            case_id=case_id,
            control_name=control_name,
            artifact_path=Path(observation.artifact_path),
            artifact_sha256=sha256_file(Path(observation.artifact_path)),
            frame_fingerprint=observation.frame_fingerprint,
            image_size=tuple(observation.image_size),
            screen_type=observation.screen_type.value,
            frame=frame_ref_dict(observation.frame_ref),
            issued_at=datetime.now(tz=UTC),
            request_path=request_path,
            response_path=self._directory / f"{request_id}.response.json",
        )
        request_path.write_text(
            json.dumps(
                {
                    "request_id": request.request_id,
                    "case_id": request.case_id,
                    "control_name": request.control_name,
                    "artifact_path": str(request.artifact_path),
                    "artifact_sha256": request.artifact_sha256,
                    "frame_fingerprint": request.frame_fingerprint,
                    "image_size": list(request.image_size),
                    "screen_type": request.screen_type,
                    "frame": request.frame,
                    "issued_at": request.issued_at.isoformat(),
                    "instructions": (
                        "Write the sibling .response.json with control_name, "
                        "task_owned_foreground, visual_reason, bounds {x,y,width,height}, "
                        "action_point {x,y}, and intended_effect."
                    ),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return request

    def await_proof(
        self,
        request: AnnotationRequest,
        observation: Observation,
        *,
        foreground_target: HomeCityObjectId,
    ) -> MeasuredControlProof | None:
        """Polls for the response until the bounded deadline; ``None`` on timeout."""

        deadline = self._now() + self._timeout_seconds
        while True:
            if request.response_path.exists():
                proof = self._parse_response(
                    request, observation, foreground_target=foreground_target
                )
                if proof is not None:
                    return proof
                raise ValueError(
                    f"Annotation response {request.response_path.name} failed frame binding."
                )
            if self._now() >= deadline:
                return None
            self._sleep(self._poll_seconds)

    @staticmethod
    def _parse_response(
        request: AnnotationRequest,
        observation: Observation,
        *,
        foreground_target: HomeCityObjectId,
    ) -> MeasuredControlProof | None:
        """Binds the tester's attestation to the request's exact frame."""

        try:
            payload = json.loads(request.response_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("control_name") != request.control_name:
            return None
        if payload.get("artifact_sha256") not in (None, request.artifact_sha256):
            return None
        frame = payload.get("frame")
        if isinstance(frame, dict):
            required = frame_ref_dict(observation.frame_ref)
            for key in ("session_id", "session_epoch", "capture_sequence", "input_sequence"):
                if frame.get(key) != required[key]:
                    return None
        bounds_raw = payload.get("bounds")
        point_raw = payload.get("action_point")
        if not isinstance(bounds_raw, dict) or not isinstance(point_raw, dict):
            return None
        try:
            bounds = Bounds(
                x=int(bounds_raw["x"]),
                y=int(bounds_raw["y"]),
                width=int(bounds_raw["width"]),
                height=int(bounds_raw["height"]),
            )
            action_point = (int(point_raw["x"]), int(point_raw["y"]))
        except (KeyError, TypeError, ValueError):
            return None
        if bounds.width <= 0 or bounds.height <= 0:
            return None
        if not (
            bounds.x <= action_point[0] < bounds.x + bounds.width
            and bounds.y <= action_point[1] < bounds.y + bounds.height
        ):
            return None
        if not isinstance(payload.get("task_owned_foreground"), bool):
            return None
        visual_reason = payload.get("visual_reason")
        if not isinstance(visual_reason, str) or not visual_reason.strip():
            return None
        try:
            intended_effect = WorkflowEffect(str(payload.get("intended_effect")))
        except ValueError:
            return None
        if payload.get("foreground_target") not in (None, foreground_target.value):
            return None
        if (
            observation.frame_ref is None
            or observation.artifact_path is None
            or observation.image_size is None
            or observation.frame_fingerprint is None
        ):
            return None
        return MeasuredControlProof(
            frame_ref=observation.frame_ref,
            artifact_path=Path(observation.artifact_path),
            frame_fingerprint=observation.frame_fingerprint,
            image_size=tuple(observation.image_size),
            decision=observation.decision,
            screen_type=observation.screen_type,
            control_name=request.control_name,
            foreground_target=foreground_target,
            task_owned_foreground=bool(payload["task_owned_foreground"]),
            visual_reason=visual_reason,
            intended_effect=intended_effect,
            bounds=bounds,
            action_point=action_point,
        )
