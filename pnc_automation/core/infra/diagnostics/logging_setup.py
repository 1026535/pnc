"""Structured logging configuration for automation runs."""

from __future__ import annotations

import atexit
import contextvars
import json
import logging
import re
import sys
import threading
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any, TypeVar

from pnc_automation.core.infra.diagnostics.async_diagnostic_writer import (
    AsyncDiagnosticWriter,
    AsyncDiagnosticWriterClosedError,
)


_QUEUE_CAPACITY = 512
_MAX_BATCH_SIZE = 64
_BATCH_INTERVAL_SECONDS = 0.1
_ADMISSION_TIMEOUT_SECONDS = 0.1
_ASYNC_HANDLER_DELIVERY: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "async_diagnostic_handler_delivery",
    default=False,
)


@dataclass(frozen=True, slots=True)
class _QueuedDiagnosticRecord:
    """Routes one already-prepared log record through its producer logger."""

    logger: logging.Logger
    record: logging.LogRecord


@dataclass(slots=True)
class _LoggingOwner:
    """Owns the configured sinks and their single asynchronous writer."""

    configuration: tuple[bool, Path | None]
    logger: logging.Logger
    handlers: tuple[logging.Handler, ...]
    writer: AsyncDiagnosticWriter[_QueuedDiagnosticRecord]


class _AsyncFailureReportingHandlerMixin:
    """Rethrows handler errors during asynchronous delivery for the writer to latch."""

    def handleError(self, record: logging.LogRecord) -> None:
        if _ASYNC_HANDLER_DELIVERY.get():
            error = sys.exception()
            if error is not None:
                raise error
            raise RuntimeError("logging handler reported an error without an active exception")
        super().handleError(record)


class _OwnedStreamHandler(_AsyncFailureReportingHandlerMixin, logging.StreamHandler):
    """Stream handler that preserves synchronous error policy and exposes async sink failures."""


class _OwnedRotatingFileHandler(_AsyncFailureReportingHandlerMixin, RotatingFileHandler):
    """Rotating file handler that exposes async sink failures to its writer."""


_OWNER_LOCK = threading.RLock()
_LIFECYCLE_LOCK = threading.RLock()
_OWNER: _LoggingOwner | None = None
_ResultT = TypeVar("_ResultT")


