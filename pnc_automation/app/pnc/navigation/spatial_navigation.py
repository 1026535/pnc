"""Canonical spatial-surface navigation helpers shared by flows and tasks."""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import (
    ActionRequest,
    SwipeAction,
    SwipeInputSource,
    TapAction,
    TapPointAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityMapCoordinate,
    HomeCityObjectId,
    home_city_map_atlas,
    home_city_map_coordinate,
    home_city_object_id_from_metadata,
    is_home_city_object_usable_as_atlas_anchor,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedSpatialObject,
    Observation,
    SpatialObjectQuery,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

_WORLD_NAVIGATION_STATE_KEY = "world_map_navigation"
_HOME_CITY_NAVIGATION_STATE_KEY = "home_city_navigation"
_HOME_CITY_FIXED_MAP_TOUR_PASSES = 3
_HOME_CITY_ATLAS_HORIZONTAL_SWIPE_Y_RATIO = 0.56
_HOME_CITY_ATLAS_VERTICAL_SWIPE_X_RATIO = 0.55
_HOME_CITY_CASTLE_UTILITY_VERTICAL_SWIPE_X_RATIO = 0.69
_HOME_CITY_RIGHT_VIEW_VERTICAL_SWIPE_X_RATIO = 0.24
_WORLD_MAP_VERTICAL_SWIPE_X_RATIO = 0.46


@dataclass(frozen=True, slots=True)
class _HomeCityViewportEstimate:
    """Carries the best-known home-city viewport center from visible anchors or remembered planned movement."""

    center: HomeCityMapCoordinate
    evidence_count: int


@dataclass(frozen=True, slots=True)
class _HomeCityAtlasRoutePlan:
    """Carries one precomputed atlas-backed swipe series plus the viewport center it should reach."""

    actions: tuple[SwipeAction, ...]
    predicted_center: HomeCityMapCoordinate


@dataclass(frozen=True, slots=True)
class WorldCoordinate:
    """Represents one absolute world-map coordinate target."""

    x: int
    y: int

    def __post_init__(self) -> None:
        """Rejects invalid coordinate targets before they reach navigation planning."""

        if self.x < 0 or self.y < 0:
            raise SelectorResolutionError("World coordinates must be non-negative integers.", x=self.x, y=self.y)


class WorldMapCardinalDirection(StrEnum):
    """Defines the canonical four-direction world-map swipe set used by sweep traversal and calibration."""

    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class _HomeCityKnownViewTapSpec:
    """Defines one normalized direct tap calibrated for one trusted home-city view."""

    target_object_id: HomeCityObjectId
    tap_x_ratio: float
    tap_y_ratio: float
    reason: str


@dataclass(frozen=True, slots=True)
class _HomeCityKnownViewSpec:
    """Defines one trusted fixed camera framing and the direct taps valid within it."""

    required_visible_object_ids: frozenset[HomeCityObjectId]
    tap_specs: tuple[_HomeCityKnownViewTapSpec, ...]


@dataclass(frozen=True, slots=True)
class _HomeCityGuidedRouteSpec:
    """Defines one deterministic view transition toward one or more exact home-city targets."""

    target_object_ids: frozenset[HomeCityObjectId]
    required_visible_object_ids: frozenset[HomeCityObjectId]
    swipe_action: SwipeAction


_HOME_CITY_KNOWN_VIEW_SPECS = (
    _HomeCityKnownViewSpec(
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.INFANTRY_BARRACKS,
                HomeCityObjectId.RANGED_BARRACKS,
            }
        ),
        tap_specs=(
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.CASTLE,
                tap_x_ratio=441 / 900,
                tap_y_ratio=425 / 1600,
                reason="open_castle_from_root_view",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.INSTITUTE,
                tap_x_ratio=722 / 900,
                tap_y_ratio=912 / 1600,
                reason="open_institute_from_root_view",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.INFANTRY_BARRACKS,
                tap_x_ratio=110 / 900,
                tap_y_ratio=699 / 1600,
                reason="open_infantry_barracks_from_root_view",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.RANGED_BARRACKS,
                tap_x_ratio=118 / 900,
                tap_y_ratio=917 / 1600,
                reason="open_ranged_barracks_from_root_view",
            ),
        ),
    ),
    _HomeCityKnownViewSpec(
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.WATCHTOWER,
                HomeCityObjectId.SAUROI_LAIR,
                HomeCityObjectId.CAMPAIGN,
            }
        ),
        tap_specs=(
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.WATCHTOWER,
                tap_x_ratio=464 / 900,
                tap_y_ratio=528 / 1600,
                reason="open_watchtower_from_utility_view",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.WAREHOUSE,
                tap_x_ratio=395 / 900,
                tap_y_ratio=841 / 1600,
                reason="open_warehouse_from_utility_view",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.INSTITUTE,
                tap_x_ratio=198 / 900,
                tap_y_ratio=932 / 1600,
                reason="open_institute_from_utility_view",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.SAUROI_LAIR,
                tap_x_ratio=760 / 900,
                tap_y_ratio=637 / 1600,
                reason="open_sauroi_lair_from_utility_view",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.CAMPAIGN,
                tap_x_ratio=800 / 900,
                tap_y_ratio=940 / 1600,
                reason="open_campaign_from_utility_view",
            ),
        ),
    ),
    _HomeCityKnownViewSpec(
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.INSTITUTE,
                HomeCityObjectId.BLACKSMITH,
                HomeCityObjectId.WALL,
            }
        ),
        tap_specs=(
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.INSTITUTE,
                tap_x_ratio=231 / 900,
                tap_y_ratio=248 / 1600,
                reason="open_institute_from_institute_wall_quadrant",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.ALLIANCE_HALL,
                tap_x_ratio=827 / 900,
                tap_y_ratio=666 / 1600,
                reason="open_alliance_hall_from_institute_wall_quadrant",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.BLACKSMITH,
                tap_x_ratio=190 / 900,
                tap_y_ratio=924 / 1600,
                reason="open_blacksmith_from_institute_wall_quadrant",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.WALL,
                tap_x_ratio=750 / 900,
                tap_y_ratio=959 / 1600,
                reason="open_wall_from_institute_wall_quadrant",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.TRAP_WORKSHOP,
                tap_x_ratio=241 / 900,
                tap_y_ratio=1365 / 1600,
                reason="open_trap_workshop_from_institute_wall_quadrant",
            ),
        ),
    ),
    _HomeCityKnownViewSpec(
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.INSTITUTE,
                HomeCityObjectId.ALLIANCE_HALL,
                HomeCityObjectId.WALL,
            }
        ),
        tap_specs=(
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.BLACKSMITH,
                tap_x_ratio=190 / 900,
                tap_y_ratio=924 / 1600,
                reason="open_blacksmith_from_institute_wall_quadrant",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.TRAP_WORKSHOP,
                tap_x_ratio=241 / 900,
                tap_y_ratio=1365 / 1600,
                reason="open_trap_workshop_from_institute_wall_quadrant",
            ),
        ),
    ),
    _HomeCityKnownViewSpec(
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.INSTITUTE,
                HomeCityObjectId.ALLIANCE_HALL,
                HomeCityObjectId.BLACKSMITH,
            }
        ),
        tap_specs=(
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.WALL,
                tap_x_ratio=750 / 900,
                tap_y_ratio=959 / 1600,
                reason="open_wall_from_institute_wall_quadrant",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.TRAP_WORKSHOP,
                tap_x_ratio=241 / 900,
                tap_y_ratio=1365 / 1600,
                reason="open_trap_workshop_from_institute_wall_quadrant",
            ),
        ),
    ),
    _HomeCityKnownViewSpec(
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.BLACKSMITH,
                HomeCityObjectId.FARM,
            }
        ),
        tap_specs=(
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.TRAP_WORKSHOP,
                tap_x_ratio=667 / 900,
                tap_y_ratio=875 / 1600,
                reason="open_trap_workshop_from_blacksmith_lower_band",
            ),
        ),
    ),
    _HomeCityKnownViewSpec(
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.HERO_HALL,
                HomeCityObjectId.HALL_OF_WAR,
            }
        ),
        tap_specs=(
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.HERO_HALL,
                tap_x_ratio=451 / 900,
                tap_y_ratio=312 / 1600,
                reason="open_hero_hall_from_hero_war_view",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.HALL_OF_WAR,
                tap_x_ratio=446 / 900,
                tap_y_ratio=697 / 1600,
                reason="open_hall_of_war_from_hero_war_view",
            ),
        ),
    ),
    _HomeCityKnownViewSpec(
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.PIT,
                HomeCityObjectId.SACRED_TREE,
                HomeCityObjectId.RECRUITING_CENTER,
            }
        ),
        tap_specs=(
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.PIT,
                tap_x_ratio=300 / 900,
                tap_y_ratio=294 / 1600,
                reason="open_pit_from_sacred_tree_band",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.SACRED_TREE,
                tap_x_ratio=619 / 900,
                tap_y_ratio=377 / 1600,
                reason="open_sacred_tree_from_sacred_tree_band",
            ),
        ),
    ),
    _HomeCityKnownViewSpec(
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.SAUROI_LAIR,
                HomeCityObjectId.ARENA,
            }
        ),
        tap_specs=(
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.SAUROI_LAIR,
                tap_x_ratio=275 / 900,
                tap_y_ratio=861 / 1600,
                reason="open_sauroi_lair_from_sauroi_arena_view",
            ),
            _HomeCityKnownViewTapSpec(
                target_object_id=HomeCityObjectId.ARENA,
                tap_x_ratio=585 / 900,
                tap_y_ratio=982 / 1600,
                reason="open_arena_from_sauroi_arena_view",
            ),
        ),
    ),
)


