"""BlueStacks-specific device and app control built on top of ADB."""

from __future__ import annotations

import math
import random
import re
import shlex
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from functools import wraps
from threading import RLock
from typing import Protocol
from uuid import uuid4

from pnc_automation.core.infra.adb.client import AdbClient
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.bluestacks_management.instance_lease import (
    PROCESS_INSTANCE_LEASES,
    InstanceLeaseRegistry,
    ProcessInstanceLease,
)
from pnc_automation.core.config.host import BlueStacksCapabilities
from pnc_automation.core.errors import (
    DeviceConnectionError,
    FrameProvenanceError,
    GameLaunchError,
    ScreenshotCaptureError,
)
from pnc_automation.core.infra.emulator.input_dispatch import (
    SwipeDispatch,
    TapDispatch,
    WheelDispatch,
)
from pnc_automation.core.infra.emulator.provenance import CapturedFrame, FrameRef
from pnc_automation.core.infra.emulator.scroll_transport import (
    SCROLL_TRANSPORT_NAME,
    ScrcpyControlTransport,
    build_scroll_packet,
    require_native_display_mapping,
)
from pnc_automation.core.lifecycle import close_preserving_error
from pnc_automation.core.vision.image.models import Bounds


def _input_dispatch(function: Callable[..., object]) -> Callable[..., object]:
    """Serializes one entire ADB input call with capture provenance state."""

    @wraps(function)
    def wrapped(session: BlueStacksSession, *args: object, **kwargs: object) -> object:
        with session._provenance_lock:
            session._input_sequence += 1
            return function(session, *args, **kwargs)

    return wrapped


DEFAULT_BLUESTACKS_SHUTDOWN_GRACE_SECONDS = 120.0
_app_foreground_attempts = 30
_app_foreground_retry_delay_seconds = 2.0
_input_letter_delay_seconds_range = (0.03, 0.08)
_input_letter_delay_distance_seconds = 0.10
_input_letter_same_finger_seconds = 0.05
_input_word_delay_seconds_range = (0.20, 0.28)


class BlueStacksSessionCleanupMode(StrEnum):
    """Controls whether a connected session may close its host instance."""

    KEEP_WARM = "keep_warm"
    CLOSE_AT_PHASE_END = "close_at_phase_end"


@dataclass(frozen=True, slots=True)
class BlueStacksSessionCleanupPolicy:
    """Keeps short sessions warm until the active agent ends a live-testing phase."""

    mode: BlueStacksSessionCleanupMode = BlueStacksSessionCleanupMode.KEEP_WARM
    close_preexisting_instance: bool = False
    shutdown_grace_seconds: float = DEFAULT_BLUESTACKS_SHUTDOWN_GRACE_SECONDS

    def __post_init__(self) -> None:
        """Rejects an invalid phase-end quiescence window."""

        if (
            isinstance(self.shutdown_grace_seconds, bool)
            or not isinstance(self.shutdown_grace_seconds, (int, float))
            or not math.isfinite(float(self.shutdown_grace_seconds))
            or self.shutdown_grace_seconds < 0
        ):
            raise ValueError("BlueStacks shutdown grace seconds must be finite and non-negative.")

    @classmethod
    def keep_warm(cls) -> "BlueStacksSessionCleanupPolicy":
        """Returns the default policy for short or interactive work."""

        return cls()

    @classmethod
    def close_at_phase_end(
        cls,
        *,
        close_preexisting_instance: bool = False,
        shutdown_grace_seconds: float = DEFAULT_BLUESTACKS_SHUTDOWN_GRACE_SECONDS,
    ) -> "BlueStacksSessionCleanupPolicy":
        """Returns the live-test policy that closes when the caller ends its phase."""

        return cls(
            mode=BlueStacksSessionCleanupMode.CLOSE_AT_PHASE_END,
            close_preexisting_instance=close_preexisting_instance,
            shutdown_grace_seconds=shutdown_grace_seconds,
        )

    def should_close(self, *, instance: BlueStacksInstance) -> bool:
        """Returns whether the session may request host shutdown."""

        if self.mode is not BlueStacksSessionCleanupMode.CLOSE_AT_PHASE_END:
            return False
        return instance.started_by_resolver or self.close_preexisting_instance


class BlueStacksInstanceCloser(Protocol):
    """Persists and executes lifecycle cleanup for one resolved process."""

    def register_close_intent(
        self,
        instance: BlueStacksInstance,
        *,
        grace_period_seconds: float,
    ) -> str:
        """Persists cleanup intent before live work begins."""

    def cancel_close_intent(self, instance: BlueStacksInstance) -> None:
        """Cancels pending cleanup when new keep-warm work claims the instance."""

    def finalize_close_intent(self, instance: BlueStacksInstance, *, intent_id: str) -> None:
        """Waits for quiescence, then reclaims and revalidates before shutdown."""


