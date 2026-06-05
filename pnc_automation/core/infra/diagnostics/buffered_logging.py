"""Shared buffered-vs-immediate structured logging helpers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DiagnosticLogMode(StrEnum):
    """Defines whether structured diagnostics are emitted immediately or buffered per sequence."""

    IMMEDIATE = "immediate"
    BUFFERED_SEQUENCE = "buffered_sequence"


@dataclass(frozen=True, slots=True)
class BufferedDiagnosticEvent:
    """Carries one buffered structured log event until a sequence flush writes it through."""

    level: int
    message: str
    extra: Mapping[str, Any] | None = None


def emit_diagnostic_log(
    *,
    logger: logging.LoggerAdapter | None,
    runtime_state: dict[str, Any] | None,
    mode: DiagnosticLogMode,
    level: int,
    message: str,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Emits one structured diagnostic log immediately or buffers it on the shared runtime state."""

    if logger is None:
        return
    if mode == DiagnosticLogMode.IMMEDIATE:
        _write_log(logger=logger, level=level, message=message, extra=extra)
        return
    buffer = _buffer(runtime_state)
    buffer.append(BufferedDiagnosticEvent(level=level, message=message, extra=extra))


def flush_buffered_diagnostic_logs(
    *,
    logger: logging.LoggerAdapter | None,
    runtime_state: dict[str, Any] | None,
) -> None:
    """Flushes any buffered sequence logs in order and clears the shared runtime buffer."""

    if logger is None or runtime_state is None:
        return
    buffer = _buffer(runtime_state)
    while buffer:
        event = buffer.pop(0)
        _write_log(logger=logger, level=event.level, message=event.message, extra=event.extra)


def _buffer(runtime_state: dict[str, Any] | None) -> list[BufferedDiagnosticEvent]:
    """Returns the mutable buffered diagnostics list on runtime state, creating it when needed."""

    if runtime_state is None:
        return []
    key = "_buffered_diagnostic_events"
    value = runtime_state.get(key)
    if isinstance(value, list) and all(isinstance(item, BufferedDiagnosticEvent) for item in value):
        return value
    buffer: list[BufferedDiagnosticEvent] = []
    runtime_state[key] = buffer
    return buffer


def _write_log(
    *,
    logger: logging.LoggerAdapter,
    level: int,
    message: str,
    extra: Mapping[str, Any] | None,
) -> None:
    """Writes one structured event through the wrapped logger while preserving adapter extras."""

    merged_extra = {**logger.extra, **({} if extra is None else dict(extra))}
    logger.logger.log(level, message, extra=merged_extra)