_HOME_CITY_GUIDED_ROUTE_SPECS = (
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset({HomeCityObjectId.WALL}),
        required_visible_object_ids=frozenset({HomeCityObjectId.BLACKSMITH}),
        swipe_action=SwipeAction(
            direction="left",
            distance_ratio=0.28,
            duration_ms=300,
            reason="guide_wall_search_from_blacksmith",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.72,
            start_y_ratio=0.52,
            end_x_ratio=0.48,
            end_y_ratio=0.52,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset({HomeCityObjectId.TRAP_WORKSHOP}),
        required_visible_object_ids=frozenset({HomeCityObjectId.BLACKSMITH}),
        swipe_action=SwipeAction(
            direction="up",
            distance_ratio=0.24,
            duration_ms=300,
            reason="guide_trap_workshop_lower_band_from_blacksmith",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.72,
            start_y_ratio=0.62,
            end_x_ratio=0.72,
            end_y_ratio=0.38,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset({HomeCityObjectId.WALL}),
        required_visible_object_ids=frozenset({HomeCityObjectId.CASTLE}),
        swipe_action=SwipeAction(
            direction="up",
            distance_ratio=0.28,
            duration_ms=300,
            reason="guide_wall_search_from_castle",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.52,
            start_y_ratio=0.68,
            end_x_ratio=0.52,
            end_y_ratio=0.42,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset({HomeCityObjectId.WAREHOUSE}),
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.HALL_OF_WAR,
                HomeCityObjectId.HERO_HALL,
            }
        ),
        swipe_action=SwipeAction(
            direction="left",
            distance_ratio=0.32,
            duration_ms=320,
            reason="guide_warehouse_search_from_hall_of_war_and_hero_hall",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.70,
            start_y_ratio=0.52,
            end_x_ratio=0.40,
            end_y_ratio=0.52,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset({HomeCityObjectId.WAREHOUSE}),
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.HALL_OF_WAR,
                HomeCityObjectId.SACRED_TREE,
                HomeCityObjectId.RECRUITING_CENTER,
            }
        ),
        swipe_action=SwipeAction(
            direction="down",
            distance_ratio=0.36,
            duration_ms=320,
            reason="guide_warehouse_search_from_hall_of_war_and_recruiting_center_band",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.54,
            start_y_ratio=0.38,
            end_x_ratio=0.54,
            end_y_ratio=0.72,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset(
            {
                HomeCityObjectId.WATCHTOWER,
                HomeCityObjectId.WAREHOUSE,
                HomeCityObjectId.SAUROI_LAIR,
                HomeCityObjectId.CAMPAIGN,
                HomeCityObjectId.ARENA,
                HomeCityObjectId.ALLIANCE_HALL,
                HomeCityObjectId.BLACKSMITH,
                HomeCityObjectId.TRAP_WORKSHOP,
            }
        ),
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.INFANTRY_BARRACKS,
                HomeCityObjectId.RANGED_BARRACKS,
            }
        ),
        swipe_action=SwipeAction(
            direction="left",
            distance_ratio=0.56,
            duration_ms=320,
            reason="guide_utility_view_from_root_view",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.76,
            start_y_ratio=0.52,
            end_x_ratio=0.28,
            end_y_ratio=0.52,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset(
            {
                HomeCityObjectId.CASTLE,
                HomeCityObjectId.INFANTRY_BARRACKS,
                HomeCityObjectId.RANGED_BARRACKS,
            }
        ),
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.WATCHTOWER,
                HomeCityObjectId.SAUROI_LAIR,
                HomeCityObjectId.CAMPAIGN,
            }
        ),
        swipe_action=SwipeAction(
            direction="right",
            distance_ratio=0.56,
            duration_ms=320,
            reason="guide_root_view_from_utility_view",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.28,
            start_y_ratio=0.52,
            end_x_ratio=0.76,
            end_y_ratio=0.52,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset(
            {
                HomeCityObjectId.ALLIANCE_HALL,
                HomeCityObjectId.BLACKSMITH,
                HomeCityObjectId.WALL,
                HomeCityObjectId.TRAP_WORKSHOP,
            }
        ),
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.WATCHTOWER,
                HomeCityObjectId.SAUROI_LAIR,
                HomeCityObjectId.CAMPAIGN,
            }
        ),
        swipe_action=SwipeAction(
            direction="up",
            distance_ratio=0.42,
            duration_ms=320,
            reason="guide_institute_wall_quadrant_from_utility_view",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.54,
            start_y_ratio=0.70,
            end_x_ratio=0.54,
            end_y_ratio=0.34,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset({HomeCityObjectId.ARENA}),
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.WATCHTOWER,
                HomeCityObjectId.SAUROI_LAIR,
                HomeCityObjectId.CAMPAIGN,
            }
        ),
        swipe_action=SwipeAction(
            direction="left",
            distance_ratio=0.34,
            duration_ms=320,
            reason="guide_sauroi_arena_view_from_utility_view",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.78,
            start_y_ratio=0.54,
            end_x_ratio=0.42,
            end_y_ratio=0.54,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset(
            {
                HomeCityObjectId.HERO_HALL,
                HomeCityObjectId.HALL_OF_WAR,
                HomeCityObjectId.PIT,
                HomeCityObjectId.SACRED_TREE,
            }
        ),
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.INFANTRY_BARRACKS,
                HomeCityObjectId.RANGED_BARRACKS,
            }
        ),
        swipe_action=SwipeAction(
            direction="up",
            distance_ratio=0.44,
            duration_ms=320,
            reason="guide_hero_war_view_from_root_view",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.54,
            start_y_ratio=0.72,
            end_x_ratio=0.54,
            end_y_ratio=0.34,
        ),
    ),
    _HomeCityGuidedRouteSpec(
        target_object_ids=frozenset(
            {
                HomeCityObjectId.PIT,
                HomeCityObjectId.SACRED_TREE,
            }
        ),
        required_visible_object_ids=frozenset(
            {
                HomeCityObjectId.HERO_HALL,
                HomeCityObjectId.HALL_OF_WAR,
            }
        ),
        swipe_action=SwipeAction(
            direction="up",
            distance_ratio=0.32,
            duration_ms=320,
            reason="guide_sacred_tree_band_from_hero_war_view",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.52,
            start_y_ratio=0.66,
            end_x_ratio=0.52,
            end_y_ratio=0.36,
        ),
    ),
)


class SpatialSurfaceNavigator(ABC):
    """Minimal shared contract implemented by concrete surface-specific navigators."""

    surface_type: SpatialSurfaceType

    def require_surface(self, observation: Observation) -> SpatialSurfaceObservation:
        """Returns the active surface or fails fast when the current observation is incompatible."""

        return observation.require_spatial_surface(self.surface_type)


@dataclass(frozen=True, slots=True)
class _WorldMapSwipeProfile:
    """Defines one calibrated world-map swipe lane plus the coordinate-signs it is expected to produce."""

    name: str
    start_x_ratio: float
    start_y_ratio: float
    end_x_ratio: float
    end_y_ratio: float
    expected_delta_x_sign: int
    expected_delta_y_sign: int
    minimum_effective_delta_x: int
    minimum_effective_delta_y: int
    default_duration_ms: int
    input_source: SwipeInputSource
    default_horizontal_distance_ratio: float
    default_vertical_distance_ratio: float

    @property
    def is_diagonal(self) -> bool:
        """Returns whether the profile is intended to move both axes at once."""

        return self.expected_delta_x_sign != 0 and self.expected_delta_y_sign != 0

    @property
    def native_horizontal_distance_ratio(self) -> float:
        """Returns the reviewed native horizontal lane span encoded by the profile endpoints."""

        return abs(self.start_x_ratio - self.end_x_ratio)

    @property
    def native_vertical_distance_ratio(self) -> float:
        """Returns the reviewed native vertical lane span encoded by the profile endpoints."""

        return abs(self.start_y_ratio - self.end_y_ratio)


