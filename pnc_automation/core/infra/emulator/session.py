"""BlueStacks-specific device and app control built on top of ADB."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from pnc_automation.core.infra.adb.client import AdbClient
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.errors import DeviceConnectionError, GameLaunchError, ScreenshotCaptureError


@dataclass(slots=True)
class BlueStacksSession:
    """Owns one connected emulator session and app-level control primitives."""

    adb_client: AdbClient
    instance: BlueStacksInstance
    sleep: Callable[[float], None] = time.sleep
    connect_attempts: int = 30
    connect_retry_delay_seconds: float = 2.0

    def connect(self) -> None:
        """Connects to the configured ADB endpoint and validates device readiness."""

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

    def ensure_responsive(self) -> None:
        """Ensures the Android session responds to a trivial shell command."""

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

        result = self.adb_client.shell(self.instance.device_id, "dumpsys", "window", "windows")
        if not result.succeeded:
            raise GameLaunchError(
                f"Failed to determine foreground app for '{self.instance.device_id}'.",
                device_id=self.instance.device_id,
                stderr=result.stderr_text,
            )
        return self.instance.app_package in result.stdout_text

    def ensure_app_foregrounded(self) -> None:
        """Launches the game when it is not already foregrounded."""

        if self.is_app_foregrounded():
            return
        self.launch_app()

    def launch_app(self) -> None:
        """Launches the configured Puzzles & Conquest package."""

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

        result = self.adb_client.exec_out(self.instance.device_id, "screencap", "-p", timeout_seconds=20)
        if not result.succeeded or result.stdout == b"":
            raise ScreenshotCaptureError(
                "Failed to capture screenshot from device.",
                device_id=self.instance.device_id,
                stderr=result.stderr_text,
            )
        return result.stdout


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
