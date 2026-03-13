"""Translates declarative actions into ADB-backed emulator interactions."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.chat import chat_channel_selector_id
from pnc_automation.pnc.action_requests import (
    ActionRequest,
    ActionTimingProfile,
    InputTextAction,
    KeyEventAction,
    LaunchAppAction,
    SelectChatChannelAction,
    SwipeAction,
    TapAction,
    TapListEntryAction,
    TapPointAction,
    WaitAction,
)
from pnc_automation.pnc.observation import DetectedListEntry, Observation
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_request import ObservationRequest


@dataclass(slots=True)
class ActionExecutor:
    """Executes action requests against one emulator session."""

    session: BlueStacksSession
    stable_click_delay_ms: int
    post_action_observe_delay_ms: int
    chat_stable_click_delay_ms: int
    chat_post_action_observe_delay_ms: int
    logger: logging.LoggerAdapter
    sleep: Callable[[float], None] = time.sleep

    def execute_actions(
        self,
        actions: Sequence[ActionRequest],
        initial_observation: Observation,
        *,
        observe: Callable[[str, ObservationRequest | None], Observation],
    ) -> Observation:
        """Executes the action sequence and returns the freshest observation."""

        current_observation = initial_observation
        observed_after_action = False
        for index, action in enumerate(actions):
            self.execute_action(action, current_observation)
            if getattr(action, "observe_after", False):
                self._sleep_ms(self._observe_delay_ms_for(action))
                current_observation = observe(f"post_action_{index + 1}", action.follow_up_request)
                observed_after_action = True
        if actions and not observed_after_action:
            self._sleep_ms(self.post_action_observe_delay_ms)
            return observe("post_actions", None)
        return current_observation

    def execute_action(self, action: ActionRequest, observation: Observation) -> None:
        """Executes one declarative action against the current observation."""

        self.logger.info("Executing action.", extra={"action_type": type(action).__name__, "screen_type": observation.screen_type})
        if isinstance(action, TapAction):
            element = observation.require(action.selector_id)
            target = element.action_point if element.action_point is not None else element.bounds.center()
            self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return
        if isinstance(action, TapPointAction):
            self.session.tap_point(action.x, action.y)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return
        if isinstance(action, TapListEntryAction):
            entry = self._require_entry(action, observation)
            target = entry.action_point if action.use_action_point and entry.action_point is not None else entry.bounds.center()
            self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return
        if isinstance(action, SelectChatChannelAction):
            if observation.screen_type != ScreenType.PNC_CHAT:
                raise SelectorResolutionError(
                    "SelectChatChannelAction requires the shared chat screen.",
                    screen_type=observation.screen_type,
                )
            if observation.is_chat_channel_active(action.channel):
                return
            element = observation.require(chat_channel_selector_id(action.channel))
            target = element.action_point if element.action_point is not None else element.bounds.center()
            self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return
        if isinstance(action, InputTextAction):
            if action.selector_id is not None:
                element = observation.require(action.selector_id)
                x, y = element.action_point if element.action_point is not None else element.bounds.center()
                self.session.tap_point(x, y)
                self._sleep_ms(self._stable_delay_ms_for(action))
                self._clear_existing_text(action, observation)
            self.session.input_text(action.text)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return
        if isinstance(action, KeyEventAction):
            self.session.press_key(action.key_code)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return
        if isinstance(action, WaitAction):
            self._sleep_ms(action.milliseconds)
            return
        if isinstance(action, LaunchAppAction):
            self.session.launch_app()
            self._sleep_ms(self._stable_delay_ms_for(action))
            return
        if isinstance(action, SwipeAction):
            if observation.image_size is None:
                raise SelectorResolutionError("Swipe actions require the current screenshot dimensions.")
            width, height = observation.image_size
            start_x, start_y, end_x, end_y = _resolve_swipe_points(
                width=width,
                height=height,
                direction=action.direction,
                distance_ratio=action.distance_ratio,
            )
            self.session.swipe(start_x, start_y, end_x, end_y, duration_ms=action.duration_ms)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return
        raise SelectorResolutionError(f"Unsupported action type '{type(action).__name__}'.", action_type=type(action).__name__)

    def _require_entry(self, action: TapListEntryAction, observation: Observation) -> DetectedListEntry:
        """Returns the matching list entry for one dynamic-entry tap."""

        for entry in observation.entries(action.entry_kind):
            if action.title_text is not None and entry.title_text != action.title_text:
                continue
            if action.metadata_key is not None and entry.metadata.get(action.metadata_key) != action.metadata_value:
                continue
            if action.selected is not None and entry.selected != action.selected:
                continue
            return entry
        raise SelectorResolutionError(
            "Could not resolve the requested list entry tap target.",
            entry_kind=action.entry_kind,
            title_text=action.title_text,
            metadata_key=action.metadata_key,
            metadata_value=action.metadata_value,
        )

    def _sleep_ms(self, milliseconds: int) -> None:
        """Sleeps using millisecond units for action pacing."""

        if milliseconds <= 0:
            return
        self.sleep(milliseconds / 1000.0)

    def _stable_delay_ms_for(self, action: ActionRequest) -> int:
        """Returns the pacing delay applied after one concrete UI action."""

        if action.timing_profile == ActionTimingProfile.CHAT:
            return self.chat_stable_click_delay_ms
        return self.stable_click_delay_ms

    def _observe_delay_ms_for(self, action: ActionRequest) -> int:
        """Returns the delay applied before one observe-after capture."""

        if action.timing_profile == ActionTimingProfile.CHAT:
            return self.chat_post_action_observe_delay_ms
        return self.post_action_observe_delay_ms

    def _clear_existing_text(self, action: InputTextAction, observation: Observation) -> None:
        """Clears one selector-backed draft when the action requests replace-in-place input."""

        if not action.replace_existing:
            return
        if action.selector_id is None:
            raise SelectorResolutionError("InputTextAction.replace_existing requires a selector-backed field.")
        if action.selector_id != UiElementId.PNC_CHAT_INPUT_FIELD:
            raise SelectorResolutionError(
                "InputTextAction.replace_existing is only implemented for the shared chat input field.",
                selector_id=action.selector_id,
            )
        if observation.chat_draft_empty is None:
            raise SelectorResolutionError(
                "Chat draft state must be observed before typing into the shared chat input field.",
                selector_id=action.selector_id,
                screen_type=observation.screen_type,
            )
        if observation.chat_draft_empty:
            return
        self.session.press_key("KEYCODE_MOVE_END")
        for _ in range(_chat_delete_budget(observation.chat_draft_text)):
            self.session.press_key("KEYCODE_DEL")
        self._sleep_ms(self._stable_delay_ms_for(action))


def _resolve_swipe_points(*, width: int, height: int, direction: str, distance_ratio: float) -> tuple[int, int, int, int]:
    """Converts a directional swipe into screen-relative coordinates."""

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


def _chat_delete_budget(draft_text: str | None) -> int:
    """Returns a conservative delete count for the observed reusable chat draft."""

    if draft_text is None or draft_text.strip() == "":
        return 36
    return max(len(draft_text) + 8, 24)