_WORLD_MAP_SWIPE_PROFILES: tuple[_WorldMapSwipeProfile, ...] = (
    _WorldMapSwipeProfile(
        name="left",
        start_x_ratio=0.80,
        start_y_ratio=0.60,
        end_x_ratio=0.16,
        end_y_ratio=0.60,
        expected_delta_x_sign=1,
        expected_delta_y_sign=0,
        minimum_effective_delta_x=2,
        minimum_effective_delta_y=0,
        default_duration_ms=700,
        input_source=SwipeInputSource.TOUCHSCREEN,
        default_horizontal_distance_ratio=0.40,
        default_vertical_distance_ratio=0.0,
    ),
    _WorldMapSwipeProfile(
        name="right",
        start_x_ratio=0.16,
        start_y_ratio=0.60,
        end_x_ratio=0.80,
        end_y_ratio=0.60,
        expected_delta_x_sign=-1,
        expected_delta_y_sign=0,
        minimum_effective_delta_x=2,
        minimum_effective_delta_y=0,
        default_duration_ms=700,
        input_source=SwipeInputSource.DEFAULT,
        default_horizontal_distance_ratio=0.20,
        default_vertical_distance_ratio=0.0,
    ),
    _WorldMapSwipeProfile(
        name="up",
        start_x_ratio=_WORLD_MAP_VERTICAL_SWIPE_X_RATIO,
        start_y_ratio=0.72,
        end_x_ratio=_WORLD_MAP_VERTICAL_SWIPE_X_RATIO,
        end_y_ratio=0.28,
        expected_delta_x_sign=0,
        expected_delta_y_sign=1,
        minimum_effective_delta_x=0,
        minimum_effective_delta_y=8,
        default_duration_ms=500,
        input_source=SwipeInputSource.TOUCHSCREEN,
        default_horizontal_distance_ratio=0.0,
        default_vertical_distance_ratio=0.40,
    ),
    _WorldMapSwipeProfile(
        name="down",
        start_x_ratio=_WORLD_MAP_VERTICAL_SWIPE_X_RATIO,
        start_y_ratio=0.28,
        end_x_ratio=_WORLD_MAP_VERTICAL_SWIPE_X_RATIO,
        end_y_ratio=0.72,
        expected_delta_x_sign=0,
        expected_delta_y_sign=-1,
        minimum_effective_delta_x=0,
        minimum_effective_delta_y=8,
        default_duration_ms=500,
        input_source=SwipeInputSource.TOUCHSCREEN,
        default_horizontal_distance_ratio=0.0,
        default_vertical_distance_ratio=0.44,
    ),
    _WorldMapSwipeProfile(
        name="up_left",
        start_x_ratio=0.80,
        start_y_ratio=0.72,
        end_x_ratio=0.16,
        end_y_ratio=0.28,
        expected_delta_x_sign=1,
        expected_delta_y_sign=1,
        minimum_effective_delta_x=2,
        minimum_effective_delta_y=8,
        default_duration_ms=700,
        input_source=SwipeInputSource.TOUCHSCREEN,
        default_horizontal_distance_ratio=0.40,
        default_vertical_distance_ratio=0.44,
    ),
    _WorldMapSwipeProfile(
        name="up_right",
        start_x_ratio=0.16,
        start_y_ratio=0.72,
        end_x_ratio=0.80,
        end_y_ratio=0.28,
        expected_delta_x_sign=-1,
        expected_delta_y_sign=1,
        minimum_effective_delta_x=2,
        minimum_effective_delta_y=8,
        default_duration_ms=700,
        input_source=SwipeInputSource.DEFAULT,
        default_horizontal_distance_ratio=0.40,
        default_vertical_distance_ratio=0.44,
    ),
    _WorldMapSwipeProfile(
        name="down_left",
        start_x_ratio=0.80,
        start_y_ratio=0.28,
        end_x_ratio=0.16,
        end_y_ratio=0.72,
        expected_delta_x_sign=1,
        expected_delta_y_sign=-1,
        minimum_effective_delta_x=2,
        minimum_effective_delta_y=8,
        default_duration_ms=700,
        input_source=SwipeInputSource.TOUCHSCREEN,
        default_horizontal_distance_ratio=0.40,
        default_vertical_distance_ratio=0.40,
    ),
    _WorldMapSwipeProfile(
        name="down_right",
        start_x_ratio=0.16,
        start_y_ratio=0.28,
        end_x_ratio=0.80,
        end_y_ratio=0.72,
        expected_delta_x_sign=-1,
        expected_delta_y_sign=-1,
        minimum_effective_delta_x=2,
        minimum_effective_delta_y=8,
        default_duration_ms=700,
        input_source=SwipeInputSource.DEFAULT,
        default_horizontal_distance_ratio=0.40,
        default_vertical_distance_ratio=0.40,
    ),
)
_WORLD_MAP_SWIPE_PROFILE_BY_NAME = {profile.name: profile for profile in _WORLD_MAP_SWIPE_PROFILES}


