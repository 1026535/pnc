"""BlueStacks-specific device and app control built on top of ADB."""

from __future__ import annotations

import math
import re
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
from pnc_automation.core.infra.emulator.provenance import CapturedFrame, FrameRef
from pnc_automation.core.lifecycle import close_preserving_error


def _input_dispatch(function: Callable[..., object]) -> Callable[..., object]:
    """Serializes one entire ADB input call with capture provenance state."""

    @wraps(function)
    def wrapped(session: BlueStacksSession, *args: object, **kwargs: object) -> object:
        with session._provenance_lock:
            session._input_sequence += 1
            return function(session, *args, **kwargs)

    return wrapped


DEFAULT_BLUESTACKS_SHUTDOWN_GRACE_SECONDS = 120.0


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
    _provenance_lock: RLock = field(default_factory=RLock, init=False, repr=False)

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
        """Returns whether the configured P&C package is the foreground app."""

        self._ensure_lease()
        result = self.adb_client.shell(self.instance.device_id, "dumpsys", "window", "windows")
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

    def ensure_app_foregrounded(self) -> bool:
        """Launches the game when needed and reports whether a launch was started."""

        if self.is_app_foregrounded():
            return False
        self._require_app_launch()
        self.launch_app()
        return True

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

    @_input_dispatch
    def tap_point(self, x: int, y: int) -> None:
        """Sends one screen tap to the device."""

        self._require_input()
        result = self.adb_client.shell(self.instance.device_id, "input", "tap", str(x), str(y))
        if not result.succeeded:
            raise DeviceConnectionError(
                f"Failed to tap point ({x}, {y}).",
                device_id=self.instance.device_id,
                x=x,
                y=y,
                stderr=result.stderr_text,
            )

    @_input_dispatch
    def input_text(self, text: str) -> None:
        """Inputs one text payload using Android's input subsystem."""

        self._require_input()
        encoded = _encode_adb_text(text)
        result = self.adb_client.shell(self.instance.device_id, "input", "text", encoded)
        if not result.succeeded:
            raise DeviceConnectionError(
                "Failed to input text through ADB.",
                device_id=self.instance.device_id,
                stderr=result.stderr_text,
            )

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
    ) -> None:
        """Sends one swipe-like drag through the requested Android input primitive."""

        self._require_input()
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
            return
        if gesture_primitive != "press_move_release":
            raise DeviceConnectionError(
                "Unsupported swipe gesture primitive.",
                device_id=self.instance.device_id,
                gesture_primitive=gesture_primitive,
            )
        motion_event_prefix = [*_input_command_prefix(input_source=input_source, device_id=self.instance.device_id), "motionevent"]
        timeline = _motion_event_drag_timeline(
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            duration_ms=duration_ms,
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
            yield

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
        age_seconds = time.monotonic() - frame_ref.captured_monotonic
        if age_seconds < 0.0 or age_seconds > self.provenance_max_age_seconds:
            raise FrameProvenanceError(
                "Action proof exceeded the bounded frame age policy.",
                age_seconds=age_seconds,
                max_age_seconds=self.provenance_max_age_seconds,
            )
        if self._consumed_frame == identity:
            raise FrameProvenanceError(
                "Action proof was already consumed and cannot authorize replay.",
                capture_sequence=frame_ref.capture_sequence,
            )

    def _start_session_epoch(self) -> None:
        """Starts a new connected epoch and clears prior frame authorization state."""

        with self._provenance_lock:
            self._session_epoch += 1
            self._capture_sequence = 0
            self._input_sequence = 0
            self._latest_frame = None
            self._consumed_frame = None

    def close(self) -> None:
        """Optionally closes the selected phase target, then releases its operation lease."""

        if self._closed:
            return
        self._closed = True
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
    """Encodes text for `adb shell input text` without shell quoting."""

    if "\n" in text or "\r" in text:
        raise DeviceConnectionError("ADB text input does not support multiline values.", text=text)
    replacements = {
        " ": "%s",
        "&": "\\&",
        "<": "\\<",
        ">": "\\>",
        "|": "\\|",
        ";": "\\;",
        "(": "\\(",
        ")": "\\)",
        "'": "\\'",
        '"': '\\"',
    }
    return "".join(replacements.get(character, character) for character in text)


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
) -> tuple[tuple[str, int, int, float], ...]:
    """Builds one linear press-move-release event timeline with bounded intermediate move samples."""

    move_event_count = 4
    points = [(start_x, start_y)]
    for step_index in range(1, move_event_count + 1):
        progress = step_index / move_event_count
        points.append(
            (
                round(start_x + ((end_x - start_x) * progress)),
                round(start_y + ((end_y - start_y) * progress)),
            )
        )
    transition_count = move_event_count + 1
    segment_delay_seconds = max(duration_ms, 0) / 1000.0 / transition_count
    timeline: list[tuple[str, int, int, float]] = [("DOWN", start_x, start_y, segment_delay_seconds)]
    for x, y in points[1:]:
        timeline.append(("MOVE", x, y, segment_delay_seconds))
    timeline.append(("UP", end_x, end_y, 0.0))
    return tuple(timeline)
