"""Shared immediate and asynchronous structured logging helpers."""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pnc_automation.core.infra.diagnostics.logging_setup import submit_async_diagnostic_record


class DiagnosticLogMode(StrEnum):
    """Defines whether structured diagnostics are emitted immediately or queued asynchronously."""

    IMMEDIATE = "immediate"
    ASYNC_QUEUE = "async_queue"


def emit_diagnostic_log(
    *,
    logger: logging.LoggerAdapter | None,
    mode: DiagnosticLogMode,
    level: int,
    message: str,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Emits one structured diagnostic immediately or enqueues a producer-time record."""

    if logger is None or not logger.logger.isEnabledFor(level):
        return
    merged_extra = {
        **({} if logger.extra is None else dict(logger.extra)),
        **({} if extra is None else dict(extra)),
    }
    if mode == DiagnosticLogMode.IMMEDIATE:
        logger.logger.log(level, message, extra=merged_extra)
        return
    if mode != DiagnosticLogMode.ASYNC_QUEUE:
        raise ValueError(f"unsupported diagnostic log mode: {mode!r}")

    snapshot = copy.deepcopy(merged_extra)
    pathname, lineno, function, stack_info = logger.logger.findCaller(stacklevel=2)
    record = logger.logger.makeRecord(
        logger.logger.name,
        level,
        pathname,
        lineno,
        message,
        (),
        None,
        function,
        extra=snapshot,
        sinfo=stack_info,
    )
    submit_async_diagnostic_record(logger.logger, record)
