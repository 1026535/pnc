"""BlueStacks-specific device and app control built on top of ADB."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from pnc_automation.core.infra.adb.client import AdbClient
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.bluestacks_management.instance_lease import (
    PROCESS_INSTANCE_LEASES,
    InstanceLeaseRegistry,
    ProcessInstanceLease,
)
from pnc_automation.core.config.host import BlueStacksCapabilities
from pnc_automation.core.errors import DeviceConnectionError, GameLaunchError, ScreenshotCaptureError
from pnc_automation.core.lifecycle import close_preserving_error


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
    _instance_lease: ProcessInstanceLease | None = field(default=None, init=False, repr=False)
    _cleanup_intent_registered: bool = field(default=False, init=False, repr=False)
    _cleanup_intent_id: str | None = field(default=None, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

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
        return self.instance.app_package in result.stdout_text

    def ensure_app_foregrounded(self) -> bool:
        """Launches the game when needed and reports whether a launch was started."""

        if self.is_app_foregrounded():
            return False
        self._require_app_launch()
        self.launch_app()
        return True

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

        self._ensure_lease()
        result = self.adb_client.exec_out(self.instance.device_id, "screencap", "-p", timeout_seconds=20)
        if not result.succeeded or result.stdout == b"":
            raise ScreenshotCaptureError(
                "Failed to capture screenshot from device.",
                device_id=self.instance.device_id,
                stderr=result.stderr_text,
            )
        return result.stdout

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
