"""Checkpoint-oriented owner for repeated world-map survey observations and debug dumps."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pnc_automation.app.pnc.domain.observation import SpatialSurfaceObservation, SpatialSurfaceType
from pnc_automation.app.pnc.navigation.world_map_index import (
    WorldMapObjectKey,
    WorldMapObjectSighting,
    WorldMapSurveyIndex,
)
from pnc_automation.app.pnc.persistence.world_map_survey_debug_store import (
    StoredWorldMapSurveyDebugDump,
    WorldMapSurveyDebugStore,
)
from pnc_automation.app.pnc.vision.observation_builder import CapturedObservation, ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.runtime.observation_artifacts import (
    ObservationArtifactKind,
    ObservationArtifactOwner,
    ObservationArtifactSelection,
    ResolvedObservationArtifactPolicy,
    resolve_observation_artifact_policy,
)
from pnc_automation.core.errors import SelectorResolutionError


@dataclass(frozen=True, slots=True)
class WorldMapSurveyCheckpointResult:
    """Summarizes one survey checkpoint capture and optional persisted debug dump."""

    capture: CapturedObservation
    updated_sightings: tuple[WorldMapObjectSighting, ...]
    artifact_selection: ObservationArtifactSelection
    debug_dump: StoredWorldMapSurveyDebugDump | None


@dataclass(frozen=True, slots=True)
class _LatestWorldMapCheckpointContext:
    """Carries the latest ingested world-map checkpoint metadata needed for later debug dumps."""

    captured_at: datetime
    artifact_path: Path | None
    surface: SpatialSurfaceObservation


@dataclass(slots=True)
class WorldMapSurveyRecorder:
    """Owns survey-local world-map observation ingestion and optional checkpoint debug persistence."""

    observation_service: ObservationService
    debug_store: WorldMapSurveyDebugStore
    index: WorldMapSurveyIndex = field(default_factory=WorldMapSurveyIndex)
    _latest_checkpoint_context: _LatestWorldMapCheckpointContext | None = field(default=None, init=False, repr=False)

    def capture_checkpoint(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> WorldMapSurveyCheckpointResult:
        """Captures one world-map observation, ingests it into the canonical index, and persists one debug dump when requested."""

        artifact_policy = self._resolve_artifact_policy(
            request=request,
            artifact_selection=artifact_selection,
        )
        capture = self.observation_service.capture_observation(
            label,
            request=request,
            artifact_selection=artifact_policy.for_owner(ObservationArtifactOwner.OBSERVATION_SERVICE),
        )
        updated_sightings = self.ingest_capture(capture)
        return WorldMapSurveyCheckpointResult(
            capture=capture,
            updated_sightings=updated_sightings,
            artifact_selection=artifact_policy.selection,
            debug_dump=self._persist_checkpoint(
                label,
                artifact_policy=artifact_policy,
            ),
        )

    def ingest_capture(self, capture: CapturedObservation) -> tuple[WorldMapObjectSighting, ...]:
        """Indexes one already-captured world-map observation and remembers its checkpoint context for later dumps."""

        surface = capture.observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP)
        self._latest_checkpoint_context = _LatestWorldMapCheckpointContext(
            captured_at=capture.observation.captured_at,
            artifact_path=capture.observation.artifact_path,
            surface=surface,
        )
        return self.index.ingest_observation(capture.observation)

    def persist_checkpoint(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> StoredWorldMapSurveyDebugDump | None:
        """Persists one debug dump for the latest ingested checkpoint when the artifact selection enables it."""

        return self._persist_checkpoint(
            label,
            artifact_policy=self._resolve_artifact_policy(
                request=request,
                artifact_selection=artifact_selection,
            ),
        )

    def _persist_checkpoint(
        self,
        label: str,
        *,
        artifact_policy: ResolvedObservationArtifactPolicy,
    ) -> StoredWorldMapSurveyDebugDump | None:
        """Persists one debug dump for the latest ingested checkpoint using one already-resolved artifact policy."""

        survey_artifacts = artifact_policy.for_owner(ObservationArtifactOwner.WORLD_MAP_SURVEY)
        if ObservationArtifactKind.WORLD_MAP_SURVEY_STATE not in survey_artifacts:
            return None
        if self._latest_checkpoint_context is None:
            raise SelectorResolutionError(
                "World-map survey-state dumping requires an ingested world-map checkpoint before persistence.",
                artifact_kind=ObservationArtifactKind.WORLD_MAP_SURVEY_STATE.value,
            )
        return self.debug_store.persist(
            self.index.snapshot(
                artifact_directory=self.observation_service.artifact_directory,
                label=label,
                captured_at=self._latest_checkpoint_context.captured_at,
                artifact_path=self._latest_checkpoint_context.artifact_path,
                surface=self._latest_checkpoint_context.surface,
            )
        )

    def _resolve_artifact_policy(
        self,
        *,
        request: ObservationRequest | None,
        artifact_selection: ObservationArtifactSelection | None,
    ) -> ResolvedObservationArtifactPolicy:
        """Resolves the effective artifact policy for one world-map survey checkpoint flow."""

        return resolve_observation_artifact_policy(
            mode=self.observation_service.mode,
            request_selection=None if request is None else request.artifact_selection,
            override_selection=artifact_selection,
        )

    def annotate_castle_player_name(
        self,
        key: WorldMapObjectKey,
        *,
        player_name: str,
        profile_artifact_path: Path | None = None,
    ) -> WorldMapObjectSighting:
        """Attaches resolved player-profile evidence to one indexed castle sighting."""

        return self.index.annotate_castle_player_name(
            key,
            player_name=player_name,
            profile_artifact_path=profile_artifact_path,
        )
