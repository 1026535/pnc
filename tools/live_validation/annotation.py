"""Bounded tester-annotation exchange for measured control proof.

Machine geometry and provenance never establish that a foreground rectangle is
a named control. A tester attests the control on one persisted frame by writing
a JSON response next to the runner's request file; the runner binds the
response to that frame's artifact hash and session identity before building a
``MeasuredControlProof``. A missing or stale response blocks the case — the
frame age is never extended to wait.

A frozen case may instead declare ``measurement_selector_id`` to name a
reviewed canonical selector whose current-frame template element supplies the
measurement. ``selector_proof`` generates that response in-process from the
observation's own provenanced element — no external await, no free-form
bounds — and persists it through the same response contract so journal and
validator provenance stay inspectable. The selector identifies the visible
control only; it claims no destination.
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
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import DetectionKind, build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.image.models import Bounds

from tools.live_validation.evidence import frame_ref_dict, sha256_file


@dataclass(frozen=True, slots=True)
class AnnotationRequest:
    """One published annotation request bound to a single persisted frame."""

    request_id: str
    case_id: str
    control_name: str
    foreground_target: str
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
        self,
        *,
        case_id: str,
        control_name: str,
        foreground_target: HomeCityObjectId,
        observation: Observation,
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
            foreground_target=foreground_target.value,
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
                    "foreground_target": request.foreground_target,
                    "artifact_path": str(request.artifact_path),
                    "artifact_sha256": request.artifact_sha256,
                    "frame_fingerprint": request.frame_fingerprint,
                    "image_size": list(request.image_size),
                    "screen_type": request.screen_type,
                    "frame": request.frame,
                    "issued_at": request.issued_at.isoformat(),
                    "instructions": (
                        "Write the sibling .response.json echoing request_id, case_id, "
                        "control_name, foreground_target, artifact_path, artifact_sha256, "
                        "and frame exactly, plus task_owned_foreground, visual_reason, "
                        "bounds {x,y,width,height}, action_point {x,y}, and intended_effect."
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

    def selector_proof(
        self,
        request: AnnotationRequest,
        observation: Observation,
        *,
        selector_id: UiElementId,
        foreground_target: HomeCityObjectId,
        intended_effect: WorkflowEffect,
    ) -> MeasuredControlProof:
        """Builds the typed proof from the observation's canonical selector element.

        For a frozen case declaring ``measurement_selector_id`` the current
        frame's own template-matched element — never a tester attestation or
        free-form bounds — supplies the measurement. The element must be the
        registry's ``TEMPLATE``/``action`` selector declared on this screen,
        carry this frame's provenance, stay inside the native image, and reach
        the catalog's qualified confidence; any gap raises
        ``SelectorResolutionError`` so a missing, stale, or foreign element
        can never silently authorize input. The generated response persists
        beside the request and parses through the same typed contract as a
        tester attestation.
        """

        registry = build_default_selector_registry()
        definition = registry.require_supported(selector_id)
        if (
            definition.detection_kind is not DetectionKind.TEMPLATE
            or definition.interaction_kind is not SelectorInteractionKind.ACTION
        ):
            raise SelectorResolutionError(
                f"Selector measurement requires a template action selector; "
                f"'{selector_id.value}' is not one.",
                selector_id=selector_id,
            )
        if observation.screen_type not in definition.screens:
            raise SelectorResolutionError(
                f"Selector '{selector_id.value}' is not declared on "
                f"'{observation.screen_type.value}'.",
                selector_id=selector_id,
                screen_type=observation.screen_type.value,
            )
        element = observation.visible_elements.get(selector_id)
        if element is None or element.source_kind is not VisibleElementSourceKind.TEMPLATE:
            raise SelectorResolutionError(
                f"Selector '{selector_id.value}' has no current-frame template element.",
                selector_id=selector_id,
            )
        if (
            element.frame_ref is None
            or element.frame_ref != observation.frame_ref
            or element.source_screen != observation.screen_type
            or element.source_layout_id != observation.decision.layout_id
        ):
            raise SelectorResolutionError(
                f"Selector '{selector_id.value}' element is not bound to this frame.",
                selector_id=selector_id,
            )
        if observation.image_size is None or not Bounds(
            0, 0, *observation.image_size
        ).contains_bounds(element.bounds):
            raise SelectorResolutionError(
                f"Selector '{selector_id.value}' bounds leave the native image.",
                selector_id=selector_id,
            )
        if element.confidence < definition.threshold:
            raise SelectorResolutionError(
                f"Selector '{selector_id.value}' confidence {element.confidence:.4f} "
                f"is below the catalog threshold {definition.threshold:.2f}.",
                selector_id=selector_id,
            )
        action_point = element.action_point or element.bounds.center()
        request.response_path.write_text(
            json.dumps(
                {
                    "request_id": request.request_id,
                    "case_id": request.case_id,
                    "control_name": request.control_name,
                    "foreground_target": request.foreground_target,
                    "artifact_path": str(request.artifact_path),
                    "artifact_sha256": request.artifact_sha256,
                    "frame": frame_ref_dict(observation.frame_ref),
                    "bounds": {
                        "x": element.bounds.x,
                        "y": element.bounds.y,
                        "width": element.bounds.width,
                        "height": element.bounds.height,
                    },
                    "action_point": {"x": action_point[0], "y": action_point[1]},
                    "task_owned_foreground": True,
                    "visual_reason": (
                        f"Canonical {selector_id.value} template element measured "
                        f"on the current frame."
                    ),
                    "intended_effect": intended_effect.value,
                    "measurement_source": "canonical_selector",
                    "selector_id": selector_id.value,
                    "selector_confidence": element.confidence,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        proof = self._parse_response(
            request, observation, foreground_target=foreground_target
        )
        if proof is None:
            raise SelectorResolutionError(
                "Generated selector response failed frame binding.",
                selector_id=selector_id,
            )
        return proof

    @staticmethod
    def _parse_response(
        request: AnnotationRequest,
        observation: Observation,
        *,
        foreground_target: HomeCityObjectId,
    ) -> MeasuredControlProof | None:
        """Binds the tester's attestation to the request's exact frame.

        Every provenance field must echo the request — request id, case,
        control, target, artifact path and hash, and the full frame identity —
        so a response written for a different frame, control, or request is
        rejected instead of silently authorizing this input.
        """

        try:
            payload = json.loads(request.response_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("request_id") != request.request_id:
            return None
        if payload.get("case_id") != request.case_id:
            return None
        if payload.get("control_name") != request.control_name:
            return None
        if payload.get("foreground_target") != request.foreground_target:
            return None
        if payload.get("artifact_sha256") != request.artifact_sha256:
            return None
        artifact_path = payload.get("artifact_path")
        if not isinstance(artifact_path, str):
            return None
        try:
            if Path(artifact_path).resolve() != request.artifact_path.resolve():
                return None
        except OSError:
            return None
        frame = payload.get("frame")
        if not isinstance(frame, dict):
            return None
        required = frame_ref_dict(observation.frame_ref)
        if any(frame.get(key) != required[key] for key in required):
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