@dataclass(slots=True)
class BlueStacksSession:
    """Owns one connected emulator session and app-level control primitives."""

    adb_client: AdbClient
    instance: BlueStacksInstance
    sleep: Callable[[float], None] = time.sleep
    connect_attempts: int = 30
    connect_retry_delay_seconds: float = 2.0
    lease_registry: InstanceLeaseRegistry = field(
        default_factory=lambda: PROCESS_INSTANCE_LEASES,
        repr=False,
    )
    capabilities: BlueStacksCapabilities = field(
        default_factory=BlueStacksCapabilities.unrestricted,
        repr=False,
    )
    cleanup_policy: BlueStacksSessionCleanupPolicy = field(default_factory=BlueStacksSessionCleanupPolicy.keep_warm)
    instance_closer: BlueStacksInstanceCloser | None = field(default=None, repr=False)
    instance_lease: ProcessInstanceLease | None = field(default=None, repr=False)
    provenance_max_age_seconds: float = 30.0
    rng: random.Random = field(default_factory=random.Random, repr=False)
    input_jitter_px: float = 4.0
    scroll_transport_factory: Callable[[BlueStacksSession], ScrcpyControlTransport] | None = field(
        default=None,
        repr=False,
    )
    _instance_lease: ProcessInstanceLease | None = field(default=None, init=False, repr=False)
    _cleanup_intent_registered: bool = field(default=False, init=False, repr=False)
    _cleanup_intent_id: str | None = field(default=None, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _session_id: str = field(default_factory=lambda: uuid4().hex, init=False, repr=False)
    _session_epoch: int = field(default=0, init=False, repr=False)
    _capture_sequence: int = field(default=0, init=False, repr=False)
    _input_sequence: int = field(default=0, init=False, repr=False)
    _latest_frame: FrameRef | None = field(default=None, init=False, repr=False)
    _consumed_frame: tuple[str, int, int, int] | None = field(default=None, init=False, repr=False)
    _authorizing_frame: FrameRef | None = field(default=None, init=False, repr=False)
    _provenance_lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _scroll_transport: ScrcpyControlTransport | None = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        """Connects to the configured ADB endpoint and validates device readiness."""

        self._ensure_lease()
        self._ensure_cleanup_intent()
        try:
            attempts = max(1, self.connect_attempts)
            last_connect_result = None
            last_state_result = None
            for attempt_index in range(attempts):
                last_connect_result = self.adb_client.connect(self.instance.device_id)
                if last_connect_result.succeeded:
                    last_state_result = self.adb_client.get_state(self.instance.device_id)
                    if last_state_result.succeeded and last_state_result.stdout_text.strip() == "device":
                        self._start_session_epoch()
                        return
                if attempt_index < attempts - 1 and self.connect_retry_delay_seconds > 0:
                    self.sleep(self.connect_retry_delay_seconds)
            if last_connect_result is not None and not last_connect_result.succeeded:
                raise DeviceConnectionError(
                    f"Failed to connect to device '{self.instance.device_id}'.",
                    device_id=self.instance.device_id,
                    stderr=last_connect_result.stderr_text,
                )
            raise DeviceConnectionError(
                f"Device '{self.instance.device_id}' is not ready.",
                device_id=self.instance.device_id,
                stdout="" if last_state_result is None else last_state_result.stdout_text,
                stderr="" if last_state_result is None else last_state_result.stderr_text,
            )
        except BaseException as error:
            close_preserving_error(
                self.close,
                error,
                message="BlueStacks connection and phase cleanup both failed.",
            )
            raise

    def ensure_responsive(self) -> None:
        """Ensures the Android session responds to a trivial shell command."""

        self._ensure_lease()
        attempts = max(1, self.connect_attempts)
        last_result = None
        for attempt_index in range(attempts):
            last_result = self.adb_client.shell(self.instance.device_id, "getprop", "ro.product.model")
            if last_result.succeeded and last_result.stdout_text.strip() != "":
                return
            if attempt_index < attempts - 1 and self.connect_retry_delay_seconds > 0:
                self.sleep(self.connect_retry_delay_seconds)
        raise DeviceConnectionError(
            f"Device '{self.instance.device_id}' did not respond to a readiness check.",
            device_id=self.instance.device_id,
            stdout="" if last_result is None else last_result.stdout_text,
            stderr="" if last_result is None else last_result.stderr_text,
        )

    def is_app_foregrounded(self) -> bool:
        """Reads foreground focus after a bounded wait for Android's window service."""

        self._ensure_lease()
        attempts = max(1, self.connect_attempts)
        for attempt_index in range(attempts):
            result = self.adb_client.shell(self.instance.device_id, "dumpsys", "window")
            # ADB can respond before system services start; dumpsys even exits zero.
            # Retry that observed boot state, never malformed or ambiguous focus data.
            if result.stderr_text.strip() == "Can't find service: window":
                if attempt_index < attempts - 1 and self.connect_retry_delay_seconds > 0:
                    self.sleep(self.connect_retry_delay_seconds)
                continue
            if not result.succeeded:
                raise GameLaunchError(
                    f"Failed to determine foreground app for '{self.instance.device_id}'.",
                    device_id=self.instance.device_id,
                    stderr=result.stderr_text,
                )
            current_focus_package = _parse_current_focus_package(
                result.stdout_text,
                device_id=self.instance.device_id,
            )
            return current_focus_package == self.instance.app_package
        raise GameLaunchError(
            f"Android window service did not become ready on '{self.instance.device_id}'.",
            device_id=self.instance.device_id,
            attempts=attempts,
            stdout=result.stdout_text,
            stderr=result.stderr_text,
        )

    def ensure_app_foregrounded(self) -> bool:
        """Launches the game when needed and waits for its package to take focus."""

        if self.is_app_foregrounded():
            return False
        self._require_app_launch()
        self.launch_app()
        self._wait_for_app_foreground()
        return True

    def _wait_for_app_foreground(self) -> None:
        """Waits through launcher or store startup before a caller captures the game."""

        attempts = max(1, _app_foreground_attempts)
        for attempt_index in range(attempts):
            if self.is_app_foregrounded():
                return
            if attempt_index < attempts - 1 and _app_foreground_retry_delay_seconds > 0:
                self.sleep(_app_foreground_retry_delay_seconds)
        raise GameLaunchError(
            f"Timed out waiting for package '{self.instance.app_package}' to take foreground focus.",
            package=self.instance.app_package,
            device_id=self.instance.device_id,
        )

    @_input_dispatch
    def launch_app(self) -> None:
        """Launches the configured Puzzles & Conquest package."""

        self._ensure_lease()
        self._require_app_launch()
        result = self.adb_client.shell(
            self.instance.device_id,
            "monkey",
            "-p",
            self.instance.app_package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
            timeout_seconds=20,
        )
        if not result.succeeded:
            raise GameLaunchError(
                f"Failed to foreground package '{self.instance.app_package}'.",
                package=self.instance.app_package,
                stderr=result.stderr_text,
            )

    def _jitter_point(self, x: int, y: int) -> tuple[int, int]:
        """Offsets one point within `input_jitter_px`, mimicking finger contact-area spread."""

        if self.input_jitter_px <= 0:
            return x, y
        magnitude = self.input_jitter_px
        return (
            max(0, round(x + self.rng.triangular(-magnitude, magnitude))),
            max(0, round(y + self.rng.triangular(-magnitude, magnitude))),
        )

    def _jitter_duration_ms(self, duration_ms: int) -> int:
        """Varies one gesture duration by up to 15 percent when jitter is enabled."""

        if self.input_jitter_px <= 0:
            return duration_ms
        return max(0, round(duration_ms * self.rng.uniform(0.85, 1.15)))

    @_input_dispatch
    def tap_point(
        self,
        x: int,
        y: int,
        *,
        exact_geometry: bool = False,
        safe_bounds: Bounds | None = None,
    ) -> TapDispatch:
        """Sends one screen tap to the device and returns its actual dispatch."""

        self._require_input()
        if not exact_geometry:
            x, y = self._jitter_point(x, y)
        _require_point_in_safe_bounds(
            (x, y),
            safe_bounds=safe_bounds,
            primitive="tap",
            device_id=self.instance.device_id,
        )
        result = self.adb_client.shell(self.instance.device_id, "input", "tap", str(x), str(y))
        if not result.succeeded:
            raise DeviceConnectionError(
                f"Failed to tap point ({x}, {y}).",
                device_id=self.instance.device_id,
                x=x,
                y=y,
                stderr=result.stderr_text,
            )
        return TapDispatch(point=(x, y), input_sequence=self._input_sequence)

    @_input_dispatch
    def input_text(self, text: str) -> None:
        """Inputs one text payload using Android's input subsystem.

        With input jitter enabled the payload is typed one character at a
        time, with a keystroke cadence shaped by word boundaries, QWERTY
        key distance, and same-finger transitions instead of one burst.
        """

        self._require_input()
        _encode_adb_text(text)  # Validates the whole payload before any character is sent.
        chunks = tuple(text) if self.input_jitter_px > 0 and len(text) > 1 else (text,)
        for index, chunk in enumerate(chunks):
            encoded = _encode_adb_text(chunk)
            result = self.adb_client.shell(self.instance.device_id, "input", "text", encoded)
            if not result.succeeded:
                raise DeviceConnectionError(
                    "Failed to input text through ADB.",
                    device_id=self.instance.device_id,
                    chunk_index=index,
                    stderr=result.stderr_text,
                )
            if index < len(chunks) - 1:
                self.sleep(_type_delay_seconds(chunk, chunks[index + 1], rng=self.rng))

    @_input_dispatch
    def press_key(self, key_code: str) -> None:
        """Sends one Android key event."""

        self._require_input()
        result = self.adb_client.shell(self.instance.device_id, "input", "keyevent", key_code)
        if not result.succeeded:
            raise DeviceConnectionError(
                f"Failed to send key event '{key_code}'.",
                device_id=self.instance.device_id,
                key_code=key_code,
                stderr=result.stderr_text,
            )

    @_input_dispatch
    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        duration_ms: int = 300,
        input_source: str = "touchscreen",
        gesture_primitive: str = "swipe",
        exact_geometry: bool = False,
        safe_bounds: Bounds | None = None,
    ) -> SwipeDispatch:
        """Sends one swipe-like drag and returns its actual post-jitter dispatch.

        With ``exact_geometry=True`` the resolved endpoints and duration are sent
        exactly: no jitter and no eased path drift for motion-event gestures.
        """

        self._require_input()
        if not exact_geometry:
            start_x, start_y = self._jitter_point(start_x, start_y)
            end_x, end_y = self._jitter_point(end_x, end_y)
            duration_ms = self._jitter_duration_ms(duration_ms)
        _require_point_in_safe_bounds(
            (start_x, start_y),
            safe_bounds=safe_bounds,
            primitive="swipe start",
            device_id=self.instance.device_id,
        )
        _require_point_in_safe_bounds(
            (end_x, end_y),
            safe_bounds=safe_bounds,
            primitive="swipe end",
            device_id=self.instance.device_id,
        )
        if gesture_primitive == "swipe":
            command = [
                *_input_command_prefix(input_source=input_source, device_id=self.instance.device_id),
                "swipe",
                str(start_x),
                str(start_y),
                str(end_x),
                str(end_y),
                str(duration_ms),
            ]
            result = self.adb_client.shell(
                self.instance.device_id,
                *command,
            )
            if not result.succeeded:
                raise DeviceConnectionError(
                    "Failed to send swipe gesture.",
                    device_id=self.instance.device_id,
                    stderr=result.stderr_text,
                    gesture_primitive=gesture_primitive,
                )
        elif gesture_primitive == "press_move_release":
            motion_event_prefix = [*_input_command_prefix(input_source=input_source, device_id=self.instance.device_id), "motionevent"]
            timeline = _motion_event_drag_timeline(
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
                duration_ms=duration_ms,
                rng=self.rng,
                jitter_px=0.0 if exact_geometry else self.input_jitter_px,
            )
            for index, (event_name, x, y, delay_seconds) in enumerate(timeline):
                result = self.adb_client.shell(
                    self.instance.device_id,
                    *motion_event_prefix,
                    event_name,
                    str(x),
                    str(y),
                )
                if not result.succeeded:
                    raise DeviceConnectionError(
                        "Failed to send press-move-release gesture.",
                        device_id=self.instance.device_id,
                        stderr=result.stderr_text,
                        gesture_primitive=gesture_primitive,
                        event_name=event_name,
                        event_index=index,
                    )
                if delay_seconds > 0:
                    self.sleep(delay_seconds)
        else:
            raise DeviceConnectionError(
                "Unsupported swipe gesture primitive.",
                device_id=self.instance.device_id,
                gesture_primitive=gesture_primitive,
            )
        return SwipeDispatch(
            start=(start_x, start_y),
            end=(end_x, end_y),
            duration_ms=duration_ms,
            input_source=input_source,
            gesture_primitive=gesture_primitive,
            input_sequence=self._input_sequence,
        )

    def prepare_scroll_transport(self) -> None:
        """Prepares the lazily owned scroll transport without sending any input.

        Preparation performs the bounded transport setup outside the provenance
        transaction so the frame that will authorize a wheel dispatch is
        revalidated immediately before the single packet send.
        """

        self._require_input()
        self._require_scroll_transport()

    def scroll_wheel(
        self,
        x: int,
        y: int,
        *,
        vertical_detent: int,
        frame_size: tuple[int, int],
    ) -> WheelDispatch:
        """Sends exactly one signed vertical wheel detent through the scrcpy control transport.

        The packet is fully built and validated before the dispatch boundary so
        an invalid wheel request neither consumes the source frame nor advances
        the input sequence.
        """

        packet = build_scroll_packet(
            x=x,
            y=y,
            width=frame_size[0],
            height=frame_size[1],
            vscroll_detent=vertical_detent,
        )
        return self._send_wheel_packet(
            x=x,
            y=y,
            vertical_detent=vertical_detent,
            frame_size=frame_size,
            packet=packet,
        )

    @_input_dispatch
    def _send_wheel_packet(
        self,
        *,
        x: int,
        y: int,
        vertical_detent: int,
        frame_size: tuple[int, int],
        packet: bytes,
    ) -> WheelDispatch:
        """Crosses the dispatch boundary and sends one prebuilt wheel packet."""

        self._require_input()
        transport = self._require_scroll_transport()
        require_native_display_mapping(
            self.adb_client,
            device_id=self.instance.device_id,
            frame_size=frame_size,
        )
        # Display mapping is a blocking device read; the frame authorizing this
        # send must still be fresh at the packet boundary, not only on entry.
        authorizing_frame = self._authorizing_frame
        if authorizing_frame is not None:
            self._require_frame_within_age_policy(authorizing_frame)
        transport.send_packet(packet)
        return WheelDispatch(
            point=(x, y),
            frame_size=(frame_size[0], frame_size[1]),
            vertical_detent=vertical_detent,
            transport=SCROLL_TRANSPORT_NAME,
            input_sequence=self._input_sequence,
        )

    def _require_scroll_transport(self) -> ScrcpyControlTransport:
        """Builds or returns the session-epoch-owned scrcpy control transport."""

        transport = self._scroll_transport
        if transport is None:
            factory = self.scroll_transport_factory
            transport = (
                factory(self)
                if factory is not None
                else ScrcpyControlTransport(
                    adb_client=self.adb_client,
                    device_id=self.instance.device_id,
                    run_id=f"s{self._session_epoch}-{self._session_id[:12]}",
                )
            )
            transport.start()
            self._scroll_transport = transport
        return transport

    def _close_scroll_transport(self) -> None:
        """Releases the epoch-owned transport, preserving its cleanup failure."""

        transport = self._scroll_transport
        self._scroll_transport = None
        if transport is not None:
            transport.close()

    def capture_screenshot_bytes(self) -> bytes:
        """Captures a PNG screenshot through `adb exec-out screencap -p`."""

        return self.capture_screenshot_frame().payload

    def capture_screenshot_frame(self) -> CapturedFrame:
        """Captures one atomically provenance-stamped screenshot.

        The input sequence is sampled before and after the ADB capture.  Any
        concurrent input invalidates the capture instead of allowing a frame
        whose pixels may describe a different UI state to authorize an action.
        """

        self._ensure_lease()
        with self._provenance_lock:
            input_sequence = self._input_sequence
            session_epoch = self._session_epoch
            self._capture_sequence += 1
            capture_sequence = self._capture_sequence
            # A newer capture start invalidates the previous frame immediately;
            # an older backend completion must never republish it as newest.
            self._latest_frame = None
            self._consumed_frame = None
        captured_at = datetime.now(tz=UTC)
        captured_monotonic = time.monotonic()
        result = self.adb_client.exec_out(self.instance.device_id, "screencap", "-p", timeout_seconds=20)
        if not result.succeeded or result.stdout == b"":
            raise ScreenshotCaptureError(
                "Failed to capture screenshot from device.",
                device_id=self.instance.device_id,
                stderr=result.stderr_text,
            )
        with self._provenance_lock:
            if (
                input_sequence != self._input_sequence
                or session_epoch != self._session_epoch
                or capture_sequence != self._capture_sequence
            ):
                raise ScreenshotCaptureError(
                    "Screenshot capture overlapped session input or epoch change, or a newer capture began, and was discarded.",
                    device_id=self.instance.device_id,
                    capture_input_sequence=input_sequence,
                    current_input_sequence=self._input_sequence,
                    capture_session_epoch=session_epoch,
                    current_session_epoch=self._session_epoch,
                    capture_sequence=capture_sequence,
                    current_capture_sequence=self._capture_sequence,
                )
            frame_ref = FrameRef(
                session_id=self._session_id,
                session_epoch=self._session_epoch,
                capture_sequence=capture_sequence,
                input_sequence=self._input_sequence,
                captured_at=captured_at,
                captured_monotonic=captured_monotonic,
            )
            self._latest_frame = frame_ref
            self._consumed_frame = None
        return CapturedFrame(payload=result.stdout, frame_ref=frame_ref)

    def validate_and_consume_frame(self, frame_ref: FrameRef) -> None:
        """Atomically validates and consumes one fresh frame authorization proof."""

        with self.authorized_input(frame_ref):
            return

    @contextmanager
    def authorized_input(self, frame_ref: FrameRef):
        """Holds the provenance lock across one logical input dispatch."""

        with self._provenance_lock:
            self._validate_frame_locked(frame_ref)
            self._consumed_frame = _frame_identity(frame_ref)
            previous_frame = self._authorizing_frame
            self._authorizing_frame = frame_ref
            try:
                yield
            finally:
                self._authorizing_frame = previous_frame

    def _validate_frame_locked(self, frame_ref: FrameRef) -> None:
        """Validates a frame while the caller holds the provenance lock."""

        identity = _frame_identity(frame_ref)
        if frame_ref.session_id != self._session_id:
            raise FrameProvenanceError(
                "Action proof belongs to a different emulator session.",
                expected_session_id=self._session_id,
                actual_session_id=frame_ref.session_id,
            )
        if frame_ref.session_epoch != self._session_epoch:
            raise FrameProvenanceError(
                "Action proof belongs to an expired emulator session epoch.",
                expected_session_epoch=self._session_epoch,
                actual_session_epoch=frame_ref.session_epoch,
            )
        if self._latest_frame != frame_ref or frame_ref.input_sequence != self._input_sequence:
            raise FrameProvenanceError(
                "Action proof is stale because the session input or latest capture changed.",
                capture_sequence=frame_ref.capture_sequence,
                input_sequence=frame_ref.input_sequence,
                current_input_sequence=self._input_sequence,
            )
        self._require_frame_within_age_policy(frame_ref)
        if self._consumed_frame == identity:
            raise FrameProvenanceError(
                "Action proof was already consumed and cannot authorize replay.",
                capture_sequence=frame_ref.capture_sequence,
            )

    def _require_frame_within_age_policy(self, frame_ref: FrameRef) -> None:
        """Enforces the bounded frame age at the moment it is checked."""

        age_seconds = time.monotonic() - frame_ref.captured_monotonic
        if age_seconds < 0.0 or age_seconds > self.provenance_max_age_seconds:
            raise FrameProvenanceError(
                "Action proof exceeded the bounded frame age policy.",
                age_seconds=age_seconds,
                max_age_seconds=self.provenance_max_age_seconds,
            )

    def _start_session_epoch(self) -> None:
        """Starts a new connected epoch and clears prior frame authorization state."""

        self._close_scroll_transport()
        with self._provenance_lock:
            self._session_epoch += 1
            self._capture_sequence = 0
            self._input_sequence = 0
            self._latest_frame = None
            self._consumed_frame = None
            self._authorizing_frame = None

    def close(self) -> None:
        """Releases the owned transport, then runs phase cleanup and releases the lease.

        A transport cleanup failure is held while the operation lease release
        path runs, then surfaced so callers learn about unresolved remote
        resources without the failure stranding the lease.
        """

        if self._closed:
            return
        self._closed = True
        transport_cleanup_error: BaseException | None = None
        try:
            self._close_scroll_transport()
        except BaseException as error:
            transport_cleanup_error = error
        close_preserving_error(
            self._release_instance_lease,
            transport_cleanup_error,
            message="BlueStacks scroll transport and phase cleanup both failed.",
        )
        if transport_cleanup_error is not None:
            raise transport_cleanup_error

    def _release_instance_lease(self) -> None:
        """Runs the phase-end cleanup policy and releases the operation lease."""

        lease = self._instance_lease
        self._instance_lease = None
        should_close = self.cleanup_policy.should_close(instance=self.instance)
        if should_close and lease is None:
            raise DeviceConnectionError(
                "BlueStacks session cleanup requires an active instance lease.",
                display_name=self.instance.display_name,
            )
        if should_close and self.instance_closer is None:
            if lease is not None:
                lease.release()
            raise DeviceConnectionError(
                "BlueStacks session cleanup requested, but no instance closer is configured.",
                display_name=self.instance.display_name,
            )
        if should_close and self._cleanup_intent_id is None:
            try:
                self._ensure_cleanup_intent()
            except BaseException:
                if lease is not None:
                    lease.release()
                raise
        if lease is not None:
            finalizer = None
            if (
                should_close
                and self.instance_closer is not None
                and self._cleanup_intent_id is not None
            ):
                intent_id = self._cleanup_intent_id
                finalizer = lambda: self.instance_closer.finalize_close_intent(
                    self.instance,
                    intent_id=intent_id,
                )
            lease.release(finalizer=finalizer)

    def __enter__(self) -> "BlueStacksSession":
        """Enters an explicitly scoped connected session."""

        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        """Releases the session lease on normal or exceptional exit."""

        active_error = _exception if isinstance(_exception, BaseException) else None
        close_preserving_error(
            self.close,
            active_error,
            message="BlueStacks session operation and phase cleanup both failed.",
        )

    def _ensure_lease(self) -> ProcessInstanceLease:
        """Ensures every ADB operation is preceded by the configured display-name lease."""

        if self._closed:
            raise DeviceConnectionError(
                "BlueStacks session is closed.",
                display_name=self.instance.display_name,
            )
        if self._instance_lease is None:
            self._instance_lease = self.instance_lease or self.lease_registry.acquire(
                display_name=self.instance.display_name,
            )
        return self._instance_lease

    def _ensure_cleanup_intent(self) -> None:
        """Persists phase-end intent once the exact process is leased and connected."""

        if self._cleanup_intent_registered:
            return
        if self.cleanup_policy.mode is BlueStacksSessionCleanupMode.KEEP_WARM:
            if (
                self.instance_closer is not None
                and self.instance.host_instance_key is not None
                and self.instance.process_id is not None
            ):
                self.instance_closer.cancel_close_intent(self.instance)
            self._cleanup_intent_registered = True
            return
        if not self.cleanup_policy.should_close(instance=self.instance):
            self._cleanup_intent_registered = True
            return
        if self.instance_closer is None:
            raise DeviceConnectionError(
                "BlueStacks phase cleanup requires an instance lifecycle manager.",
                display_name=self.instance.display_name,
            )
        self._cleanup_intent_id = self.instance_closer.register_close_intent(
            self.instance,
            grace_period_seconds=self.cleanup_policy.shutdown_grace_seconds,
        )
        self._cleanup_intent_registered = True

    def _require_app_launch(self) -> None:
        """Rejects foreground/launch requests when the dynamic role policy forbids them."""

        if not self.capabilities.allow_app_launch:
            raise PermissionError(
                f"BlueStacks account for '{self.instance.display_name}' cannot foreground or launch the app."
            )

    def _require_input(self) -> None:
        """Rejects every input primitive when the dynamic role policy is read-only."""

        self._ensure_lease()
        if not self.capabilities.allow_input:
            raise PermissionError(
                f"BlueStacks account for '{self.instance.display_name}' is read-only and cannot send input."
            )


