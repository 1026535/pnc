"""Canonical spatial-surface navigation helpers shared by flows and tasks."""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.action_requests import ActionRequest, SwipeAction, TapSpatialObjectAction
from pnc_automation.pnc.observation import Observation, SpatialObjectQuery, SpatialSurfaceObservation, SpatialSurfaceType
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.vision.observation_request import ObservationRequest

_WORLD_NAVIGATION_STATE_KEY = "world_map_navigation"
_HOME_CITY_NAVIGATION_STATE_KEY = "home_city_navigation"


@dataclass(frozen=True, slots=True)
class WorldCoordinate:
    """Represents one absolute world-map coordinate target."""

    x: int
    y: int

    def __post_init__(self) -> None:
        """Rejects invalid coordinate targets before they reach navigation planning."""

        if self.x < 0 or self.y < 0:
            raise SelectorResolutionError("World coordinates must be non-negative integers.", x=self.x, y=self.y)


class SpatialSurfaceNavigator(ABC):
    """Minimal shared contract implemented by concrete surface-specific navigators."""

    surface_type: SpatialSurfaceType

    def require_surface(self, observation: Observation) -> SpatialSurfaceObservation:
        """Returns the active surface or fails fast when the current observation is incompatible."""

        return observation.require_spatial_surface(self.surface_type)


