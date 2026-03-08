"""Typed error model for the automation platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AutomationErrorKind(StrEnum):
    """Categorizes fail-fast automation errors."""

    CONFIGURATION = "configuration"
    DEVICE_CONNECTION = "device_connection"
    GAME_LAUNCH = "game_launch"
    SCREENSHOT_CAPTURE = "screenshot_capture"
    SCREEN_CLASSIFICATION = "screen_classification"
    SELECTOR_RESOLUTION = "selector_resolution"
    TASK_VERIFICATION = "task_verification"
    SCRIPT_VALIDATION = "script_validation"


@dataclass(slots=True)
class AutomationError(RuntimeError):
    """Base exception that carries a typed automation failure kind."""

    message: str
    kind: AutomationErrorKind
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initializes the base RuntimeError message."""

        RuntimeError.__init__(self, self.message)


class ConfigurationError(AutomationError):
    """Raised when configuration is invalid or incomplete."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message=message, kind=AutomationErrorKind.CONFIGURATION, details=details)


class DeviceConnectionError(AutomationError):
    """Raised when the target emulator session cannot be reached reliably."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message=message, kind=AutomationErrorKind.DEVICE_CONNECTION, details=details)


class GameLaunchError(AutomationError):
    """Raised when the game cannot be foregrounded."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message=message, kind=AutomationErrorKind.GAME_LAUNCH, details=details)


class ScreenshotCaptureError(AutomationError):
    """Raised when screenshot capture or image decoding fails."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message=message, kind=AutomationErrorKind.SCREENSHOT_CAPTURE, details=details)


class ScreenClassificationError(AutomationError):
    """Raised when a screenshot cannot be interpreted into a supported screen state."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message=message, kind=AutomationErrorKind.SCREEN_CLASSIFICATION, details=details)


class SelectorResolutionError(AutomationError):
    """Raised when a required selector or observed UI element cannot be resolved."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message=message, kind=AutomationErrorKind.SELECTOR_RESOLUTION, details=details)


class TaskVerificationError(AutomationError):
    """Raised when a task cannot verify its expected state transition."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message=message, kind=AutomationErrorKind.TASK_VERIFICATION, details=details)


class ScriptValidationError(AutomationError):
    """Raised when a run script contains invalid task identifiers or parameters."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message=message, kind=AutomationErrorKind.SCRIPT_VALIDATION, details=details)