def _frame_identity(frame_ref: FrameRef) -> tuple[str, int, int, int]:
    """Returns the stable identity used for one-frame replay protection."""

    return (
        frame_ref.session_id,
        frame_ref.session_epoch,
        frame_ref.capture_sequence,
        frame_ref.input_sequence,
    )


_CURRENT_FOCUS_FIELD = re.compile(r"^[ \t]*mCurrentFocus[ \t]*=[ \t]*(?P<value>[^\r\n]*)[ \t]*\r?$", re.MULTILINE)
_WINDOW_FOCUS_VALUE = re.compile(
    r"^Window\{(?P<token>[0-9A-Fa-f]+)[ \t]+(?P<user>u[0-9]+)[ \t]+(?P<title>[^{}\r\n]+)\}$"
)


def _parse_current_focus_package(window_dump: str, *, device_id: str) -> str | None:
    """Extracts the package from exactly one WMS mCurrentFocus field."""

    matches = tuple(_CURRENT_FOCUS_FIELD.finditer(window_dump))
    if len(matches) != 1:
        raise GameLaunchError(
            "Android window output must contain exactly one mCurrentFocus field.",
            device_id=device_id,
            field="mCurrentFocus",
            field_count=len(matches),
        )
    value = matches[0].group("value").strip()
    if value == "null":
        return None
    match = _WINDOW_FOCUS_VALUE.fullmatch(value)
    if match is None:
        raise GameLaunchError(
            "Android mCurrentFocus field is malformed; expected a Window value or null.",
            device_id=device_id,
            field="mCurrentFocus",
        )
    title = match.group("title").strip()
    if not title:
        raise GameLaunchError(
            "Android mCurrentFocus Window title is empty.",
            device_id=device_id,
            field="mCurrentFocus",
        )
    component = title.split(maxsplit=1)[0]
    if "/" not in component:
        return None
    if component.count("/") != 1:
        raise GameLaunchError(
            "Android mCurrentFocus Window component is malformed.",
            device_id=device_id,
            field="mCurrentFocus",
        )
    package, _, activity = component.partition("/")
    if not package or not activity:
        raise GameLaunchError(
            "Android mCurrentFocus Window component is malformed.",
            device_id=device_id,
            field="mCurrentFocus",
        )
    return package


