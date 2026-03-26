"""Translates declarative actions into ADB-backed emulator interactions."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.chat import chat_channel_selector_id
from pnc_automation.pnc.mail import multiline_text_field_selector_ids
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
    TapSpatialObjectAction,
    WaitAction,
)
from pnc_automation.pnc.observation import (
    DetectedListEntry,
    DetectedSpatialObject,
    ListEntryKind,
    Observation,
    castle_names_match,
)
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
        executed_any_action = False
        for index, action in enumerate(actions):
            action_executed = self.execute_action(action, current_observation)
            executed_any_action = executed_any_action or action_executed
            if getattr(action, "observe_after", False) and action_executed:
                self._sleep_ms(self._observe_delay_ms_for(action))
                current_observation = observe(f"post_action_{index + 1}", action.follow_up_request)
                if not self.validate_follow_up(action, current_observation):
                    return current_observation
                observed_after_action = True
        if executed_any_action and not observed_after_action:
            self._sleep_ms(self.post_action_observe_delay_ms)
            return observe("post_actions", None)
        return current_observation

    def execute_action(self, action: ActionRequest, observation: Observation) -> bool:
        """Executes one declarative action and returns whether it changed emulator state."""

        self.logger.info("Executing action.", extra={"action_type": type(action).__name__, "screen_type": observation.screen_type})
        if isinstance(action, TapAction):
            element = observation.require(action.selector_id)
            target = element.action_point if element.action_point is not None else element.bounds.center()
            self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, TapPointAction):
            self.session.tap_point(action.x, action.y)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, TapListEntryAction):
            entry = self._require_entry(action, observation)
            target = entry.action_point if action.use_action_point and entry.action_point is not None else entry.bounds.center()
            self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, TapSpatialObjectAction):
            target = action.target_point
            if target is None:
                object_ = self._require_spatial_object(action, observation)
                target = (
                    object_.action_point
                    if action.use_action_point and object_.action_point is not None
                    else object_.bounds.center()
                )
            self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, SelectChatChannelAction):
            if observation.screen_type != ScreenType.PNC_CHAT:
                raise SelectorResolutionError(
                    "SelectChatChannelAction requires the shared chat screen.",
                    screen_type=observation.screen_type,
                )
            if observation.is_chat_channel_active(action.channel):
                return False
            element = observation.require(chat_channel_selector_id(action.channel))
            target = element.action_point if element.action_point is not None else element.bounds.center()
            self.session.tap_point(*target)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, InputTextAction):
            if action.selector_id is not None:
                element = observation.require(action.selector_id)
                x, y = element.action_point if element.action_point is not None else element.bounds.center()
                self.session.tap_point(x, y)
                self._sleep_ms(self._stable_delay_ms_for(action))
                self._clear_existing_text(action, observation)
            self._input_text(action, observation)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, KeyEventAction):
            self.session.press_key(action.key_code)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, WaitAction):
            self._sleep_ms(action.milliseconds)
            return True
        if isinstance(action, LaunchAppAction):
            self.session.launch_app()
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        if isinstance(action, SwipeAction):
            if observation.image_size is None:
                raise SelectorResolutionError("Swipe actions require the current screenshot dimensions.")
            width, height = observation.image_size
            start_x, start_y, end_x, end_y = _resolve_swipe_points_for_action(
                width=width,
                height=height,
                action=action,
            )
            self.session.swipe(start_x, start_y, end_x, end_y, duration_ms=action.duration_ms)
            self._sleep_ms(self._stable_delay_ms_for(action))
            return True
        raise SelectorResolutionError(f"Unsupported action type '{type(action).__name__}'.", action_type=type(action).__name__)

    def validate_follow_up(self, action: ActionRequest, observation: Observation) -> bool:
        """Returns whether the action sequence can safely continue from the observed follow-up state."""

        if isinstance(action, SelectChatChannelAction):
            if observation.blocking_popup or observation.screen_type in {
                ScreenType.PNC_POPUP,
                ScreenType.PNC_LOADING,
                ScreenType.UNKNOWN,
            }:
                return False
            if observation.screen_type != ScreenType.PNC_CHAT:
                return False
            if not observation.is_chat_channel_active(action.channel):
                return False
            if observation.chat_draft_empty is None:
                return False
            return True
        follow_up_request = getattr(action, "follow_up_request", None)
        if follow_up_request is None:
            return True
        return self._matches_follow_up_request(observation, follow_up_request)

    def _require_entry(self, action: TapListEntryAction, observation: Observation) -> DetectedListEntry:
        """Returns the matching list entry for one dynamic-entry tap."""

        for entry in observation.entries(action.entry_kind):
            if action.title_text is not None and not self._entry_title_matches(action=action, entry=entry):
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

    def _entry_title_matches(self, *, action: TapListEntryAction, entry: DetectedListEntry) -> bool:
        """Returns whether one observed list-entry title satisfies the tap request."""

        if action.title_text is None:
            return True
        if entry.title_text is None:
            return False
        if action.entry_kind == ListEntryKind.CASTLE:
            return castle_names_match(entry.title_text, action.title_text)
        return entry.title_text == action.title_text

    def _require_spatial_object(self, action: TapSpatialObjectAction, observation: Observation) -> DetectedSpatialObject:
        """Returns the matching visible spatial object for one spatial-object tap."""

        if action.query is None:
            raise SelectorResolutionError("TapSpatialObjectAction requires a semantic spatial-object query.")
        return observation.require_spatial_object(action.query)

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
        field_state = observation.text_field_state(action.selector_id)
        if field_state is None:
            if action.selector_id == UiElementId.PNC_CHAT_INPUT_FIELD and observation.chat_draft_empty is not None:
                if observation.chat_draft_empty:
                    return
                delete_budget = _delete_budget(observation.chat_draft_text)
                self.session.press_key("KEYCODE_MOVE_END")
                for _ in range(delete_budget):
                    self.session.press_key("KEYCODE_DEL")
                self._sleep_ms(self._stable_delay_ms_for(action))
                return
            raise SelectorResolutionError(
                "Observed text-field state is required before replacing existing text.",
                selector_id=action.selector_id,
                screen_type=observation.screen_type,
            )
        if field_state.empty:
            return
        self.session.press_key("KEYCODE_MOVE_END")
        for _ in range(_delete_budget(field_state.text)):
            self.session.press_key("KEYCODE_DEL")
        self._sleep_ms(self._stable_delay_ms_for(action))

    def _input_text(self, action: InputTextAction, observation: Observation) -> None:
        """Inputs text through the shared single-line or multiline field policy."""

        if "\n" not in action.text and "\r" not in action.text:
            self.session.input_text(action.text)
            return
        if action.selector_id is None:
            raise SelectorResolutionError("Multiline text entry requires a selector-backed field.", text=action.text)
        if action.selector_id not in multiline_text_field_selector_ids():
            raise SelectorResolutionError(
                "The requested selector does not support multiline text entry.",
                selector_id=action.selector_id,
                screen_type=observation.screen_type,
            )
        normalized_lines = action.text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for index, line in enumerate(normalized_lines):
            self.session.input_text(line)
            if index == len(normalized_lines) - 1:
                continue
            self.session.press_key("KEYCODE_ENTER")

    def _matches_follow_up_request(
        self,
        observation: Observation,
        request: ObservationRequest,
    ) -> bool:
        """Returns whether one observed follow-up landed on a usable screen for the remaining action sequence."""

        if observation.blocking_popup or observation.screen_type in {
            ScreenType.PNC_POPUP,
            ScreenType.PNC_LOADING,
            ScreenType.UNKNOWN,
        }:
            return False
        if not request.candidate_screen_types:
            return True
        return observation.screen_type in request.candidate_screen_types


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


def _resolve_swipe_points_for_action(*, width: int, height: int, action: SwipeAction) -> tuple[int, int, int, int]:
    """Returns explicit swipe coordinates when provided, otherwise uses directional screen-relative swipes."""

    explicit_ratios = (
        action.start_x_ratio,
        action.start_y_ratio,
        action.end_x_ratio,
        action.end_y_ratio,
    )
    if all(ratio is None for ratio in explicit_ratios):
        return _resolve_swipe_points(
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


def _validate_swipe_ratio(ratio: float, *, field_name: str) -> None:
    """Rejects explicit swipe ratios that fall outside normalized screen bounds."""

    if not 0 <= ratio <= 1:
        raise SelectorResolutionError(
            "Explicit swipe ratios must be within [0, 1].",
            field_name=field_name,
            ratio=ratio,
        )


def _delete_budget(draft_text: str | None) -> int:
    """Returns a conservative delete count for one observed reusable text field."""

    if draft_text is None or draft_text.strip() == "":
        return 36
    return max(len(draft_text) + 8, 24)
