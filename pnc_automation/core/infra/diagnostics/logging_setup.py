"""Structured logging configuration for automation runs."""

from __future__ import annotations

import json
import logging
import re
import traceback
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Formats log records as compact JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        """Serializes the record, structured extras, and sanitized exception context."""

        payload: dict[str, Any] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
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
    """Configures JSON-line diagnostics, optionally with a bounded state-root log."""

    root_logger = logging.getLogger("pnc_automation")
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    for existing_handler in root_logger.handlers:
        existing_handler.close()
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(handler)
    if log_file_root is not None:
        log_file_root.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file_root / "bluestacks_management.jsonl",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(JsonLogFormatter())
        root_logger.addHandler(file_handler)
    root_logger.propagate = False
    return root_logger