class JsonLogFormatter(logging.Formatter):
    """Formats log records as compact JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        """Serializes the record, structured extras, and sanitized exception context."""

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _RESERVED_LOG_FIELDS:
                continue
            payload[key] = value
        exc_info = record.exc_info
        if isinstance(exc_info, tuple) and len(exc_info) == 3 and exc_info[1] is not None:
            payload["_exception"] = _exception_payload(exc_info[1], exc_info[2], {id(exc_info[1])})
        if record.stack_info:
            payload["_stack"] = _stack_info_frames(record.stack_info)
        return json.dumps(payload, default=str)


_RESERVED_LOG_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}

_STACK_INFO_FRAME = re.compile(r'\s*File "(?P<path>.*)", line (?P<line>\d+), in (?P<function>.*\S)\s*$')


def _exception_payload(
    exception: BaseException,
    tb: TracebackType | None,
    seen: set[int],
) -> dict[str, Any]:
    """Serializes the exception class and its sanitized traceback chain.

    Top-level frames come from ``tb``, the traceback captured on the record;
    exception-group members and chained ``cause``/``context`` frames come from
    each nested exception's own traceback. Exception text, absolute paths,
    source lines, and frame locals are never included.
    """

    payload: dict[str, Any] = {
        "type": type(exception).__name__,
        "frames": _traceback_frames(tb),
    }
    if isinstance(exception, BaseExceptionGroup):
        members = []
        for member in exception.exceptions:
            if id(member) not in seen:
                member_seen = seen | {id(member)}
                members.append(_exception_payload(member, member.__traceback__, member_seen))
        payload["exceptions"] = members
    cause = getattr(exception, "__cause__", None)
    if cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        payload["cause"] = _exception_payload(cause, getattr(cause, "__traceback__", None), seen)
    context = getattr(exception, "__context__", None)
    if (
        context is not None
        and not getattr(exception, "__suppress_context__", False)
        and id(context) not in seen
    ):
        seen.add(id(context))
        payload["context"] = _exception_payload(context, getattr(context, "__traceback__", None), seen)
    return payload


def _traceback_frames(tb: TracebackType | None) -> list[dict[str, Any]]:
    """Returns file basename, function, and line for each traceback frame."""

    frames = []
    for frame, lineno in traceback.walk_tb(tb):
        code = frame.f_code
        frames.append({"file": _basename(code.co_filename), "function": code.co_name, "line": lineno})
    return frames


def _stack_info_frames(stack_info: str) -> list[dict[str, Any]]:
    """Reduces a captured stack string to safe frame metadata."""

    frames = []
    for line in stack_info.splitlines():
        match = _STACK_INFO_FRAME.match(line)
        if match is not None:
            frames.append(
                {
                    "file": _basename(match.group("path")),
                    "function": match.group("function"),
                    "line": int(match.group("line")),
                }
            )
    return frames


def _basename(path: str) -> str:
    """Returns the final path component for either platform separator."""

    return path.replace("\\", "/").rsplit("/", 1)[-1]


def configure_logging(*, verbose: bool = False, log_file_root: Path | None = None) -> logging.Logger:
    """Configures JSON-line diagnostics and reuses one healthy owner for identical settings."""

    global _OWNER
    configuration = (
        verbose,
        None if log_file_root is None else Path(log_file_root).resolve(),
    )
    with _LIFECYCLE_LOCK:
        with _OWNER_LOCK:
            owner = _OWNER
            if (
                owner is not None
                and owner.configuration == configuration
                and owner.writer.failure is None
                and not owner.writer.closed
            ):
                return owner.logger
        if owner is not None:
            shutdown_logging()

        root_logger = logging.getLogger("pnc_automation")
        root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        for existing_handler in tuple(root_logger.handlers):
            root_logger.removeHandler(existing_handler)
            existing_handler.close()

        if configuration[1] is not None:
            configuration[1].mkdir(parents=True, exist_ok=True)

        handlers: list[logging.Handler] = []
        try:
            stream_handler = _OwnedStreamHandler()
            stream_handler.setFormatter(JsonLogFormatter())
            handlers.append(stream_handler)
            if configuration[1] is not None:
                file_handler = _OwnedRotatingFileHandler(
                    configuration[1] / "bluestacks_management.jsonl",
                    maxBytes=1_000_000,
                    backupCount=3,
                    encoding="utf-8",
                )
                file_handler.setFormatter(JsonLogFormatter())
                handlers.append(file_handler)
            for handler in handlers:
                root_logger.addHandler(handler)
            root_logger.propagate = False

            writer = AsyncDiagnosticWriter(
                _write_async_batch,
                queue_capacity=_QUEUE_CAPACITY,
                max_batch_size=_MAX_BATCH_SIZE,
                batch_interval=_BATCH_INTERVAL_SECONDS,
                admission_timeout=_ADMISSION_TIMEOUT_SECONDS,
            )
        except BaseException:
            for handler in handlers:
                root_logger.removeHandler(handler)
                handler.close()
            raise

        with _OWNER_LOCK:
            _OWNER = _LoggingOwner(
                configuration=configuration,
                logger=root_logger,
                handlers=tuple(handlers),
                writer=writer,
            )
        return root_logger


def submit_async_diagnostic_record(logger: logging.Logger, record: logging.LogRecord) -> None:
    """Enqueues one producer-prepared record on the configured diagnostics writer."""

    with _OWNER_LOCK:
        owner = _OWNER
    if owner is None:
        raise AsyncDiagnosticWriterClosedError(
            "asynchronous diagnostic logging is not configured or has been shut down"
        )
    owner.writer.submit(_QueuedDiagnosticRecord(logger=logger, record=record))


def shutdown_logging() -> None:
    """Stops async admission, drains accepted records, then flushes and closes owned handlers."""

    global _OWNER
    with _LIFECYCLE_LOCK:
        with _OWNER_LOCK:
            owner = _OWNER
        if owner is None:
            return

        failure: BaseException | None = None
        try:
            owner.writer.close()
        except BaseException as error:
            failure = error

        for handler in owner.handlers:
            owner.logger.removeHandler(handler)
        for handler in owner.handlers:
            for close_action in (handler.flush, handler.close):
                try:
                    close_action()
                except BaseException as error:
                    if failure is None:
                        failure = error
                    else:
                        failure.add_note(f"Logging handler cleanup also failed: {error!r}")

        if owner.writer.failure is None:
            with _OWNER_LOCK:
                if _OWNER is owner:
                    _OWNER = None
        if failure is not None:
            raise failure


def run_with_logging_shutdown(action: Callable[[], _ResultT]) -> _ResultT:
    """Runs one process-level action and surfaces final sink failures before success returns."""

    try:
        result = action()
    except BaseException as error:
        try:
            shutdown_logging()
        except BaseException as shutdown_error:
            error.add_note(f"Logging shutdown also failed: {shutdown_error!r}")
        raise
    shutdown_logging()
    return result


def _write_async_batch(records: Sequence[_QueuedDiagnosticRecord]) -> None:
    """Dispatches accepted records in FIFO order and lets configured handler errors reach the writer."""

    token = _ASYNC_HANDLER_DELIVERY.set(True)
    try:
        for queued_record in records:
            queued_record.logger.handle(queued_record.record)
    finally:
        _ASYNC_HANDLER_DELIVERY.reset(token)


atexit.register(shutdown_logging)
