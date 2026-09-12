"""Synthetic FakeScreenshotSession fixture."""

from __future__ import annotations

from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame


class _FakeScreenshotSession:
    """Returns a deterministic screenshot payload for synthetic vision tests."""

    def __init__(self, payload: bytes) -> None:
        """Stores the screenshot payload returned by capture."""

        self._payload = payload

    def capture_screenshot_frame(self):
        """Returns the pre-seeded screenshot bytes with explicit provenance."""

        return make_captured_frame(self._payload)
