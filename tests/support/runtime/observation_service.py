"""Synthetic fixtures owned by runtime.observation_service."""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import replace
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactRecord
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.observation_builder import CapturedObservation
from pnc_automation.app.pnc.domain.observation_policy import (
    ObservationArtifactKind,
    ObservationArtifactSelection,
    resolve_observation_artifact_selection,
)
from pnc_automation.core.vision.observation_policy import ObservationMode

from tests.support.core.images import build_png_bytes


@dataclass
class FakeObservationService:
    """Returns a pre-seeded sequence of observations."""

    observations: list[Observation]
    mode: ObservationMode = ObservationMode.DEBUG
    labels: list[str] = field(default_factory=list)
    requests: list[ObservationRequest | None] = field(default_factory=list)
    artifact_selections: list[ObservationArtifactSelection | None] = field(default_factory=list)
    captures: list[CapturedObservation] = field(default_factory=list)

    def observe(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> Observation:
        """Returns the next queued observation."""

        self.labels.append(label)
        self.requests.append(request)
        self.artifact_selections.append(artifact_selection)
        if not self.observations:
            raise AssertionError(f"No observation queued for label '{label}'.")
        return self.observations.pop(0)

    def capture_observation(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> CapturedObservation:
        """Returns the next queued observation wrapped in a synthetic captured screenshot."""

        observation = self.observe(label, request=request, artifact_selection=artifact_selection)
        resolved_artifact_selection = resolve_observation_artifact_selection(
            mode=self.mode,
            request_selection=None if request is None else request.artifact_selection,
            override_selection=artifact_selection,
        )
        artifact = (
            ArtifactRecord(
                path=observation.artifact_path or Path(f"{label}.png"),
                label=label,
                captured_at=observation.captured_at,
                size_bytes=0,
                sha256="0" * 64,
            )
            if ObservationArtifactKind.SCREENSHOT in resolved_artifact_selection
            else None
        )
        if artifact is not None and observation.artifact_path is None:
            observation = replace(observation, artifact_path=artifact.path)
        capture = CapturedObservation(
            screenshot=CapturedScreenshot(
                artifact=artifact,
                image=Image.new("RGB", observation.image_size or (10, 10), (0, 0, 0)),
                image_format="PNG",
                payload=build_png_bytes(size=observation.image_size or (10, 10)),
                ephemeral_captured_at=None if artifact is not None else observation.captured_at,
            ),
            observation=observation,
        )
        self.captures.append(capture)
        return capture