def _encode_adb_text(text: str) -> str:
    """Encodes Android spaces and quotes one literal argument for its remote shell."""

    if "\n" in text or "\r" in text:
        raise DeviceConnectionError("ADB text input does not support multiline values.")
    return shlex.quote(text.replace(" ", "%s"))


_QWERTY_KEY_ROWS = (
    ("1234567890", -1.0, 0.0),
    ("qwertyuiop", 0.0, 0.0),
    ("asdfghjkl", 1.0, 0.4),
    ("zxcvbnm", 2.0, 0.8),
)
_QWERTY_KEY_POSITIONS = {
    key: (row_index, column_index + row_offset)
    for row, row_index, row_offset in _QWERTY_KEY_ROWS
    for column_index, key in enumerate(row)
}
_QWERTY_FINGERS = {
    "1": 0, "q": 0, "a": 0, "z": 0,
    "2": 1, "w": 1, "s": 1, "x": 1,
    "3": 2, "e": 2, "d": 2, "c": 2,
    "4": 3, "5": 3, "r": 3, "f": 3, "v": 3, "t": 3, "g": 3, "b": 3,
    "6": 4, "7": 4, "y": 4, "h": 4, "n": 4, "u": 4, "j": 4, "m": 4,
    "8": 5, "i": 5, "k": 5,
    "9": 6, "o": 6, "l": 6,
    "0": 7, "p": 7,
}
_QWERTY_MAX_KEY_DISTANCE = max(
    math.hypot(first_row - second_row, first_column - second_column)
    for first_row, first_column in _QWERTY_KEY_POSITIONS.values()
    for second_row, second_column in _QWERTY_KEY_POSITIONS.values()
)


