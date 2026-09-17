"""Canonical typed action-kind sets shared by authority, specs, and journals.

One feature scope (``FeatureActionKind``) authorizes a bounded workflow such as
one building action or one ``pet_workshop.run`` invocation. A journaled
operation carries one typed sub-action (``JournaledActionKind``) — a building
mutation kind or a Workshop intent kind — never the feature scope itself and
never an arbitrary string.
"""

from __future__ import annotations

from pnc_automation.app.pnc.domain.building_operations import BuildingMutationKind
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopIntentKind,
    WorkshopMutationKind,
)

FeatureActionKind = BuildingMutationKind | WorkshopMutationKind
JournaledActionKind = BuildingMutationKind | WorkshopIntentKind

WORKSHOP_MUTATION_INTENT_KINDS = frozenset(
    {
        WorkshopIntentKind.PRODUCE,
        WorkshopIntentKind.MERGE,
        WorkshopIntentKind.ACTIVATE,
        WorkshopIntentKind.FEED,
        WorkshopIntentKind.RECYCLE,
        WorkshopIntentKind.SUBMIT_ORDER,
    }
)
"""The Workshop sub-actions a journaled mutation operation may carry.

``select``, ``inspect``, ``wait`` and ``stop`` never mutate game resources and
must not be journaled as mutation intents; the scope covers only this set.
"""

_FEATURE_ACTION_KIND_TYPES = (BuildingMutationKind, WorkshopMutationKind)
_JOURNALED_ACTION_KIND_TYPES = (BuildingMutationKind, WorkshopIntentKind)


def normalize_feature_action_kind(value: str) -> FeatureActionKind:
    """Parse one exact feature action kind, rejecting unknown feature strings."""

    for kind_type in _FEATURE_ACTION_KIND_TYPES:
        try:
            return kind_type(value)
        except ValueError:
            continue
    raise ValueError(f"Unknown feature action kind '{value}'.")


def normalize_journaled_action_kind(value: str) -> JournaledActionKind:
    """Parse one typed journaled sub-action kind, rejecting unknown values."""

    for kind_type in _JOURNALED_ACTION_KIND_TYPES:
        try:
            return kind_type(value)
        except ValueError:
            continue
    raise ValueError(f"Unknown journaled action kind '{value}'.")


def is_workshop_journaled_action(value: str | None) -> bool:
    """Return whether a stored intent action kind is a Workshop sub-action."""

    if value is None:
        return False
    try:
        WorkshopIntentKind(value)
    except ValueError:
        return False
    return True
