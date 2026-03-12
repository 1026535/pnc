"""Canonical selector interaction helpers shared by automation and validation."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.observation import Observation, VisibleElement, VisibleElementSourceKind
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_request import ObservationRequest
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.vision.selectors import ClickOutcome, SelectorDefinition

_TRANSITIONAL_SCREEN_TYPES = frozenset({ScreenType.UNKNOWN, ScreenType.PNC_LOADING})


def safe_navigation_outcomes(selector: SelectorDefinition) -> tuple[ClickOutcome, ...]:
    """Returns the reviewed navigation outcomes that are safe for runtime clicks."""

    if selector.interaction_kind != SelectorInteractionKind.NAVIGATION:
        return ()
    return tuple(
        outcome
        for outcome in selector.click_outcomes
        if outcome.safe_to_click and not outcome.monetized
    )


def match_reviewed_navigation_outcome(
    observation: Observation,
    reviewed_outcomes: Sequence[ClickOutcome],
) -> tuple[ClickOutcome | None, tuple[UiElementId, ...]]:
    """Returns the reviewed navigation outcome that matches the observed destination, if any."""

    closest_missing_selectors: tuple[UiElementId, ...] = ()
    for outcome in reviewed_outcomes:
        _require_supported_reviewed_outcome(outcome)
        if outcome.target_screen is not None and observation.screen_type != outcome.target_screen:
            continue
        missing_selectors = tuple(
            selector_id
            for selector_id in outcome.verification_selectors
            if not observation.has(selector_id)
        )
        if not missing_selectors:
            return outcome, ()
        if not closest_missing_selectors or len(missing_selectors) < len(closest_missing_selectors):
            closest_missing_selectors = missing_selectors
    return None, closest_missing_selectors


def settle_reviewed_navigation_observation(
    *,
    first_observation: Observation,
    reviewed_outcomes: Sequence[ClickOutcome],
    label_prefix: str,
    request: ObservationRequest | None,
    max_settle_observations: int,
    observe: Callable[[str, ObservationRequest | None], Observation],
    sleep: Callable[[], None] | None = None,
) -> Observation:
    """Passively re-observes one reviewed navigation destination until it settles."""

    if max_settle_observations < 0:
        raise ValueError("settle_reviewed_navigation_observation max_settle_observations cannot be negative.")
    latest_observation = first_observation
    for settle_index in range(max_settle_observations):
        matched_outcome, _ = match_reviewed_navigation_outcome(latest_observation, reviewed_outcomes)
        if matched_outcome is not None or is_popup_observation(latest_observation):
            return latest_observation
        if not is_transitional_observation(latest_observation):
            return latest_observation
        if sleep is not None:
            sleep()
        latest_observation = observe(
            f"{label_prefix}_settle_{settle_index + 1}",
            request,
        )
    return latest_observation


def is_popup_observation(observation: Observation) -> bool:
    """Returns whether the observation represents a blocking popup state."""

    return observation.blocking_popup or observation.screen_type == ScreenType.PNC_POPUP


def is_transitional_observation(observation: Observation) -> bool:
    """Returns whether the observation is still in a transient loading or unknown state."""

    return observation.screen_type in _TRANSITIONAL_SCREEN_TYPES


def is_settled_primary_navigation_miss(
    selector: SelectorDefinition,
    before: Observation,
    after: Observation,
    source_element: VisibleElement,
) -> bool:
    """Returns whether one primary geometry-backed navigation tap settled into a same-screen miss."""

    if source_element.source_kind != VisibleElementSourceKind.GEOMETRY:
        return False
    reviewed_outcomes = safe_navigation_outcomes(selector)
    if selector.interaction_kind == SelectorInteractionKind.NAVIGATION and not reviewed_outcomes:
        raise SelectorResolutionError(
            "Geometry-backed navigation fallback requires at least one safe reviewed click outcome.",
            selector_id=selector.id,
            screen_type=before.screen_type,
        )
    if not reviewed_outcomes:
        return False
    matched_outcome, _ = match_reviewed_navigation_outcome(after, reviewed_outcomes)
    if matched_outcome is not None:
        return False
    if is_popup_observation(after) or is_transitional_observation(after):
        return False
    return after.screen_type == before.screen_type


def _require_supported_reviewed_outcome(outcome: ClickOutcome) -> None:
    """Rejects reviewed navigation contracts that runtime matching cannot yet verify."""

    if not outcome.verification_texts:
        return
    raise SelectorResolutionError(
        "Reviewed navigation verification_texts are not supported at runtime.",
        target_screen=None if outcome.target_screen is None else outcome.target_screen.name,
        verification_texts=outcome.verification_texts,
    )