def _qwerty_key_distance(first: str, second: str) -> float | None:
    """Returns the unit-key distance between two keys on a staggered QWERTY layout."""

    first_position = _QWERTY_KEY_POSITIONS.get(first.lower())
    second_position = _QWERTY_KEY_POSITIONS.get(second.lower())
    if first_position is None or second_position is None:
        return None
    return math.hypot(
        first_position[0] - second_position[0],
        first_position[1] - second_position[1],
    )


def _same_qwerty_finger(first: str, second: str) -> bool:
    """Returns whether two different keys share one touch-typing finger on QWERTY."""

    first_key, second_key = first.lower(), second.lower()
    if first_key == second_key:
        return False
    first_finger = _QWERTY_FINGERS.get(first_key)
    return first_finger is not None and first_finger == _QWERTY_FINGERS.get(second_key)


def _skewed_delay_seconds(low: float, high: float, *, rng: random.Random) -> float:
    """Draws one right-skewed pause: most keystrokes are quick, long pauses happen."""

    return rng.triangular(low, high, low + (high - low) * 0.2)


def _type_delay_seconds(previous: str, current: str, *, rng: random.Random) -> float:
    """Returns one human-like pause before the next keystroke.

    Word boundaries pause longest; within a word the pause grows with the
    QWERTY distance a finger travels between the two keys plus a penalty
    for same-finger transitions, with a mid-range pause for keys outside
    the layout. Draws are right-skewed like measured keystroke intervals.
    """

    if previous == " " or current == " ":
        return _skewed_delay_seconds(*_input_word_delay_seconds_range, rng=rng)
    low, high = _input_letter_delay_seconds_range
    distance = _qwerty_key_distance(previous, current)
    scale = 0.5 if distance is None else distance / _QWERTY_MAX_KEY_DISTANCE
    shift = _input_letter_delay_distance_seconds * scale
    if _same_qwerty_finger(previous, current):
        shift += _input_letter_same_finger_seconds
    return _skewed_delay_seconds(low + shift, high + shift, rng=rng)


