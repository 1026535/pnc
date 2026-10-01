"""Synthetic fixtures owned by automation.session."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

from pnc_automation.core.errors import FrameProvenanceError
from pnc_automation.core.infra.emulator.input_dispatch import (
    SwipeDispatch,
    TapDispatch,
    WheelDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.infra.emulator.scroll_transport import SCROLL_TRANSPORT_NAME
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.app.pnc.domain.action_requests import SwipeGesturePrimitive, SwipeInputSource



@dataclass
class FakeSession:
    """Captures action-executor calls without talking to ADB."""

    taps: list[tuple[int, int]] = field(default_factory=list)
    tap_exact_geometry: list[bool] = field(default_factory=list)
    tap_safe_bounds: list[Bounds | None] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    key_events: list[str] = field(default_factory=list)
    launches: int = 0
    swipes: list[tuple[int, int, int, int, int]] = field(default_factory=list)
    swipe_input_sources: list[SwipeInputSource] = field(default_factory=list)
    swipe_gesture_primitives: list[SwipeGesturePrimitive] = field(default_factory=list)
    swipe_exact_geometry: list[bool] = field(default_factory=list)
    swipe_safe_bounds: list[Bounds | None] = field(default_factory=list)
    wheel_prepares: int = 0
    wheel_calls: list[tuple[int, int, int, tuple[int, int]]] = field(default_factory=list)
    wheel_prepare_error: Exception | None = None
    wheel_send_error: Exception | None = None
    swipe_error: Exception | None = None
    tap_error: Exception | None = None
    _input_sequence: int = field(default=0, init=False, repr=False)
    _consumed_frame_identity: tuple[str, int, int, int] | None = field(default=None, init=False, repr=False)

    @contextmanager
    def authorized_input(self, frame_ref: FrameRef):
        """Models one explicit frame authorization transaction for offline tests."""

        identity = (
            frame_ref.session_id,
            frame_ref.session_epoch,
            frame_ref.capture_sequence,
            frame_ref.input_sequence,
        )
        if self._consumed_frame_identity == identity:
            raise FrameProvenanceError("Synthetic frame proof was replayed.")
        self._consumed_frame_identity = identity
        yield

    def prepare_scroll_transport(self) -> None:
        """Records one bounded scroll transport preparation."""

        self.wheel_prepares += 1
        if self.wheel_prepare_error is not None:
            raise self.wheel_prepare_error

    def scroll_wheel(
        self,
        x: int,
        y: int,
        *,
        vertical_detent: int,
        frame_size: tuple[int, int],
    ) -> WheelDispatch:
        """Records one wheel dispatch."""

        self.wheel_calls.append((x, y, vertical_detent, frame_size))
        if self.wheel_send_error is not None:
            raise self.wheel_send_error
        self._input_sequence += 1
        return WheelDispatch(
            point=(x, y),
            frame_size=frame_size,
            vertical_detent=vertical_detent,
            transport=SCROLL_TRANSPORT_NAME,
            input_sequence=self._input_sequence,
        )

    def tap_point(
        self,
        x: int,
        y: int,
        *,
        exact_geometry: bool = False,
        safe_bounds: Bounds | None = None,
    ) -> TapDispatch:
        """Records one tap."""

        self.taps.append((x, y))
        self.tap_exact_geometry.append(exact_geometry)
        self.tap_safe_bounds.append(safe_bounds)
        if self.tap_error is not None:
            raise self.tap_error
        self._input_sequence += 1
        return TapDispatch(point=(x, y), input_sequence=self._input_sequence)

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
        exact_geometry: bool = False,
        safe_bounds: Bounds | None = None,
    ) -> SwipeDispatch:
        """Records one swipe gesture."""

        self.swipes.append((start_x, start_y, end_x, end_y, duration_ms))
        if self.swipe_error is not None:
            raise self.swipe_error
        self.swipe_input_sources.append(SwipeInputSource(input_source))
        self.swipe_gesture_primitives.append(SwipeGesturePrimitive(gesture_primitive))
        self.swipe_exact_geometry.append(exact_geometry)
        self.swipe_safe_bounds.append(safe_bounds)
        self._input_sequence += 1
        return SwipeDispatch(
            start=(start_x, start_y),
            end=(end_x, end_y),
            duration_ms=duration_ms,
            input_source=input_source,
            gesture_primitive=gesture_primitive,
            input_sequence=self._input_sequence,
        )
