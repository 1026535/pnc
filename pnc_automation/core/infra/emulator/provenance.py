"""Session-bound screenshot provenance used to authorize emulator input."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FrameRef:
    """Immutable identity for one screenshot captured by one session epoch."""

    session_id: str
    session_epoch: int
    capture_sequence: int
    input_sequence: int
    captured_at: datetime
    captured_monotonic: float = 0.0


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """Carries screenshot bytes together with their immutable session proof."""

    payload: bytes
    frame_ref: FrameRef
