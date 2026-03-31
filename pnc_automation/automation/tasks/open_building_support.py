"""Shared helpers for opening one requested home-city object screen."""

from __future__ import annotations

from pnc_automation.pnc.action_requests import ActionRequest
from pnc_automation.pnc.building_catalog import (
    HomeCityObjectId,
    build_menu_option_selector_for_home_city_object,
    build_menu_screen_type_for_home_city_object,
    home_city_object_id_for_screen,
    primary_screen_type_for_home_city_object,
)
from pnc_automation.pnc.observation import (
    DetectedSpatialObject,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId


def home_city_object_query(home_city_object_id: HomeCityObjectId) -> SpatialObjectQuery:
    """Builds the canonical home-city spatial query for one exact object id."""

    return SpatialObjectQuery(
        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
        kind=SpatialObjectKind.HOME_BUILDING,
        metadata_key="home_city_object_id",
        metadata_value=home_city_object_id.value,
    )


def home_city_object_id_from_object(object_: DetectedSpatialObject) -> HomeCityObjectId | None:
    """Returns the exact home-city object id modeled for one visible spatial object."""

    metadata = getattr(object_, "metadata", {})
    object_id = metadata.get("home_city_object_id")
    if not isinstance(object_id, str):
        return None
    try:
        return HomeCityObjectId(object_id)
    except ValueError:
        return None


def find_visible_target_home_city_object(
    observation: Observation,
    *,
    target: HomeCityObjectId,
) -> DetectedSpatialObject | None:
    """Returns one visible home-city object candidate whose exact id matches the requested target."""

    return next(
        (
            object_
            for object_ in observation.spatial_objects(SpatialObjectKind.HOME_BUILDING)
            if home_city_object_id_from_object(object_) == target
        ),
        None,
    )


def requested_home_city_object_observation_matches(observation: Observation, target: HomeCityObjectId) -> bool:
    """Returns whether the observation proves the requested building or unbuilt build slot is open."""

    screen_type = observation.screen_type
    if home_city_object_id_for_screen(screen_type) == target:
        return True
    if screen_type == ScreenType.PNC_BUILDING_DETAILS and primary_screen_type_for_home_city_object(target) is None:
        return True
    build_menu_screen_type = build_menu_screen_type_for_home_city_object(target)
    build_menu_option_selector = build_menu_option_selector_for_home_city_object(target)
    if (
        build_menu_screen_type is not None
        and build_menu_option_selector is not None
        and screen_type == build_menu_screen_type
        and observation.has(build_menu_option_selector)
    ):
        return True
    if target != HomeCityObjectId.SANCTUM:
        return False
    return observation.has(UiElementId.PNC_SANCTUM_ARTIFACT_BUTTON) and observation.has(UiElementId.PNC_SANCTUM_RELIC_BUTTON)


def plan_focus_requested_home_city_object(
    *,
    flows: ScreenFlowPlanner,
    observation: Observation,
    target: HomeCityObjectId,
    runtime_state: dict[str, object],
    reason: str,
    observe_after: bool = True,
) -> list[ActionRequest]:
    """Plans one canonical search or guided direct-opening increment for the requested home-city object."""

    return flows.open_home_city_object(
        observation,
        home_city_object_query(target),
        reason=reason,
        runtime_state=runtime_state,
        observe_after=observe_after,
    )