@dataclass(slots=True)
class WorldMapNavigator(SpatialSurfaceNavigator):
    """Plans coordinate-driven world-map movement and visible world-object taps."""

    surface_type: SpatialSurfaceType = SpatialSurfaceType.WORLD_MAP
    focus_tolerance: int = 1
    min_swipe_ratio: float = 0.08
    max_swipe_ratio: float = 0.72
    max_stagnant_attempts: int = 2
    stagnant_retry_ratio_multiplier: float = 2.0

    def plan_focus_coordinate(
        self,
        observation: Observation,
        target: WorldCoordinate,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> list[ActionRequest]:
        """Plans one coordinate-driven world-map swipe toward the requested target."""

        surface = self.require_surface(observation)
        current_coordinate = surface.viewport.coordinate
        if current_coordinate is None:
            raise SelectorResolutionError(
                "World-map navigation requires a coordinate-addressable viewport.",
                screen_type=observation.screen_type,
            )
        state = _mutable_state(runtime_state, _WORLD_NAVIGATION_STATE_KEY)
        self._update_calibration_state(state=state, current_coordinate=current_coordinate)
        delta_x = target.x - current_coordinate[0]
        delta_y = target.y - current_coordinate[1]
        if abs(delta_x) <= self.focus_tolerance and abs(delta_y) <= self.focus_tolerance:
            state.pop("pending_swipe", None)
            return []
        profile = self._resolve_profile(delta_x=delta_x, delta_y=delta_y)
        horizontal_distance_ratio, vertical_distance_ratio = self._resolve_axis_distance_ratios(
            state=state,
            profile=profile,
            delta_x=delta_x,
            delta_y=delta_y,
        )
        stagnant_attempts = _pending_swipe_stagnant_attempts(state)
        state["pending_swipe"] = {
            "from_coordinate": current_coordinate,
            "profile_name": profile.name,
            "horizontal_distance_ratio": horizontal_distance_ratio,
            "vertical_distance_ratio": vertical_distance_ratio,
            "stagnant_attempts": stagnant_attempts,
        }
        return [
            _build_world_map_navigation_swipe_action(
                profile=profile,
                horizontal_distance_ratio=horizontal_distance_ratio,
                vertical_distance_ratio=vertical_distance_ratio,
                duration_ms=profile.default_duration_ms,
                reason=f"focus_world_coordinate_{profile.name}",
                observe_after=True,
                follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
            )
        ]

    def build_cardinal_probe_action(
        self,
        direction: WorldMapCardinalDirection,
        *,
        distance_ratio: float,
        lane_center_ratio: float | None = None,
        reason: str,
        observe_after: bool = True,
        follow_up_request: ObservationRequest | None = None,
    ) -> SwipeAction:
        """Builds one exact cardinal world-map swipe probe on the requested lane without involving target-coordinate planning."""

        profile = _WORLD_MAP_SWIPE_PROFILE_BY_NAME[direction.value]
        if profile.is_diagonal:
            raise SelectorResolutionError(
                "World-map probe actions only support canonical cardinal directions.",
                direction=direction.value,
            )
        if direction in {WorldMapCardinalDirection.LEFT, WorldMapCardinalDirection.RIGHT}:
            resolved_lane_ratio = profile.start_y_ratio if lane_center_ratio is None else lane_center_ratio
            start_x_ratio, end_x_ratio = _scaled_ratio_pair(
                profile.start_x_ratio,
                profile.end_x_ratio,
                distance_ratio=distance_ratio,
                native_distance_ratio=profile.native_horizontal_distance_ratio,
            )
            start_y_ratio = resolved_lane_ratio
            end_y_ratio = resolved_lane_ratio
        else:
            resolved_lane_ratio = profile.start_x_ratio if lane_center_ratio is None else lane_center_ratio
            start_y_ratio, end_y_ratio = _scaled_ratio_pair(
                profile.start_y_ratio,
                profile.end_y_ratio,
                distance_ratio=distance_ratio,
                native_distance_ratio=profile.native_vertical_distance_ratio,
            )
            start_x_ratio = resolved_lane_ratio
            end_x_ratio = resolved_lane_ratio
        return SwipeAction(
            direction=direction.value,
            distance_ratio=distance_ratio,
            duration_ms=profile.default_duration_ms,
            input_source=profile.input_source,
            reason=reason,
            observe_after=observe_after,
            follow_up_request=follow_up_request,
            start_x_ratio=start_x_ratio,
            start_y_ratio=start_y_ratio,
            end_x_ratio=end_x_ratio,
            end_y_ratio=end_y_ratio,
        )

    def tap_visible_object(
        self,
        observation: Observation,
        target: DetectedSpatialObject,
        *,
        reason: str,
        observe_after: bool = True,
        follow_up_request: ObservationRequest | None = None,
    ) -> list[ActionRequest]:
        """Returns one canonical tap against one exact visible world-map spatial object."""

        self.require_surface(observation).require_visible_object(target)
        return [
            TapSpatialObjectAction(
                query=_query_for_target(self.surface_type, target),
                target_point=_resolve_target_point(target=target, use_action_point=True),
                reason=reason,
                observe_after=observe_after,
                follow_up_request=follow_up_request,
            )
        ]

    def _update_calibration_state(
        self,
        *,
        state: dict[str, Any],
        current_coordinate: tuple[int, int],
    ) -> None:
        """Updates cached swipe-to-coordinate calibration from the latest observed viewport."""

        pending_swipe = state.get("pending_swipe")
        if not isinstance(pending_swipe, dict):
            return
        from_coordinate = pending_swipe.get("from_coordinate")
        if not (
            isinstance(from_coordinate, tuple)
            and len(from_coordinate) == 2
            and isinstance(from_coordinate[0], int)
            and isinstance(from_coordinate[1], int)
        ):
            state.pop("pending_swipe", None)
            return
        profile_name = pending_swipe.get("profile_name")
        if not isinstance(profile_name, str):
            state.pop("pending_swipe", None)
            return
        profile = _WORLD_MAP_SWIPE_PROFILE_BY_NAME.get(profile_name)
        if profile is None:
            state.pop("pending_swipe", None)
            return
        horizontal_distance_ratio = float(
            pending_swipe.get("horizontal_distance_ratio", profile.default_horizontal_distance_ratio)
        )
        vertical_distance_ratio = float(
            pending_swipe.get("vertical_distance_ratio", profile.default_vertical_distance_ratio)
        )
        delta_x = current_coordinate[0] - from_coordinate[0]
        delta_y = current_coordinate[1] - from_coordinate[1]
        if not self._is_effective_profile_movement(profile=profile, delta_x=delta_x, delta_y=delta_y):
            stagnant_attempts = int(pending_swipe.get("stagnant_attempts", 0)) + 1
            if stagnant_attempts > self.max_stagnant_attempts:
                state.pop("pending_swipe", None)
                raise SelectorResolutionError(
                    "World-map navigation swipe did not produce meaningful coordinate movement.",
                    from_coordinate=from_coordinate,
                    current_coordinate=current_coordinate,
                    profile_name=profile.name,
                    delta_x=delta_x,
                    delta_y=delta_y,
                )
            pending_swipe["stagnant_attempts"] = stagnant_attempts
            state["pending_swipe"] = pending_swipe
            return
        calibrations = _mutable_profile_calibrations(state)
        calibration = calibrations.setdefault(profile.name, {})
        if profile.expected_delta_x_sign != 0 and horizontal_distance_ratio > 0:
            calibration["delta_x_per_ratio_unit"] = delta_x / max(horizontal_distance_ratio, 0.01)
        if profile.expected_delta_y_sign != 0 and vertical_distance_ratio > 0:
            calibration["delta_y_per_ratio_unit"] = delta_y / max(vertical_distance_ratio, 0.01)
        state.pop("pending_swipe", None)

    def _resolve_profile(self, *, delta_x: int, delta_y: int) -> _WorldMapSwipeProfile:
        """Returns the best swipe profile for the remaining coordinate delta."""

        want_x = abs(delta_x) > self.focus_tolerance
        want_y = abs(delta_y) > self.focus_tolerance
        if want_x and want_y:
            diagonal_name = _diagonal_profile_name(delta_x=delta_x, delta_y=delta_y)
            assert diagonal_name is not None
            return _WORLD_MAP_SWIPE_PROFILE_BY_NAME[diagonal_name]
        if want_x:
            horizontal_name = "left" if delta_x > 0 else "right"
            return _WORLD_MAP_SWIPE_PROFILE_BY_NAME[horizontal_name]
        if want_y:
            vertical_name = "up" if delta_y > 0 else "down"
            return _WORLD_MAP_SWIPE_PROFILE_BY_NAME[vertical_name]
        raise SelectorResolutionError("World-map profile resolution requires at least one unresolved axis.", delta_x=delta_x, delta_y=delta_y)

    def _resolve_axis_distance_ratios(
        self,
        *,
        state: Mapping[str, Any],
        profile: _WorldMapSwipeProfile,
        delta_x: int,
        delta_y: int,
    ) -> tuple[float, float]:
        """Returns bounded horizontal and vertical swipe spans calibrated independently for the selected profile."""

        calibration = _profile_calibration(state, profile.name)
        delta_x_per_ratio = None if calibration is None else calibration.get("delta_x_per_ratio_unit")
        delta_y_per_ratio = None if calibration is None else calibration.get("delta_y_per_ratio_unit")
        return (
            self._resolve_axis_distance_ratio(
                axis_delta=delta_x,
                expected_sign=profile.expected_delta_x_sign,
                default_ratio=profile.default_horizontal_distance_ratio,
                calibrated_delta_per_ratio=delta_x_per_ratio,
                pending_swipe=state.get("pending_swipe"),
                axis_key="horizontal_distance_ratio",
            ),
            self._resolve_axis_distance_ratio(
                axis_delta=delta_y,
                expected_sign=profile.expected_delta_y_sign,
                default_ratio=profile.default_vertical_distance_ratio,
                calibrated_delta_per_ratio=delta_y_per_ratio,
                pending_swipe=state.get("pending_swipe"),
                axis_key="vertical_distance_ratio",
            ),
        )

    def _resolve_axis_distance_ratio(
        self,
        *,
        axis_delta: int,
        expected_sign: int,
        default_ratio: float,
        calibrated_delta_per_ratio: object,
        pending_swipe: object,
        axis_key: str,
    ) -> float:
        """Returns one bounded axis-specific swipe span from the latest calibration when that axis is active."""

        if expected_sign == 0:
            return 0.0
        if not isinstance(calibrated_delta_per_ratio, int | float) or abs(float(calibrated_delta_per_ratio)) <= 0:
            return self._apply_stagnant_retry_ratio(
                default_ratio=default_ratio,
                pending_swipe=pending_swipe,
                axis_key=axis_key,
            )
        estimated_ratio = abs(axis_delta) / abs(float(calibrated_delta_per_ratio))
        return self._apply_stagnant_retry_ratio(
            default_ratio=max(self.min_swipe_ratio, min(self.max_swipe_ratio, estimated_ratio)),
            pending_swipe=pending_swipe,
            axis_key=axis_key,
        )

    def _apply_stagnant_retry_ratio(
        self,
        *,
        default_ratio: float,
        pending_swipe: object,
        axis_key: str,
    ) -> float:
        """Widens the next swipe span after a stagnant attempt so retries are materially different."""

        if not isinstance(pending_swipe, Mapping):
            return default_ratio
        stagnant_attempts = pending_swipe.get("stagnant_attempts")
        previous_ratio = pending_swipe.get(axis_key)
        if not isinstance(stagnant_attempts, int) or stagnant_attempts <= 0:
            return default_ratio
        if not isinstance(previous_ratio, int | float):
            return default_ratio
        widened_ratio = max(float(previous_ratio), default_ratio) * (self.stagnant_retry_ratio_multiplier**stagnant_attempts)
        return max(self.min_swipe_ratio, min(self.max_swipe_ratio, widened_ratio))

    def _is_effective_profile_movement(
        self,
        *,
        profile: _WorldMapSwipeProfile,
        delta_x: int,
        delta_y: int,
    ) -> bool:
        """Returns whether the observed delta meaningfully matched the selected profile's expected displacement signs."""

        if profile.expected_delta_x_sign != 0:
            if delta_x == 0 or (1 if delta_x > 0 else -1) != profile.expected_delta_x_sign:
                return False
            if abs(delta_x) < profile.minimum_effective_delta_x:
                return False
        if profile.expected_delta_y_sign != 0:
            if delta_y == 0 or (1 if delta_y > 0 else -1) != profile.expected_delta_y_sign:
                return False
            if abs(delta_y) < profile.minimum_effective_delta_y:
                return False
        return True


def _build_world_map_navigation_swipe_action(
    *,
    profile: _WorldMapSwipeProfile,
    horizontal_distance_ratio: float,
    vertical_distance_ratio: float,
    duration_ms: int,
    reason: str,
    observe_after: bool,
    follow_up_request: ObservationRequest | None,
) -> SwipeAction:
    """Builds one world-map drag from the selected calibrated profile, scaled around its safe-lane center."""

    start_x_ratio, end_x_ratio = _scaled_ratio_pair(
        profile.start_x_ratio,
        profile.end_x_ratio,
        distance_ratio=horizontal_distance_ratio,
        native_distance_ratio=profile.native_horizontal_distance_ratio,
    )
    start_y_ratio, end_y_ratio = _scaled_ratio_pair(
        profile.start_y_ratio,
        profile.end_y_ratio,
        distance_ratio=vertical_distance_ratio,
        native_distance_ratio=profile.native_vertical_distance_ratio,
    )
    return SwipeAction(
        direction=profile.name,
        distance_ratio=max(horizontal_distance_ratio, vertical_distance_ratio),
        duration_ms=duration_ms,
        input_source=profile.input_source,
        reason=reason,
        observe_after=observe_after,
        follow_up_request=follow_up_request,
        start_x_ratio=start_x_ratio,
        start_y_ratio=start_y_ratio,
        end_x_ratio=end_x_ratio,
        end_y_ratio=end_y_ratio,
    )


def _pending_swipe_stagnant_attempts(state: Mapping[str, Any]) -> int:
    """Returns the carried bounded stagnant-attempt count for the active pending world-map swipe, if any."""

    pending_swipe = state.get("pending_swipe")
    if not isinstance(pending_swipe, Mapping):
        return 0
    stagnant_attempts = pending_swipe.get("stagnant_attempts")
    if not isinstance(stagnant_attempts, int) or stagnant_attempts < 0:
        return 0
    return stagnant_attempts


@dataclass(slots=True)
class HomeCityNavigator(SpatialSurfaceNavigator):
    """Plans camera-relative home-city search steps and visible city-object taps."""

    surface_type: SpatialSurfaceType = SpatialSurfaceType.HOME_CITY_SURFACE
    focus_tolerance_units: int = 48
    open_focus_tolerance_units: int = 0
    max_swipe_ratio: float = 0.78
    open_safe_left_margin_units: int = 150
    open_safe_right_margin_units: int = 90
    open_safe_top_margin_units: int = 140
    open_safe_bottom_margin_units: int = 515

    def focus_step_budget(self) -> int:
        """Returns the bounded number of canonical fixed-map tour steps available for one home-city search."""

        return len(_home_city_scan_steps()) * _HOME_CITY_FIXED_MAP_TOUR_PASSES

    def estimate_viewport_center(self, observation: Observation) -> HomeCityMapCoordinate | None:
        """Returns the inferred home-city atlas center from the currently visible anchor buildings when possible."""

        estimate = _estimate_home_city_viewport_center(self.require_surface(observation))
        if estimate is None:
            return None
        return estimate.center

    def plan_focus_coordinate(
        self,
        observation: Observation,
        target: HomeCityMapCoordinate,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> list[ActionRequest]:
        """Plans one full atlas-guided swipe series toward the requested inferred viewport center."""

        surface = self.require_surface(observation)
        state = _mutable_state(runtime_state, _HOME_CITY_NAVIGATION_STATE_KEY)
        estimate = _resolve_home_city_viewport_estimate(surface=surface, state=state)
        if estimate is None:
            raise SelectorResolutionError(
                "Home-city atlas navigation requires at least one visible anchor with a recorded atlas coordinate.",
                screen_type=observation.screen_type,
                surface_type=self.surface_type,
            )
        _remember_home_city_viewport_center(state=state, center=estimate.center)
        axis_order = _resolve_home_city_atlas_axis_order(
            surface=surface,
            start_center=estimate.center,
            target_center=_clamp_home_city_viewport_center(target),
        )
        route_plan = _plan_home_city_atlas_route(
            start_center=estimate.center,
            target_center=_clamp_home_city_viewport_center(target),
            focus_tolerance_units=self.focus_tolerance_units,
            max_swipe_ratio=self.max_swipe_ratio,
            reason_prefix="focus_home_city_atlas",
            axis_order=axis_order,
            vertical_swipe_x_ratio=_resolve_home_city_atlas_vertical_swipe_x_ratio(surface, axis_order=axis_order),
            observe_after_last_swipe=True,
            final_follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
        )
        if not route_plan.actions:
            return []
        _remember_home_city_viewport_center(state=state, center=route_plan.predicted_center)
        return list(route_plan.actions)

    def plan_focus_object(
        self,
        observation: Observation,
        query: SpatialObjectQuery,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> list[ActionRequest]:
        """Plans one bounded fixed-map tour increment until the requested object becomes visible."""

        surface = self.require_surface(observation)
        if surface.find_object(query) is not None:
            _clear_state(runtime_state, _HOME_CITY_NAVIGATION_STATE_KEY)
            return []
        target_object_id = _query_home_city_object_id(query)
        target_coordinate = None if target_object_id is None else home_city_map_coordinate(target_object_id)
        state = _mutable_state(runtime_state, _HOME_CITY_NAVIGATION_STATE_KEY)
        _initialize_home_city_query_state(state=state, query=query)
        if target_coordinate is not None and _resolve_home_city_viewport_estimate(surface=surface, state=state) is not None:
            focus_actions = self.plan_focus_coordinate(
                observation,
                target_coordinate,
                runtime_state=runtime_state,
            )
            if focus_actions:
                return focus_actions
        step_index = int(state.get("step_index", 0))
        scan_steps = _home_city_scan_steps()
        if step_index >= self.focus_step_budget():
            raise SelectorResolutionError(
                "Home-city navigation exhausted its canonical fixed-map tour without finding the target object.",
                screen_type=observation.screen_type,
                surface_type=self.surface_type,
                query=_query_signature(query),
            )
        state["step_index"] = step_index + 1
        return [scan_steps[step_index % len(scan_steps)]]

    def plan_open_object(
        self,
        observation: Observation,
        query: SpatialObjectQuery,
        *,
        reason: str,
        runtime_state: dict[str, Any] | None = None,
        observe_after: bool = True,
    ) -> list[ActionRequest]:
        """Plans one home-city open attempt using shortcuts, trusted fixed-view actions, atlas moves, then fallback scan."""

        shortcut_action = _plan_home_city_shortcut_action(
            observation=observation,
            query=query,
            reason=reason,
            observe_after=observe_after,
        )
        if shortcut_action is not None:
            return [shortcut_action]
        surface = self.require_surface(observation)
        target = surface.find_object(query)
        if target is not None:
            return self.tap_visible_object(
                observation,
                target,
                reason=reason,
                runtime_state=runtime_state,
                observe_after=observe_after,
            )
        state = _mutable_state(runtime_state, _HOME_CITY_NAVIGATION_STATE_KEY)
        _initialize_home_city_query_state(state=state, query=query)
        guided_action = _plan_guided_home_city_open_action(
            observation=observation,
            surface=surface,
            query=query,
            state=state,
            observe_after=observe_after,
        )
        if guided_action is not None:
            return [guided_action]
        map_tap_action = _plan_home_city_map_tap_action(
            navigator=self,
            observation=observation,
            surface=surface,
            query=query,
            state=state,
            observe_after=observe_after,
        )
        if map_tap_action is not None:
            return [map_tap_action]
        map_actions = _plan_home_city_map_open_route_actions(
            navigator=self,
            observation=observation,
            surface=surface,
            query=query,
            state=state,
            observe_after=observe_after,
        )
        if map_actions is not None:
            return map_actions
        return self.plan_focus_object(
            observation,
            query,
            runtime_state=runtime_state,
        )

    def tap_visible_object(
        self,
        observation: Observation,
        target: DetectedSpatialObject,
        *,
        reason: str,
        runtime_state: dict[str, Any] | None = None,
        observe_after: bool = True,
    ) -> list[ActionRequest]:
        """Returns one canonical tap against one exact visible home-city spatial object."""

        self.require_surface(observation).require_visible_object(target)
        _clear_state(runtime_state, _HOME_CITY_NAVIGATION_STATE_KEY)
        return [
            TapSpatialObjectAction(
                query=_query_for_target(self.surface_type, target),
                target_point=_resolve_target_point(target=target, use_action_point=True),
                reason=reason,
                observe_after=observe_after,
            )
        ]


def _mutable_state(runtime_state: dict[str, Any] | None, key: str) -> dict[str, Any]:
    """Returns one mutable runtime-state mapping, using a throwaway dict when state is absent."""

    if runtime_state is None:
        return {}
    value = runtime_state.get(key)
    if isinstance(value, dict):
        return value
    new_value: dict[str, Any] = {}
    runtime_state[key] = new_value
    return new_value


def _mapping_of_dict(state: Mapping[str, Any], key: str) -> dict[str, int]:
    """Returns one mutable nested mapping used by navigators that learn directional movement state."""

    value = state.get(key)
    if isinstance(value, dict):
        return value
    new_value: dict[str, int] = {}
    if isinstance(state, dict):
        state[key] = new_value
    return new_value


def _mutable_profile_calibrations(state: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Returns one mutable nested calibration mapping keyed by world-map swipe-profile name."""

    value = state.get("profile_calibrations")
    if isinstance(value, dict):
        return value
    new_value: dict[str, dict[str, float]] = {}
    state["profile_calibrations"] = new_value
    return new_value


def _profile_calibration(state: Mapping[str, Any], profile_name: str) -> Mapping[str, float] | None:
    """Returns the stored calibration for one swipe profile when available."""

    calibrations = state.get("profile_calibrations")
    if not isinstance(calibrations, Mapping):
        return None
    calibration = calibrations.get(profile_name)
    if not isinstance(calibration, Mapping):
        return None
    return calibration


def _diagonal_profile_name(*, delta_x: int, delta_y: int) -> str | None:
    """Returns the diagonal swipe-profile name matching the remaining coordinate signs, when both axes are active."""

    if delta_x == 0 or delta_y == 0:
        return None
    horizontal = "left" if delta_x > 0 else "right"
    vertical = "up" if delta_y > 0 else "down"
    return f"{vertical}_{horizontal}"


def _scaled_ratio_pair(
    start_ratio: float,
    end_ratio: float,
    *,
    distance_ratio: float,
    native_distance_ratio: float,
) -> tuple[float, float]:
    """Returns one normalized start/end pair centered on the original lane and scaled to the requested swipe span."""

    if abs(start_ratio - end_ratio) < 1e-9:
        return start_ratio, end_ratio
    center_ratio = (start_ratio + end_ratio) / 2
    native_half_distance = abs(start_ratio - end_ratio) / 2
    scale = distance_ratio / max(native_distance_ratio, 0.01)
    half_distance = native_half_distance * scale
    if start_ratio <= end_ratio:
        return (
            max(0.0, center_ratio - half_distance),
            min(1.0, center_ratio + half_distance),
        )
    return (
        min(1.0, center_ratio + half_distance),
        max(0.0, center_ratio - half_distance),
    )


def _clear_state(runtime_state: dict[str, Any] | None, key: str) -> None:
    """Clears one navigation-state bucket when the requested target has been resolved."""

    if runtime_state is None:
        return
    runtime_state.pop(key, None)


def _initialize_home_city_query_state(*, state: dict[str, Any], query: SpatialObjectQuery) -> None:
    """Resets shared home-city navigation state whenever the requested semantic target changes."""

    query_signature = _query_signature(query)
    if state.get("query_signature") == query_signature:
        return
    remembered_center = state.get("known_viewport_center")
    state.clear()
    if (
        isinstance(remembered_center, tuple)
        and len(remembered_center) == 2
        and isinstance(remembered_center[0], int)
        and isinstance(remembered_center[1], int)
    ):
        state["known_viewport_center"] = remembered_center
    state["query_signature"] = query_signature
    state["step_index"] = 0


def _query_signature(query: SpatialObjectQuery) -> tuple[object, ...]:
    """Returns one stable query signature so camera-relative search can reset on target changes."""

    return (
        query.surface_type,
        query.kind,
        query.relationship,
        query.name_text,
        query.alliance_tag,
        query.level,
        query.metadata_key,
        query.metadata_value,
    )


def _plan_home_city_shortcut_action(
    *,
    observation: Observation,
    query: SpatialObjectQuery,
    reason: str,
    observe_after: bool,
) -> TapAction | None:
    """Returns one trusted home-city shortcut tap when the target building has an authoritative direct affordance."""

    if (
        _query_home_city_object_id(query) == HomeCityObjectId.INSTITUTE
        and observation.has(UiElementId.PNC_HOME_RESEARCH_BUTTON)
    ):
        return TapAction(
            selector_id=UiElementId.PNC_HOME_RESEARCH_BUTTON,
            reason=reason,
            observe_after=observe_after,
        )
    return None


def _plan_home_city_map_tap_action(
    *,
    navigator: HomeCityNavigator,
    observation: Observation,
    surface: SpatialSurfaceObservation,
    query: SpatialObjectQuery,
    state: dict[str, Any],
    observe_after: bool,
) -> TapPointAction | None:
    """Returns one atlas-guided direct tap when the recorded target should already be inside the current viewport."""

    target_object_id = _query_home_city_object_id(query)
    if target_object_id is None:
        return None
    target_coordinate = home_city_map_coordinate(target_object_id)
    if target_coordinate is None:
        return None
    estimate = _resolve_home_city_viewport_estimate(surface=surface, state=state)
    if estimate is None:
        return None
    _remember_home_city_viewport_center(state=state, center=estimate.center)
    center_signature = _home_city_estimate_signature(estimate.center)
    tap_point = _resolve_home_city_open_tap_point(
        navigator=navigator,
        observation=observation,
        viewport_center=estimate.center,
        target_coordinate=target_coordinate,
    )
    if tap_point is not None and _remember_guided_view_attempt(
        state=state,
        attempt_id=f"atlas_tap_{target_object_id.value}",
        view_signature=center_signature,
    ):
        return TapPointAction(
            x=tap_point[0],
            y=tap_point[1],
            reason=f"open_{target_object_id.value}_from_home_city_atlas",
            observe_after=observe_after,
        )
    return None


def _plan_home_city_map_open_route_actions(
    *,
    navigator: HomeCityNavigator,
    observation: Observation,
    surface: SpatialSurfaceObservation,
    query: SpatialObjectQuery,
    state: dict[str, Any],
    observe_after: bool,
) -> list[ActionRequest] | None:
    """Returns one precomputed atlas-guided swipe series plus final tap for one offscreen recorded home-city object."""

    target_object_id = _query_home_city_object_id(query)
    if target_object_id is None:
        return None
    target_coordinate = home_city_map_coordinate(target_object_id)
    if target_coordinate is None:
        return None
    estimate = _resolve_home_city_viewport_estimate(surface=surface, state=state)
    if estimate is None:
        return None
    _remember_home_city_viewport_center(state=state, center=estimate.center)
    current_view_signature = _home_city_estimate_signature(estimate.center)
    desired_center = _resolve_home_city_open_route_target_center(
        navigator=navigator,
        current_center=estimate.center,
        target_coordinate=target_coordinate,
    )
    route_attempt_id = f"atlas_route_{target_object_id.value}"
    if desired_center == estimate.center or not _remember_guided_view_attempt(
        state=state,
        attempt_id=route_attempt_id,
        view_signature=current_view_signature,
    ):
        return None
    axis_order = _resolve_home_city_atlas_axis_order(
        surface=surface,
        start_center=estimate.center,
        target_center=desired_center,
    )
    route_plan = _plan_home_city_atlas_route(
        start_center=estimate.center,
        target_center=desired_center,
        focus_tolerance_units=navigator.open_focus_tolerance_units,
        max_swipe_ratio=navigator.max_swipe_ratio,
        reason_prefix=f"focus_{target_object_id.value}_from_home_city_atlas",
        axis_order=axis_order,
        vertical_swipe_x_ratio=_resolve_home_city_atlas_vertical_swipe_x_ratio(surface, axis_order=axis_order),
    )
    if not route_plan.actions:
        return None
    _remember_home_city_viewport_center(state=state, center=route_plan.predicted_center)
    predicted_view_signature = _home_city_estimate_signature(route_plan.predicted_center)
    if not _remember_guided_view_attempt(
        state=state,
        attempt_id=f"atlas_tap_{target_object_id.value}",
        view_signature=predicted_view_signature,
    ):
        return None
    tap_point = _resolve_home_city_open_tap_point(
        navigator=navigator,
        observation=observation,
        viewport_center=route_plan.predicted_center,
        target_coordinate=target_coordinate,
    )
    if tap_point is None:
        raise SelectorResolutionError(
            "Atlas route planning produced a final home-city viewport that still cannot tap the requested building.",
            target_object_id=target_object_id.value,
            predicted_center=(route_plan.predicted_center.x, route_plan.predicted_center.y),
            target_coordinate=(target_coordinate.x, target_coordinate.y),
        )
    return [
        *route_plan.actions,
        TapPointAction(
            x=tap_point[0],
            y=tap_point[1],
            reason=f"open_{target_object_id.value}_from_home_city_atlas",
            observe_after=observe_after,
        ),
    ]


def _plan_guided_home_city_open_action(
    *,
    observation: Observation,
    surface: SpatialSurfaceObservation,
    query: SpatialObjectQuery,
    state: dict[str, Any],
    observe_after: bool,
) -> ActionRequest | None:
    """Returns one anchor-guarded direct tap or deterministic transition toward the requested home-city target."""

    target_object_id = _query_home_city_object_id(query)
    if target_object_id is None:
        return None
    visible_object_ids = _visible_home_city_object_ids(surface)
    if not visible_object_ids:
        return None
    view_signature = tuple(sorted(object_id.value for object_id in visible_object_ids))
    for tap_spec in _known_view_tap_specs(visible_object_ids=visible_object_ids, target_object_id=target_object_id):
        if not _remember_guided_view_attempt(state=state, attempt_id=tap_spec.reason, view_signature=view_signature):
            continue
        return _materialize_guided_tap_action(observation=observation, tap_spec=tap_spec, observe_after=observe_after)
    for route in _HOME_CITY_GUIDED_ROUTE_SPECS:
        if target_object_id not in route.target_object_ids:
            continue
        if not route.required_visible_object_ids.issubset(visible_object_ids):
            continue
        if not _remember_guided_view_attempt(
            state=state,
            attempt_id=route.swipe_action.reason,
            view_signature=view_signature,
        ):
            continue
        return route.swipe_action
    return None


def _known_view_tap_specs(
    *,
    visible_object_ids: frozenset[HomeCityObjectId],
    target_object_id: HomeCityObjectId,
) -> tuple[_HomeCityKnownViewTapSpec, ...]:
    """Returns the normalized direct taps calibrated for the currently proven home-city view."""

    matching_specs: list[_HomeCityKnownViewTapSpec] = []
    for view_spec in _HOME_CITY_KNOWN_VIEW_SPECS:
        if not view_spec.required_visible_object_ids.issubset(visible_object_ids):
            continue
        matching_specs.extend(
            tap_spec for tap_spec in view_spec.tap_specs if tap_spec.target_object_id == target_object_id
        )
    return tuple(matching_specs)


def _query_home_city_object_id(query: SpatialObjectQuery) -> HomeCityObjectId | None:
    """Returns the exact home-city object id targeted by one semantic surface query when available."""

    if query.surface_type != SpatialSurfaceType.HOME_CITY_SURFACE:
        return None
    if query.metadata_key != "home_city_object_id" or not isinstance(query.metadata_value, str):
        return None
    try:
        return HomeCityObjectId(query.metadata_value)
    except ValueError:
        return None


def _visible_home_city_object_ids(surface: SpatialSurfaceObservation) -> frozenset[HomeCityObjectId]:
    """Returns the exact home-city object ids currently visible in the parsed fixed-map view."""

    visible_ids: set[HomeCityObjectId] = set()
    for object_ in surface.objects:
        object_id = home_city_object_id_from_metadata(object_.metadata)
        if object_id is not None:
            visible_ids.add(object_id)
    return frozenset(visible_ids)


def _estimate_home_city_viewport_center(surface: SpatialSurfaceObservation) -> _HomeCityViewportEstimate | None:
    """Returns the inferred atlas center by reconciling visible anchor offsets against recorded building coordinates."""

    atlas = home_city_map_atlas()
    center_candidates: list[tuple[int, int]] = []
    for object_ in surface.objects:
        object_id = home_city_object_id_from_metadata(object_.metadata)
        if object_id is None or object_.viewport_offset_ratio is None:
            continue
        if not is_home_city_object_usable_as_atlas_anchor(object_id):
            continue
        map_coordinate = home_city_map_coordinate(object_id)
        if map_coordinate is None:
            continue
        center_candidates.append(
            (
                map_coordinate.x - int(round(object_.viewport_offset_ratio[0] * atlas.viewport_width_units)),
                map_coordinate.y - int(round(object_.viewport_offset_ratio[1] * atlas.viewport_height_units)),
            )
        )
    if not center_candidates:
        return None
    x_candidates = sorted(candidate[0] for candidate in center_candidates)
    y_candidates = sorted(candidate[1] for candidate in center_candidates)
    center = HomeCityMapCoordinate(
        x=x_candidates[len(x_candidates) // 2],
        y=y_candidates[len(y_candidates) // 2],
    )
    return _HomeCityViewportEstimate(center=center, evidence_count=len(center_candidates))


def _resolve_home_city_viewport_estimate(
    *,
    surface: SpatialSurfaceObservation,
    state: Mapping[str, Any],
) -> _HomeCityViewportEstimate | None:
    """Returns the freshest anchor-backed viewport estimate or the last remembered planned center when anchors are absent."""

    estimate = _estimate_home_city_viewport_center(surface)
    if estimate is not None:
        return estimate
    remembered_center = _remembered_home_city_viewport_center(state)
    if remembered_center is None:
        return None
    return _HomeCityViewportEstimate(center=remembered_center, evidence_count=0)


def _remember_home_city_viewport_center(*, state: dict[str, Any], center: HomeCityMapCoordinate) -> None:
    """Stores the best-known current home-city viewport center so later blind taps can reuse planned movement."""

    state["known_viewport_center"] = (center.x, center.y)


def _remembered_home_city_viewport_center(state: Mapping[str, Any]) -> HomeCityMapCoordinate | None:
    """Returns the last remembered home-city viewport center when one was persisted in runtime state."""

    value = state.get("known_viewport_center")
    if not (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], int)
        and isinstance(value[1], int)
    ):
        return None
    return HomeCityMapCoordinate(x=value[0], y=value[1])


def _plan_home_city_atlas_route(
    *,
    start_center: HomeCityMapCoordinate,
    target_center: HomeCityMapCoordinate,
    focus_tolerance_units: int,
    max_swipe_ratio: float,
    reason_prefix: str,
    axis_order: tuple[str, str] | None = None,
    vertical_swipe_x_ratio: float = _HOME_CITY_ATLAS_VERTICAL_SWIPE_X_RATIO,
    horizontal_swipe_y_ratio: float = _HOME_CITY_ATLAS_HORIZONTAL_SWIPE_Y_RATIO,
    observe_after_last_swipe: bool = False,
    final_follow_up_request: ObservationRequest | None = None,
) -> _HomeCityAtlasRoutePlan:
    """Builds one deterministic swipe series from the inferred viewport center to the requested atlas center."""

    atlas = home_city_map_atlas()
    predicted_x = start_center.x
    predicted_y = start_center.y
    actions: list[SwipeAction] = []
    planned_axis_order = (
        axis_order
        if axis_order is not None
        else (("x", "y") if abs(target_center.x - predicted_x) >= abs(target_center.y - predicted_y) else ("y", "x"))
    )
    for axis in planned_axis_order:
        viewport_units = atlas.viewport_width_units if axis == "x" else atlas.viewport_height_units
        max_step_units = int(round(max_swipe_ratio * viewport_units))
        if max_step_units <= 0:
            raise SelectorResolutionError(
                "Home-city atlas route planning requires a positive max swipe span.",
                max_swipe_ratio=max_swipe_ratio,
                axis=axis,
            )
        while True:
            remaining_delta = (target_center.x - predicted_x) if axis == "x" else (target_center.y - predicted_y)
            if abs(remaining_delta) <= focus_tolerance_units:
                break
            step_units = min(abs(remaining_delta), max_step_units)
            if step_units <= 0:
                raise SelectorResolutionError(
                    "Home-city atlas route planning computed a non-positive swipe span.",
                    axis=axis,
                    remaining_delta=remaining_delta,
                )
            direction = _home_city_atlas_swipe_direction(axis=axis, remaining_delta=remaining_delta)
            actions.append(
                _build_home_city_atlas_swipe_action(
                    direction=direction,
                    distance_ratio=step_units / viewport_units,
                    reason=f"{reason_prefix}_{axis}",
                    vertical_swipe_x_ratio=vertical_swipe_x_ratio,
                    horizontal_swipe_y_ratio=horizontal_swipe_y_ratio,
                )
            )
            if axis == "x":
                predicted_x += step_units if remaining_delta > 0 else -step_units
            else:
                predicted_y += step_units if remaining_delta > 0 else -step_units
    if actions:
        last_action = actions[-1]
        actions[-1] = SwipeAction(
            direction=last_action.direction,
            distance_ratio=last_action.distance_ratio,
            duration_ms=last_action.duration_ms,
            reason=last_action.reason,
            observe_after=observe_after_last_swipe,
            follow_up_request=final_follow_up_request if observe_after_last_swipe else None,
            timing_profile=last_action.timing_profile,
            start_x_ratio=last_action.start_x_ratio,
            start_y_ratio=last_action.start_y_ratio,
            end_x_ratio=last_action.end_x_ratio,
            end_y_ratio=last_action.end_y_ratio,
        )
    return _HomeCityAtlasRoutePlan(
        actions=tuple(actions),
        predicted_center=HomeCityMapCoordinate(x=predicted_x, y=predicted_y),
    )


def _home_city_atlas_swipe_direction(*, axis: str, remaining_delta: int) -> str:
    """Returns the canonical directional swipe that moves the home-city viewport toward the remaining atlas delta."""

    if axis == "x":
        return "left" if remaining_delta > 0 else "right"
    return "up" if remaining_delta > 0 else "down"


def _build_home_city_atlas_swipe_action(
    *,
    direction: str,
    distance_ratio: float,
    reason: str,
    vertical_swipe_x_ratio: float,
    horizontal_swipe_y_ratio: float,
) -> SwipeAction:
    """Builds one atlas-guided swipe on a reviewed safe lane so home-city pans are not intercepted by buildings."""

    half_ratio = distance_ratio / 2
    if direction == "left":
        return SwipeAction(
            direction=direction,
            distance_ratio=distance_ratio,
            duration_ms=320,
            reason=reason,
            observe_after=False,
            start_x_ratio=min(0.92, 0.5 + half_ratio),
            start_y_ratio=horizontal_swipe_y_ratio,
            end_x_ratio=max(0.08, 0.5 - half_ratio),
            end_y_ratio=horizontal_swipe_y_ratio,
        )
    if direction == "right":
        return SwipeAction(
            direction=direction,
            distance_ratio=distance_ratio,
            duration_ms=320,
            reason=reason,
            observe_after=False,
            start_x_ratio=max(0.08, 0.5 - half_ratio),
            start_y_ratio=horizontal_swipe_y_ratio,
            end_x_ratio=min(0.92, 0.5 + half_ratio),
            end_y_ratio=horizontal_swipe_y_ratio,
        )
    if direction == "up":
        return SwipeAction(
            direction=direction,
            distance_ratio=distance_ratio,
            duration_ms=320,
            reason=reason,
            observe_after=False,
            start_x_ratio=vertical_swipe_x_ratio,
            start_y_ratio=min(0.92, 0.5 + half_ratio),
            end_x_ratio=vertical_swipe_x_ratio,
            end_y_ratio=max(0.08, 0.5 - half_ratio),
        )
    if direction == "down":
        return SwipeAction(
            direction=direction,
            distance_ratio=distance_ratio,
            duration_ms=320,
            reason=reason,
            observe_after=False,
            start_x_ratio=vertical_swipe_x_ratio,
            start_y_ratio=max(0.08, 0.5 - half_ratio),
            end_x_ratio=vertical_swipe_x_ratio,
            end_y_ratio=min(0.92, 0.5 + half_ratio),
        )
    raise SelectorResolutionError("Unsupported home-city atlas swipe direction.", direction=direction)


def _resolve_home_city_atlas_vertical_swipe_x_ratio(
    surface: SpatialSurfaceObservation,
    *,
    axis_order: tuple[str, str],
) -> float:
    """Chooses the reviewed vertical swipe lane for the currently visible home-city skyline band."""

    if axis_order[0] != "y":
        return _HOME_CITY_ATLAS_VERTICAL_SWIPE_X_RATIO
    visible_object_ids = {
        object_id
        for object_ in surface.objects
        for object_id in (home_city_object_id_from_metadata(getattr(object_, "metadata", {})),)
        if object_id is not None
    }
    if visible_object_ids & {
        HomeCityObjectId.SAUROI_LAIR,
        HomeCityObjectId.CAMPAIGN,
        HomeCityObjectId.ARENA,
    }:
        return _HOME_CITY_RIGHT_VIEW_VERTICAL_SWIPE_X_RATIO
    if visible_object_ids & {
        HomeCityObjectId.CASTLE,
        HomeCityObjectId.INSTITUTE,
        HomeCityObjectId.WAREHOUSE,
        HomeCityObjectId.WATCHTOWER,
    }:
        # The castle / institute / warehouse skyline blocks the default center lane, so route
        # vertical pans through the reviewed courtyard / canyon strip on the right side instead.
        return _HOME_CITY_CASTLE_UTILITY_VERTICAL_SWIPE_X_RATIO
    return _HOME_CITY_ATLAS_VERTICAL_SWIPE_X_RATIO


def _resolve_home_city_atlas_axis_order(
    *,
    surface: SpatialSurfaceObservation,
    start_center: HomeCityMapCoordinate,
    target_center: HomeCityMapCoordinate,
) -> tuple[str, str]:
    """Chooses the deterministic axis order for one blind atlas route from the current skyline band."""

    visible_object_ids = {
        object_id
        for object_ in surface.objects
        for object_id in (home_city_object_id_from_metadata(getattr(object_, "metadata", {})),)
        if object_id is not None
    }
    if (
        target_center.x != start_center.x
        and target_center.y != start_center.y
        and visible_object_ids
        & {
            HomeCityObjectId.SAUROI_LAIR,
            HomeCityObjectId.CAMPAIGN,
            HomeCityObjectId.ARENA,
        }
    ):
        return ("x", "y")
    return ("x", "y") if abs(target_center.x - start_center.x) >= abs(target_center.y - start_center.y) else ("y", "x")


def _resolve_home_city_open_route_target_center(
    *,
    navigator: HomeCityNavigator,
    current_center: HomeCityMapCoordinate,
    target_coordinate: HomeCityMapCoordinate,
) -> HomeCityMapCoordinate:
    """Returns the closest viewport center that would place the target inside a safe tap band."""

    delta_bounds = _home_city_open_safe_delta_bounds(navigator)
    desired_x = min(
        max(current_center.x, target_coordinate.x - delta_bounds.max_delta_x),
        target_coordinate.x - delta_bounds.min_delta_x,
    )
    desired_y = min(
        max(current_center.y, target_coordinate.y - delta_bounds.max_delta_y),
        target_coordinate.y - delta_bounds.min_delta_y,
    )
    return _clamp_home_city_viewport_center(HomeCityMapCoordinate(x=desired_x, y=desired_y))


def _clamp_home_city_viewport_center(center: HomeCityMapCoordinate) -> HomeCityMapCoordinate:
    """Clamps one requested home-city viewport center to the valid atlas bounds."""

    atlas = home_city_map_atlas()
    half_viewport_width = atlas.viewport_width_units // 2
    half_viewport_height = atlas.viewport_height_units // 2
    return HomeCityMapCoordinate(
        x=min(max(center.x, half_viewport_width), atlas.width_units - half_viewport_width),
        y=min(max(center.y, half_viewport_height), atlas.height_units - half_viewport_height),
    )


def _home_city_estimate_signature(center: HomeCityMapCoordinate) -> tuple[str, ...]:
    """Returns one stable coarse signature for the inferred atlas center used to deduplicate map taps."""

    return (
        "atlas",
        f"x{center.x // 80}",
        f"y{center.y // 80}",
    )


@dataclass(frozen=True, slots=True)
class _HomeCityOpenSafeDeltaBounds:
    """Defines the atlas-space delta window whose projected tap lands in the safe home-city click band."""

    min_delta_x: int
    max_delta_x: int
    min_delta_y: int
    max_delta_y: int


def _home_city_open_safe_delta_bounds(navigator: HomeCityNavigator) -> _HomeCityOpenSafeDeltaBounds:
    """Returns the canonical atlas-space delta bounds that keep blind home-city taps off persistent HUD chrome."""

    atlas = home_city_map_atlas()
    half_viewport_width = atlas.viewport_width_units // 2
    half_viewport_height = atlas.viewport_height_units // 2
    safe_left = min(max(0, navigator.open_safe_left_margin_units), atlas.viewport_width_units - 1)
    safe_right = min(max(0, navigator.open_safe_right_margin_units), atlas.viewport_width_units - 1)
    safe_top = min(max(0, navigator.open_safe_top_margin_units), atlas.viewport_height_units - 1)
    safe_bottom = min(max(0, navigator.open_safe_bottom_margin_units), atlas.viewport_height_units - 1)
    max_tap_x = max(safe_left, atlas.viewport_width_units - safe_right)
    max_tap_y = max(safe_top, atlas.viewport_height_units - safe_bottom)
    return _HomeCityOpenSafeDeltaBounds(
        min_delta_x=safe_left - half_viewport_width,
        max_delta_x=max_tap_x - half_viewport_width,
        min_delta_y=safe_top - half_viewport_height,
        max_delta_y=max_tap_y - half_viewport_height,
    )


def _resolve_home_city_open_tap_point(
    *,
    navigator: HomeCityNavigator,
    observation: Observation,
    viewport_center: HomeCityMapCoordinate,
    target_coordinate: HomeCityMapCoordinate,
) -> tuple[int, int] | None:
    """Returns the direct tap point implied by the atlas when the target should already be inside the safe click band."""

    atlas = home_city_map_atlas()
    delta_x = target_coordinate.x - viewport_center.x
    delta_y = target_coordinate.y - viewport_center.y
    if abs(delta_x) > atlas.viewport_width_units // 2 or abs(delta_y) > atlas.viewport_height_units // 2:
        return None
    delta_bounds = _home_city_open_safe_delta_bounds(navigator)
    if (
        delta_x < delta_bounds.min_delta_x
        or delta_x > delta_bounds.max_delta_x
        or delta_y < delta_bounds.min_delta_y
        or delta_y > delta_bounds.max_delta_y
    ):
        return None
    width, height = _require_image_size(observation)
    tap_x = int(round((width / 2) + (delta_x * width / atlas.viewport_width_units)))
    tap_y = int(round((height / 2) + (delta_y * height / atlas.viewport_height_units)))
    if tap_x < 0 or tap_x >= width or tap_y < 0 or tap_y >= height:
        return None
    return tap_x, tap_y


def _materialize_guided_tap_action(
    *,
    observation: Observation,
    tap_spec: _HomeCityKnownViewTapSpec,
    observe_after: bool,
) -> TapPointAction:
    """Builds one direct tap request from one anchor-guarded normalized tap spec."""

    width, height = _require_image_size(observation)
    return TapPointAction(
        x=int(round(width * tap_spec.tap_x_ratio)),
        y=int(round(height * tap_spec.tap_y_ratio)),
        reason=tap_spec.reason,
        observe_after=observe_after,
    )


def _require_image_size(observation: Observation) -> tuple[int, int]:
    """Returns the screenshot size needed for fixed-ratio home-city taps or fails fast when unavailable."""

    if observation.image_size is None:
        raise SelectorResolutionError(
            "Home-city fixed-view taps require the current observation image size.",
            screen_type=observation.screen_type,
        )
    return observation.image_size


def _remember_guided_view_attempt(
    *,
    state: dict[str, Any],
    attempt_id: str,
    view_signature: tuple[str, ...],
) -> bool:
    """Returns whether one guided fixed-map move is still fresh for the current visible-view signature."""

    attempts = state.get("guided_attempts")
    if not isinstance(attempts, set):
        attempts = set()
        state["guided_attempts"] = attempts
    key = (attempt_id, view_signature)
    if key in attempts:
        return False
    attempts.add(key)
    state["guided_attempts"] = attempts
    return True


def _home_city_scan_steps() -> tuple[SwipeAction, ...]:
    """Returns the canonical fixed-map tour: upper sweep right-to-left, lower shift, lower sweep left-to-right, then reset."""

    return (
        SwipeAction(
            direction="left",
            distance_ratio=0.78,
            duration_ms=350,
            reason="scan_home_city_upper_right_to_left_1",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.80,
            start_y_ratio=0.46,
            end_x_ratio=0.16,
            end_y_ratio=0.46,
        ),
        SwipeAction(
            direction="left",
            distance_ratio=0.78,
            duration_ms=350,
            reason="scan_home_city_upper_right_to_left_2",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.80,
            start_y_ratio=0.46,
            end_x_ratio=0.16,
            end_y_ratio=0.46,
        ),
        SwipeAction(
            direction="down",
            distance_ratio=0.56,
            duration_ms=350,
            reason="scan_home_city_shift_to_lower_view",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.54,
            start_y_ratio=0.34,
            end_x_ratio=0.54,
            end_y_ratio=0.82,
        ),
        SwipeAction(
            direction="right",
            distance_ratio=0.82,
            duration_ms=350,
            reason="scan_home_city_lower_left_to_right_1",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.18,
            start_y_ratio=0.64,
            end_x_ratio=0.82,
            end_y_ratio=0.64,
        ),
        SwipeAction(
            direction="right",
            distance_ratio=0.82,
            duration_ms=350,
            reason="scan_home_city_lower_left_to_right_2",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.18,
            start_y_ratio=0.64,
            end_x_ratio=0.82,
            end_y_ratio=0.64,
        ),
        SwipeAction(
            direction="up",
            distance_ratio=0.56,
            duration_ms=350,
            reason="scan_home_city_reset_to_upper_view",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.55,
            start_y_ratio=0.72,
            end_x_ratio=0.55,
            end_y_ratio=0.28,
        ),
    )


def _resolve_target_point(*, target: DetectedSpatialObject, use_action_point: bool) -> tuple[int, int]:
    """Returns the concrete tap point captured for one visible spatial object."""

    if use_action_point and target.action_point is not None:
        return target.action_point
    return target.bounds.center()


def _query_for_target(surface_type: SpatialSurfaceType, target: DetectedSpatialObject) -> SpatialObjectQuery:
    """Builds the narrowest reusable semantic query available for one visible spatial object."""

    metadata = dict(target.metadata)
    metadata_key = None
    metadata_value = None
    if "home_city_object_id" in metadata:
        metadata_key = "home_city_object_id"
        metadata_value = metadata["home_city_object_id"]
    elif "resource_type" in metadata:
        metadata_key = "resource_type"
        metadata_value = metadata["resource_type"]
    return SpatialObjectQuery(
        surface_type=surface_type,
        kind=target.kind,
        relationship=target.relationship,
        name_text=target.name_text,
        alliance_tag=target.alliance_tag,
        kingdom=target.kingdom,
        level=target.level,
        metadata_key=metadata_key,
        metadata_value=metadata_value,
    )
