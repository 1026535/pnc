"""Synthetic FakeScreenshotSession fixture."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count

from pnc_automation.core.infra.emulator.provenance import CapturedFrame, FrameRef


_SYNTHETIC_FRAME_SEQUENCE = count(1)


def make_captured_frame(payload: bytes, *, session_id: str = "synthetic-capture-session") -> CapturedFrame:
    """Builds a unique explicit provenance frame for screenshot-service fakes."""

    sequence = next(_SYNTHETIC_FRAME_SEQUENCE)
    return CapturedFrame(
        payload=payload,
        frame_ref=FrameRef(
            session_id=session_id,
            session_epoch=1,
            capture_sequence=sequence,
            input_sequence=0,
            captured_at=datetime.now(tz=UTC),
            captured_monotonic=__import__("time").monotonic(),
        ),
    )

class _FakeScreenshotSession:
    """Returns a fixed screenshot payload."""

    def __init__(self, payload: bytes) -> None:
        """Stores the screenshot bytes returned by capture."""

        self._payload = payload

    def capture_screenshot_frame(self) -> CapturedFrame:
        """Returns the pre-seeded screenshot bytes with explicit provenance."""

        return make_captured_frame(self._payload)
