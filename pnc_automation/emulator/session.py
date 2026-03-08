"""BlueStacks-specific device and app control built on top of ADB."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.adb.client import AdbClient
from pnc_automation.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.errors import DeviceConnectionError, GameLaunchError, ScreenshotCaptureError


@dataclass(slots=True)
class BlueStacksSession:
    """Owns one connected emulator session and app-level control primitives."""

    adb_client: AdbClient
    instance: BlueStacksInstance

    def connect(self) -> None:
        """Connects to the configured ADB endpoint and validates device readiness."""

        result = self.adb_client.connect(self.instance.device_id)
        if not result.succeeded:
            raise DeviceConnectionError(
                f"Failed to connect to device '{self.instance.device_id}'.",
                device_id=self.instance.device_id,
                stderr=result.stderr_text,
            )
        state = self.adb_client.get_state(self.instance.device_id)
        if not state.succeeded or state.stdout_text.strip() != "device":
            raise DeviceConnectionError(
                f"Device '{self.instance.device_id}' is not ready.",
                device_id=self.instance.device_id,
                stdout=state.stdout_text,
                stderr=state.stderr_text,
            )

    def ensure_responsive(self) -> None:
        """Ensures the Android session responds to a trivial shell command."""

        result = self.adb_client.shell(self.instance.device_id, "echo", "ready")
        if not result.succeeded or result.stdout_text.strip() != "ready":
            raise DeviceConnectionError(
                f"Device '{self.instance.device_id}' did not respond to a readiness check.",
                device_id=self.instance.device_id,
                stdout=result.stdout_text,
                stderr=result.stderr_text,
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
    ) -> None:
        """Sends one swipe gesture."""

        result = self.adb_client.shell(
            self.instance.device_id,
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(duration_ms),
        )
        if not result.succeeded:
            raise DeviceConnectionError(
                "Failed to send swipe gesture.",
                device_id=self.instance.device_id,
                stderr=result.stderr_text,
            )

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
