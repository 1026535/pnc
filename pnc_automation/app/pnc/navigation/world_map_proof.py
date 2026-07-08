"""Canonical proof contracts for exact and root world-map viewport state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pnc_automation.app.pnc.domain.observation import Observation, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import CapturedObservation
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.runtime.observation_artifacts import ObservationArtifactSelection
from pnc_automation.core.errors import SelectorResolutionError


class WorldMapProofStrength(StrEnum):
    """Describes how strongly one observation proves world-map ownership and coordinates."""

    EXACT = "exact"
    ROOT = "root"


class WorldMapProofObservationService(Protocol):
    """Defines the narrow observation-service dependency needed by P1 proof refresh."""

    def observe(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> Observation:
        """Captures or reuses one typed observation for a proof attempt."""

    def capture_observation(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> CapturedObservation:
        """Captures one screenshot and its narrow P1 observation for screenshot reuse."""


@dataclass(frozen=True, slots=True)
class WorldMapViewportProof:
    """Carries only the immutable movement facts P1 proved for one screenshot."""

    strength: WorldMapProofStrength
    coordinate: tuple[int, int] | None
    artifact_path: Path | None
    captured_at: datetime

    def __post_init__(self) -> None:
        """Rejects impossible proof payloads so downstream analysis can trust P1 facts."""

        if self.strength == WorldMapProofStrength.EXACT:
            if self.coordinate is None:
                raise SelectorResolutionError("Exact world-map proof requires one viewport coordinate.")
            return
        if self.strength == WorldMapProofStrength.ROOT:
            if self.coordinate is not None:
                raise SelectorResolutionError("Root world-map proof must not pretend to know an exact coordinate.")
            return
        raise SelectorResolutionError("Unsupported world-map proof strength.", strength=self.strength)

    @classmethod
    def from_observation(cls, observation: Observation) -> "WorldMapViewportProof":
        """Builds the strongest valid world-map proof available from one observation."""

        if observation.spatial_surface is not None and observation.spatial_surface.surface_type == SpatialSurfaceType.WORLD_MAP:
            coordinate = observation.spatial_surface.viewport.coordinate
            if coordinate is None:
                raise SelectorResolutionError(
                    "Exact world-map proof requires a coordinate-addressable spatial viewport.",
                    screen_type=observation.screen_type,
                )
            return cls(
                strength=WorldMapProofStrength.EXACT,
                coordinate=coordinate,
                artifact_path=observation.artifact_path,
                captured_at=observation.captured_at,
            )
        if observation.screen_type == ScreenType.PNC_WORLD_MAP_ROOT:
            return cls(
                strength=WorldMapProofStrength.ROOT,
                coordinate=None,
                artifact_path=observation.artifact_path,
                captured_at=observation.captured_at,
            )
        raise SelectorResolutionError(
            "Observation does not prove a world-map viewport.",
            screen_type=observation.screen_type,
        )

    @classmethod
    def from_capture(cls, capture: CapturedObservation) -> "WorldMapViewportProof":
        """Builds P1 proof from a captured screenshot while retaining no rich observation payload."""

        proof = cls.from_observation(capture.observation)
        if capture.screenshot.captured_at != proof.captured_at:
            raise SelectorResolutionError(
                "P1 screenshot and movement observation must share one capture timestamp.",
                screenshot_captured_at=capture.screenshot.captured_at.isoformat(),
                observation_captured_at=proof.captured_at.isoformat(),
            )
        if capture.screenshot.artifact_path != proof.artifact_path:
            raise SelectorResolutionError(
                "P1 screenshot and movement observation must share one artifact identity.",
                screenshot_artifact_path=capture.screenshot.artifact_path,
                observation_artifact_path=proof.artifact_path,
            )
        return proof


@dataclass(frozen=True, slots=True)
class WorldMapMovementProofPolicy:
    """Controls bounded P1 proof refresh without promoting to full rich runtime OCR."""

    refresh_budget: int = 2
    request_factory: Callable[[], ObservationRequest] = ObservationRequest.world_map_movement_proof_follow_up
    capture_sink: Callable[[CapturedObservation], None] | None = None
    artifact_selection: ObservationArtifactSelection | None = None

    def __post_init__(self) -> None:
        """Rejects invalid retry budgets before movement proof consumes them."""

        if self.refresh_budget < 0:
            raise SelectorResolutionError(
                "World-map movement proof refresh budgets must be non-negative.",
                refresh_budget=self.refresh_budget,
            )


def prove_world_map_viewport(
    *,
    observation_service: WorldMapProofObservationService | None,
    observation: Observation,
    label_prefix: str,
    policy: WorldMapMovementProofPolicy | None = None,
) -> WorldMapViewportProof:
    """Returns one exact/root world-map proof using only the bounded P1 refresh policy."""

    _observation, proof = _resolve_world_map_viewport(
        observation_service=observation_service,
        observation=observation,
        label_prefix=label_prefix,
        policy=policy,
    )
    return proof


def require_exact_world_map_observation(
    *,
    observation_service: WorldMapProofObservationService | None,
    observation: Observation,
    label_prefix: str,
    policy: WorldMapMovementProofPolicy | None = None,
) -> Observation:
    """Returns the current observation after the canonical P1 loop proves an exact viewport."""

    proven_observation, proof = _resolve_world_map_viewport(
        observation_service=observation_service,
        observation=observation,
        label_prefix=label_prefix,
        policy=policy,
    )
    _require_exact_proof_strength(proof)
    return proven_observation


def _resolve_world_map_viewport(
    *,
    observation_service: WorldMapProofObservationService | None,
    observation: Observation,
    label_prefix: str,
    policy: WorldMapMovementProofPolicy | None,
) -> tuple[Observation, WorldMapViewportProof]:
    """Runs the single canonical bounded P1 loop and returns its local observation plus proof."""

    active_policy = policy or WorldMapMovementProofPolicy()
    current = observation
    for refresh_index in range(active_policy.refresh_budget + 1):
        try:
            return current, WorldMapViewportProof.from_observation(current)
        except SelectorResolutionError as error:
            if current.screen_type not in {ScreenType.PNC_WORLD_MAP, ScreenType.PNC_WORLD_MAP_ROOT, ScreenType.UNKNOWN}:
                raise SelectorResolutionError(
                    "World-map proof requires an already-world-map-compatible observation.",
                    screen_type=current.screen_type,
                ) from error
            if observation_service is None or refresh_index >= active_policy.refresh_budget:
                raise SelectorResolutionError(
                    "World-map proof requires a parsed world-map surface or root proof, but bounded P1 refresh failed.",
                    screen_type=current.screen_type,
                    refresh_budget=active_policy.refresh_budget,
                ) from error
            if active_policy.capture_sink is None:
                current = observation_service.observe(
                    f"{label_prefix}_{refresh_index}",
                    request=active_policy.request_factory(),
                    artifact_selection=active_policy.artifact_selection,
                )
            else:
                capture = observation_service.capture_observation(
                    f"{label_prefix}_{refresh_index}",
                    request=active_policy.request_factory(),
                    artifact_selection=active_policy.artifact_selection,
                )
                active_policy.capture_sink(capture)
                current = capture.observation
    raise AssertionError("Unreachable world-map proof refresh fallthrough.")


def require_exact_world_map_proof(
    *,
    observation_service: WorldMapProofObservationService | None,
    observation: Observation,
    label_prefix: str,
    policy: WorldMapMovementProofPolicy | None = None,
) -> WorldMapViewportProof:
    """Returns an exact coordinate-addressed proof or fails fast before movement/P2 analysis proceeds."""

    proof = prove_world_map_viewport(
        observation_service=observation_service,
        observation=observation,
        label_prefix=label_prefix,
        policy=policy,
    )
    _require_exact_proof_strength(proof)
    return proof


def _require_exact_proof_strength(proof: WorldMapViewportProof) -> None:
    """Fails fast unless the resolved P1 proof is coordinate-addressable."""

    if proof.strength != WorldMapProofStrength.EXACT:
        raise SelectorResolutionError(
            "Exact world-map proof is required for coordinate-addressed movement and checkpoint analysis.",
            proof_strength=proof.strength.value,
        )
