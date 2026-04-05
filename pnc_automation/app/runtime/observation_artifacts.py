"""Shared runtime artifact-selection policy for observation flows."""

from __future__ import annotations

from collections.abc import Collection
from enum import StrEnum

from pnc_automation.app.runtime.observation_mode import ObservationMode


class ObservationArtifactKind(StrEnum):
    """Identifies one optional debug artifact kind that an observation flow can persist."""

    SCREENSHOT = "screenshot"
    WORLD_MAP_SURVEY_STATE = "world_map_survey_state"


type ObservationArtifactSelection = frozenset[ObservationArtifactKind]


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

    if override_selection is not None:
        return frozenset(override_selection)
    if request_selection is not None:
        return frozenset(request_selection)
    return mode_default_artifact_selection(mode)

