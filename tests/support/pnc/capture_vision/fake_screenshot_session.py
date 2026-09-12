"""Synthetic FakeScreenshotSession fixture."""

from __future__ import annotations



class _FakeScreenshotSession:
    """Returns a fixed screenshot payload."""

    def __init__(self, payload: bytes) -> None:
        """Stores the screenshot bytes returned by capture."""

        self._payload = payload

    def capture_screenshot_bytes(self) -> bytes:
        """Returns the pre-seeded screenshot bytes."""

        return self._payload