@dataclass(slots=True)
class WorldMapNavigator(SpatialSurfaceNavigator):
    """Plans coordinate-driven world-map movement and visible world-object taps."""

    surface_type: SpatialSurfaceType = SpatialSurfaceType.WORLD_MAP
    focus_tolerance: int = 3
    default_swipe_ratio: float = 0.45
    min_swipe_ratio: float = 0.18
    max_swipe_ratio: float = 0.72
    max_stagnant_attempts: int = 1

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
        axis = "x" if abs(delta_x) >= abs(delta_y) else "y"
        remaining_delta = delta_x if axis == "x" else delta_y
        direction = self._resolve_direction(state=state, axis=axis, remaining_delta=remaining_delta)
        distance_ratio = self._resolve_distance_ratio(state=state, axis=axis, remaining_delta=remaining_delta)
        state["pending_swipe"] = {
            "from_coordinate": current_coordinate,
            "direction": direction,
            "distance_ratio": distance_ratio,
            "stagnant_attempts": 0,
        }
        return [
            SwipeAction(
                direction=direction,
                distance_ratio=distance_ratio,
                duration_ms=350,
                reason=f"focus_world_coordinate_{axis}",
                observe_after=True,
                follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP),
            )
        ]

    def tap_visible_object(
        self,
        observation: Observation,
        query: SpatialObjectQuery,
        *,
        reason: str,
        observe_after: bool = True,
    ) -> list[ActionRequest]:
        """Returns one canonical tap against a visible world-map spatial object."""

        self.require_surface(observation).require_object(query)
        return [
            TapSpatialObjectAction(
                query=query,
                reason=reason,
                observe_after=observe_after,
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
        if current_coordinate == from_coordinate:
            stagnant_attempts = int(pending_swipe.get("stagnant_attempts", 0)) + 1
            if stagnant_attempts > self.max_stagnant_attempts:
                state.pop("pending_swipe", None)
                raise SelectorResolutionError(
                    "World-map navigation swipe did not produce any coordinate movement.",
                    from_coordinate=from_coordinate,
                    current_coordinate=current_coordinate,
                    direction=pending_swipe.get("direction"),
                )
            pending_swipe["stagnant_attempts"] = stagnant_attempts
            return
        direction = pending_swipe.get("direction")
        if not isinstance(direction, str):
            state.pop("pending_swipe", None)
            return
        distance_ratio = float(pending_swipe.get("distance_ratio", self.default_swipe_ratio))
        delta_x = current_coordinate[0] - from_coordinate[0]
        delta_y = current_coordinate[1] - from_coordinate[1]
        horizontal_signs = _mapping_of_dict(state, "horizontal_signs")
        vertical_signs = _mapping_of_dict(state, "vertical_signs")
        if direction in {"left", "right"} and delta_x != 0:
            horizontal_signs[direction] = 1 if delta_x > 0 else -1
            state["horizontal_ratio_unit_delta"] = abs(delta_x) / max(distance_ratio, 0.01)
        if direction in {"up", "down"} and delta_y != 0:
            vertical_signs[direction] = 1 if delta_y > 0 else -1
            state["vertical_ratio_unit_delta"] = abs(delta_y) / max(distance_ratio, 0.01)
        state.pop("pending_swipe", None)

    def _resolve_direction(self, *, state: Mapping[str, Any], axis: str, remaining_delta: int) -> str:
        """Returns the swipe direction that most likely reduces the remaining coordinate delta."""

        desired_sign = 1 if remaining_delta > 0 else -1
        if axis == "x":
            horizontal_signs = _mapping_of_dict(state, "horizontal_signs")
            for direction in ("left", "right"):
                if horizontal_signs.get(direction) == desired_sign:
                    return direction
            return "left" if remaining_delta > 0 else "right"
        vertical_signs = _mapping_of_dict(state, "vertical_signs")
        for direction in ("up", "down"):
            if vertical_signs.get(direction) == desired_sign:
                return direction
        return "up" if remaining_delta > 0 else "down"

    def _resolve_distance_ratio(self, *, state: Mapping[str, Any], axis: str, remaining_delta: int) -> float:
        """Returns the bounded swipe size calibrated from previous observed coordinate deltas."""

        ratio_unit_delta = state.get("horizontal_ratio_unit_delta" if axis == "x" else "vertical_ratio_unit_delta")
        if not isinstance(ratio_unit_delta, int | float) or ratio_unit_delta <= 0:
            return self.default_swipe_ratio
        estimated_ratio = abs(remaining_delta) / float(ratio_unit_delta)
        return max(self.min_swipe_ratio, min(self.max_swipe_ratio, estimated_ratio))


@dataclass(slots=True)
class HomeCityNavigator(SpatialSurfaceNavigator):
    """Plans camera-relative home-city search steps and visible city-object taps."""

    surface_type: SpatialSurfaceType = SpatialSurfaceType.HOME_CITY_SURFACE

    def plan_focus_object(
        self,
        observation: Observation,
        query: SpatialObjectQuery,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> list[ActionRequest]:
        """Plans one canonical home-city camera sweep until the requested object becomes visible."""

        surface = self.require_surface(observation)
        if surface.find_object(query) is not None:
            _clear_state(runtime_state, _HOME_CITY_NAVIGATION_STATE_KEY)
            return []
        state = _mutable_state(runtime_state, _HOME_CITY_NAVIGATION_STATE_KEY)
        query_signature = _query_signature(query)
        if state.get("query_signature") != query_signature:
            state.clear()
            state["query_signature"] = query_signature
            state["step_index"] = 0
        step_index = int(state.get("step_index", 0))
        scan_steps = _home_city_scan_steps()
        if step_index >= len(scan_steps):
            raise SelectorResolutionError(
                "Home-city navigation exhausted its canonical camera sweep pattern without finding the target object.",
                screen_type=observation.screen_type,
                surface_type=self.surface_type,
                query=query_signature,
            )
        state["step_index"] = step_index + 1
        return [scan_steps[step_index]]

    def tap_visible_object(
        self,
        observation: Observation,
        query: SpatialObjectQuery,
        *,
        reason: str,
        runtime_state: dict[str, Any] | None = None,
        observe_after: bool = True,
    ) -> list[ActionRequest]:
        """Returns one canonical tap against a visible home-city spatial object."""

        self.require_surface(observation).require_object(query)
        _clear_state(runtime_state, _HOME_CITY_NAVIGATION_STATE_KEY)
        return [
            TapSpatialObjectAction(
                query=query,
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
    """Returns a mutable nested mapping used by navigation calibration state."""

    value = state.get(key)
    if isinstance(value, dict):
        return value
    new_value: dict[str, int] = {}
    if isinstance(state, dict):
        state[key] = new_value
    return new_value


def _clear_state(runtime_state: dict[str, Any] | None, key: str) -> None:
    """Clears one navigation-state bucket when the requested target has been resolved."""

    if runtime_state is None:
        return
    runtime_state.pop(key, None)


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


def _home_city_scan_steps() -> tuple[SwipeAction, ...]:
    """Returns the canonical bounded camera sweep pattern for home-city search flows."""

    return (
        SwipeAction(
            direction="left",
            distance_ratio=0.45,
            duration_ms=350,
            reason="scan_home_city_left",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.75,
            start_y_ratio=0.58,
            end_x_ratio=0.25,
            end_y_ratio=0.58,
        ),
        SwipeAction(
            direction="right",
            distance_ratio=0.6,
            duration_ms=350,
            reason="scan_home_city_right",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.25,
            start_y_ratio=0.58,
            end_x_ratio=0.8,
            end_y_ratio=0.58,
        ),
        SwipeAction(
            direction="up",
            distance_ratio=0.38,
            duration_ms=350,
            reason="scan_home_city_up",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.55,
            start_y_ratio=0.7,
            end_x_ratio=0.55,
            end_y_ratio=0.35,
        ),
        SwipeAction(
            direction="down",
            distance_ratio=0.38,
            duration_ms=350,
            reason="scan_home_city_down",
            observe_after=True,
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
            start_x_ratio=0.55,
            start_y_ratio=0.35,
            end_x_ratio=0.55,
            end_y_ratio=0.7,
        ),
    )