def _require_point_in_safe_bounds(
    point: tuple[int, int],
    *,
    safe_bounds: Bounds | None,
    primitive: str,
    device_id: str,
) -> None:
    """Rejects one resolved input point that escapes its declared delivery rectangle."""

    if safe_bounds is None:
        return
    if safe_bounds.width <= 0 or safe_bounds.height <= 0:
        raise DeviceConnectionError(
            f"Input safe bounds for {primitive} must be a nonempty rectangle.",
            device_id=device_id,
        )
    if not safe_bounds.contains_point(point):
        raise DeviceConnectionError(
            f"Resolved {primitive} point {point} escapes its declared safe bounds {safe_bounds}.",
            device_id=device_id,
            point=point,
        )


def _input_command_prefix(*, input_source: str, device_id: str) -> list[str]:
    """Returns the shared `adb shell input` prefix for the requested Android input source."""

    if input_source == "touchscreen":
        return ["input", "touchscreen"]
    if input_source == "default":
        return ["input"]
    raise DeviceConnectionError(
        "Unsupported swipe input source.",
        device_id=device_id,
        input_source=input_source,
    )


def _motion_event_drag_timeline(
    *,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int,
    rng: random.Random,
    jitter_px: float,
) -> tuple[tuple[str, int, int, float], ...]:
    """Builds one press-move-release event timeline.

    With `jitter_px <= 0` the timeline is the original linear path with uniform
    delays; otherwise the move samples follow an eased progress curve with a
    small perpendicular drift and non-uniform delays, which better matches a
    real finger drag than a perfectly straight constant-velocity line.
    """

    move_event_count = 4
    transition_count = move_event_count + 1
    if jitter_px <= 0:
        points = [(start_x, start_y)]
        for step_index in range(1, move_event_count + 1):
            progress = step_index / move_event_count
            points.append(
                (
                    round(start_x + ((end_x - start_x) * progress)),
                    round(start_y + ((end_y - start_y) * progress)),
                )
            )
        segment_delay_seconds = max(duration_ms, 0) / 1000.0 / transition_count
        delays = [segment_delay_seconds] * transition_count
    else:
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length = math.hypot(delta_x, delta_y)
        normal_x, normal_y = (-delta_y / length, delta_x / length) if length else (0.0, 0.0)
        drift_amplitude = min(jitter_px * 2.0, length * 0.05)
        points = [(start_x, start_y)]
        for step_index in range(1, move_event_count + 1):
            progress = step_index / move_event_count
            eased = progress * progress * (3.0 - 2.0 * progress)
            drift = rng.triangular(-drift_amplitude, drift_amplitude) * math.sin(math.pi * progress)
            points.append(
                (
                    round(start_x + delta_x * eased + normal_x * drift),
                    round(start_y + delta_y * eased + normal_y * drift),
                )
            )
        weights = [rng.uniform(0.6, 1.4) for _ in range(transition_count)]
        total_seconds = max(duration_ms, 0) / 1000.0
        weight_sum = sum(weights)
        delays = [total_seconds * weight / weight_sum for weight in weights]
    timeline: list[tuple[str, int, int, float]] = [("DOWN", start_x, start_y, delays[0])]
    for index, (x, y) in enumerate(points[1:]):
        timeline.append(("MOVE", x, y, delays[index + 1]))
    timeline.append(("UP", end_x, end_y, 0.0))
    return tuple(timeline)
