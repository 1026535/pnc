"""Declarative GUI action requests emitted by tasks and flows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import ListEntryKind, SpatialObjectQuery
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest


class ActionTimingProfile(StrEnum):
    """Identifies the pacing profile applied by the low-level action executor."""

    DEFAULT = "default"
    CHAT = "chat"
    WORLD_MAP_MOVEMENT = "world_map_movement"


class SwipeInputSource(StrEnum):
    """Identifies which Android input entry point should emit one swipe gesture."""

    DEFAULT = "default"
    TOUCHSCREEN = "touchscreen"


class SwipeGesturePrimitive(StrEnum):
    """Identifies which low-level Android gesture primitive should realize one swipe-like drag."""

    SWIPE = "swipe"
    PRESS_MOVE_RELEASE = "press_move_release"


@dataclass(frozen=True, slots=True)
class ActionRequest:
    """Base metadata shared by all declarative actions."""

    reason: str = ""
    observe_after: bool = False
    follow_up_request: ObservationRequest | None = None
    timing_profile: ActionTimingProfile = ActionTimingProfile.DEFAULT


@dataclass(frozen=True, slots=True)
class TapAction(ActionRequest):
    """Taps the center of one visible selector."""

    selector_id: UiElementId = UiElementId.PNC_BOTTOM_NAV_HOME


@dataclass(frozen=True, slots=True)
class TapPointAction(ActionRequest):
    """Taps one explicit screen coordinate."""

    x: int = 0
    y: int = 0


@dataclass(frozen=True, slots=True)
class TapListEntryAction(ActionRequest):
    """Taps a dynamic list entry resolved from the current observation."""

    entry_kind: ListEntryKind = ListEntryKind.CASTLE
    title_text: str | None = None
    metadata_key: str | None = None
    metadata_value: str | int | bool | None = None
    selected: bool | None = None
    use_action_point: bool = False


@dataclass(frozen=True, slots=True)
class TapSpatialObjectAction(ActionRequest):
    """Taps one visible spatial object, preferably using the exact target captured during planning."""

    query: SpatialObjectQuery | None = None
    target_point: tuple[int, int] | None = None
    use_action_point: bool = True

    def __post_init__(self) -> None:
        """Rejects empty or malformed spatial tap requests before execution begins."""

        if self.query is None and self.target_point is None:
            raise SelectorResolutionError("TapSpatialObjectAction requires either a query or a concrete target_point.")
        if self.target_point is not None and (
            not isinstance(self.target_point, tuple)
            or len(self.target_point) != 2
            or not isinstance(self.target_point[0], int)
            or not isinstance(self.target_point[1], int)
        ):
            raise SelectorResolutionError(
                "TapSpatialObjectAction target_point must be one integer coordinate pair.",
                target_point=self.target_point,
            )


@dataclass(frozen=True, slots=True)
class InputTextAction(ActionRequest):
    """Inputs text, optionally after focusing a selector-backed field."""

    text: str = ""
    selector_id: UiElementId | None = None
    replace_existing: bool = False


@dataclass(frozen=True, slots=True)
class SelectChatChannelAction(ActionRequest):
    """Activates one chat tab, skipping the tap when that channel is already active."""

    channel: ChatChannel = ChatChannel.WORLD


@dataclass(frozen=True, slots=True)
class KeyEventAction(ActionRequest):
    """Sends one Android key code."""

    key_code: str = "KEYCODE_BACK"


@dataclass(frozen=True, slots=True)
class WaitAction(ActionRequest):
    """Waits for a fixed stabilization period."""

    milliseconds: int = 0


@dataclass(frozen=True, slots=True)
class LaunchAppAction(ActionRequest):
    """Launches or foregrounds the configured P&C package."""

    pass


@dataclass(frozen=True, slots=True)
class SwipeAction(ActionRequest):
    """Performs one directional swipe across the current screen."""

    direction: str = "up"
    distance_ratio: float = 0.5
    duration_ms: int = 300
    input_source: SwipeInputSource = SwipeInputSource.TOUCHSCREEN
    gesture_primitive: SwipeGesturePrimitive = SwipeGesturePrimitive.SWIPE
    start_x_ratio: float | None = None
    start_y_ratio: float | None = None
    end_x_ratio: float | None = None
    end_y_ratio: float | None = None


def resolve_swipe_points_for_action(*, width: int, height: int, action: SwipeAction) -> tuple[int, int, int, int]:
    """Returns the exact swipe coordinates implied by one action using the canonical shared geometry rules."""

    explicit_ratios = (
        action.start_x_ratio,
        action.start_y_ratio,
        action.end_x_ratio,
        action.end_y_ratio,
    )
    if all(ratio is None for ratio in explicit_ratios):
        return _resolve_directional_swipe_points(
            width=width,
            height=height,
            direction=action.direction,
            distance_ratio=action.distance_ratio,
        )
    if any(ratio is None for ratio in explicit_ratios):
        raise SelectorResolutionError("Explicit swipe ratios require all start/end ratios to be provided together.")
    start_x_ratio, start_y_ratio, end_x_ratio, end_y_ratio = explicit_ratios
    assert start_x_ratio is not None and start_y_ratio is not None and end_x_ratio is not None and end_y_ratio is not None
    _validate_swipe_ratio(start_x_ratio, field_name="start_x_ratio")
    _validate_swipe_ratio(start_y_ratio, field_name="start_y_ratio")
    _validate_swipe_ratio(end_x_ratio, field_name="end_x_ratio")
    _validate_swipe_ratio(end_y_ratio, field_name="end_y_ratio")
    return (
        int(width * start_x_ratio),
        int(height * start_y_ratio),
        int(width * end_x_ratio),
        int(height * end_y_ratio),
    )


def _resolve_directional_swipe_points(*, width: int, height: int, direction: str, distance_ratio: float) -> tuple[int, int, int, int]:
    """Converts one directional swipe request into screen-relative coordinates."""

    if not 0 < distance_ratio <= 1:
        raise SelectorResolutionError("Swipe distance_ratio must be within (0, 1].", distance_ratio=distance_ratio)
    center_x = width // 2
    center_y = height // 2
    horizontal_distance = int((width * distance_ratio) / 2)
    vertical_distance = int((height * distance_ratio) / 2)
    if direction == "up":
        return center_x, center_y + vertical_distance, center_x, center_y - vertical_distance
    if direction == "down":
        return center_x, center_y - vertical_distance, center_x, center_y + vertical_distance
    if direction == "left":
        return center_x + horizontal_distance, center_y, center_x - horizontal_distance, center_y
    if direction == "right":
        return center_x - horizontal_distance, center_y, center_x + horizontal_distance, center_y
    raise SelectorResolutionError("Unsupported swipe direction.", direction=direction)


def _validate_swipe_ratio(ratio: float, *, field_name: str) -> None:
    """Rejects explicit swipe ratios that fall outside normalized screen bounds."""

    if not 0 <= ratio <= 1:
        raise SelectorResolutionError(
            "Explicit swipe ratios must be within [0, 1].",
            field_name=field_name,
            ratio=ratio,
        )
