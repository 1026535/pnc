"""Synthetic fixtures owned by automation.session."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnc_automation.app.pnc.domain.action_requests import SwipeGesturePrimitive, SwipeInputSource



@dataclass
class FakeSession:
    """Captures action-executor calls without talking to ADB."""

    taps: list[tuple[int, int]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    key_events: list[str] = field(default_factory=list)
    launches: int = 0
    swipes: list[tuple[int, int, int, int, int]] = field(default_factory=list)
    swipe_input_sources: list[SwipeInputSource] = field(default_factory=list)
    swipe_gesture_primitives: list[SwipeGesturePrimitive] = field(default_factory=list)

    def tap_point(self, x: int, y: int) -> None:
        """Records one tap."""

        self.taps.append((x, y))

    def input_text(self, text: str) -> None:
        """Records one text input."""

        self.texts.append(text)

    def press_key(self, key_code: str) -> None:
        """Records one key event."""

        self.key_events.append(key_code)

    def launch_app(self) -> None:
        """Records one app launch request."""

        self.launches += 1

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        duration_ms: int = 300,
        input_source: str = SwipeInputSource.TOUCHSCREEN.value,
        gesture_primitive: str = SwipeGesturePrimitive.SWIPE.value,
    ) -> None:
        """Records one swipe gesture."""

        self.swipes.append((start_x, start_y, end_x, end_y, duration_ms))
        self.swipe_input_sources.append(SwipeInputSource(input_source))
        self.swipe_gesture_primitives.append(SwipeGesturePrimitive(gesture_primitive))
