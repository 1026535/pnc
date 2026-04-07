"""Shared runtime artifact-selection policy for observation flows."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.runtime.observation_mode import ObservationMode


class ObservationArtifactKind(StrEnum):
    """Identifies one optional debug artifact kind that an observation flow can persist."""

    SCREENSHOT = "screenshot"
    WORLD_MAP_SURVEY_STATE = "world_map_survey_state"


class ObservationArtifactOwner(StrEnum):
    """Identifies one runtime owner that can persist a subset of artifact kinds."""

    OBSERVATION_SERVICE = "observation_service"
    WORLD_MAP_SURVEY = "world_map_survey"


type ObservationArtifactSelection = frozenset[ObservationArtifactKind]


@dataclass(frozen=True, slots=True)
class ResolvedObservationArtifactPolicy:
    """Carries one resolved artifact selection plus canonical owner-specific projections."""

    selection: ObservationArtifactSelection

    def for_owner(self, owner: ObservationArtifactOwner) -> ObservationArtifactSelection:
        """Returns only the artifact kinds owned by the requested runtime boundary."""

        return frozenset(kind for kind in self.selection if kind in _OWNER_ARTIFACT_KINDS[owner])

    def unsupported_for_owner(self, owner: ObservationArtifactOwner) -> ObservationArtifactSelection:
        """Returns the artifact kinds the requested runtime owner cannot satisfy."""

        return frozenset(kind for kind in self.selection if kind not in _OWNER_ARTIFACT_KINDS[owner])


def observation_artifact_selection(
    *artifact_kinds: ObservationArtifactKind,
) -> ObservationArtifactSelection:
    """Builds one immutable artifact-selection value from the requested artifact kinds."""

    return frozenset(artifact_kinds)


def mode_default_artifact_selection(mode: ObservationMode) -> ObservationArtifactSelection:
    """Returns the canonical routine artifact selection implied by one runtime mode."""

    if mode == ObservationMode.DEBUG:
        return observation_artifact_selection(ObservationArtifactKind.SCREENSHOT)
    if mode == ObservationMode.LIGHT:
        return frozenset()
    raise ValueError(f"Unsupported observation mode '{mode}'.")


def resolve_observation_artifact_selection(
    *,
    mode: ObservationMode,
    request_selection: Collection[ObservationArtifactKind] | None = None,
    override_selection: Collection[ObservationArtifactKind] | None = None,
) -> ObservationArtifactSelection:
    """Resolves one effective artifact selection from call-site override, request override, and mode defaults."""

    return resolve_observation_artifact_policy(
        mode=mode,
        request_selection=request_selection,
        override_selection=override_selection,
    ).selection


def resolve_observation_artifact_policy(
    *,
    mode: ObservationMode,
    request_selection: Collection[ObservationArtifactKind] | None = None,
    override_selection: Collection[ObservationArtifactKind] | None = None,
) -> ResolvedObservationArtifactPolicy:
    """Resolves one effective artifact policy from call-site override, request override, and mode defaults."""

    if override_selection is not None:
        return ResolvedObservationArtifactPolicy(selection=frozenset(override_selection))
    if request_selection is not None:
        return ResolvedObservationArtifactPolicy(selection=frozenset(request_selection))
    return ResolvedObservationArtifactPolicy(selection=mode_default_artifact_selection(mode))


_OWNER_ARTIFACT_KINDS: dict[ObservationArtifactOwner, frozenset[ObservationArtifactKind]] = {
    ObservationArtifactOwner.OBSERVATION_SERVICE: observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
    ObservationArtifactOwner.WORLD_MAP_SURVEY: observation_artifact_selection(
        ObservationArtifactKind.WORLD_MAP_SURVEY_STATE
    ),
}
