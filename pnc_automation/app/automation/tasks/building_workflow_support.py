"""Shared observation predicates for building construction and upgrade workflows."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.text.normalization import normalize_ocr_text


def home_city_active_build_timer_text(observation: Observation) -> str | None:
    """Returns the visible home-city construction timer when one was observed."""

    surface = observation.spatial_surface
    if surface is None:
        return None
    timer_text = surface.metadata.get("active_build_timer_text")
    if not isinstance(timer_text, str):
        return None
    stripped = timer_text.strip()
    return None if stripped == "" else stripped


def home_city_active_build_is_visible(observation: Observation) -> bool:
    """Returns whether the home-city surface proves one active construction timer."""

    return home_city_active_build_timer_text(observation) is not None


def home_build_help_is_available(observation: Observation) -> bool:
    """Returns whether the home build control currently offers alliance help."""

    build_action = observation.get(UiElementId.PNC_HOME_BUILD_BUTTON)
    if build_action is None or build_action.extracted_text is None:
        return False
    return normalize_ocr_text(build_action.extracted_text) == "HELP"


def can_open_build_queue(observation: Observation) -> bool:
    """Returns whether the home build control can safely open the build queue."""

    build_action = observation.get(UiElementId.PNC_HOME_BUILD_BUTTON)
    if build_action is None:
        return False
    if build_action.extracted_text is None:
        return True
    return normalize_ocr_text(build_action.extracted_text) != "HELP"


def build_queue_active_timer_text(observation: Observation) -> str | None:
    """Returns the first active construction timer exposed by the build queue."""

    for entry in observation.entries(ListEntryKind.BUILDING):
        if entry.metadata.get("queue_state") != "upgrading":
            continue
        if entry.timer_text is not None and entry.timer_text.strip() != "":
            return entry.timer_text.strip()
    return None


def building_requirement_is_visible(observation: Observation) -> bool:
    """Returns whether an insufficient-resource or prerequisite panel is visible."""

    return observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_HEADER)


def building_requirement_text(observation: Observation) -> str | None:
    """Returns the visible unmet requirement label when available."""

    requirement = observation.get(UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL)
    if requirement is None or requirement.extracted_text is None:
        return None
    text = requirement.extracted_text.strip()
    return None if text == "" else text
