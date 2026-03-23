"""Declarative GUI action requests emitted by tasks and flows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.pnc.chat import ChatChannel
from pnc_automation.pnc.observation import ListEntryKind, SpatialObjectQuery
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_request import ObservationRequest


class ActionTimingProfile(StrEnum):
    """Identifies the pacing profile applied by the low-level action executor."""

    DEFAULT = "default"
    CHAT = "chat"


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
    """Taps one visible spatial object resolved from the current observation."""

    query: SpatialObjectQuery | None = None
    use_action_point: bool = True


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
    start_x_ratio: float | None = None
    start_y_ratio: float | None = None
    end_x_ratio: float | None = None
    end_y_ratio: float | None = None
