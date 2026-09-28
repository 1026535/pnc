"""Typed records describing actual dispatched emulator input.

A dispatch record is a receipt: it binds the source frame that authorized one
logical input to the exact parameters the backend accepted. It never asserts
that the game applied the gesture; observed navigation state still requires a
fresh destination observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pnc_automation.core.infra.emulator.provenance import FrameRef


@dataclass(frozen=True, slots=True)
class SwipeDispatch:
    """Actual swipe gesture parameters dispatched to the backend after jitter."""

    start: tuple[int, int]
    end: tuple[int, int]
    duration_ms: int
    input_source: str
    gesture_primitive: str
    input_sequence: int


@dataclass(frozen=True, slots=True)
class TapDispatch:
    """Actual tap point dispatched to the backend after jitter."""

    point: tuple[int, int]
    input_sequence: int


@dataclass(frozen=True, slots=True)
class WheelDispatch:
    """Actual one-detent wheel message sent through the control transport."""

    point: tuple[int, int]
    frame_size: tuple[int, int]
    vertical_detent: int
    transport: str
    input_sequence: int


@dataclass(frozen=True, slots=True)
class InputDispatchRecord:
    """Binds one source frame to the input its provenance authorized."""

    source_frame: FrameRef
    dispatch: SwipeDispatch | WheelDispatch | TapDispatch
    artifact_path: Path | None = None
    home_city: bool = False


@dataclass(frozen=True, slots=True)
class InputDispatchFailure:
    """Records one input attempt that ended without a confirmed dispatch receipt.

    A send-side failure can leave backend dispatch uncertain; this record only
    asserts that no dispatch receipt was produced for the attempt.
    """

    source_frame: FrameRef | None
    input_kind: str
    failure_phase: str
    exception_type: str
    operation_id: str | None = None
    artifact_path: Path | None = None
    home_city: bool = False


InputDispatchEvent = InputDispatchRecord | InputDispatchFailure
"""Union accepted by the executor's optional dispatch receipt callback."""
