"""Structured logging configuration for automation runs."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Formats log records as compact JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        """Serializes the record and any structured extras."""

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


def configure_logging(*, verbose: bool = False) -> logging.Logger:
    """Configures the root logger for JSON-line automation diagnostics."""

    root_logger = logging.getLogger("pnc_automation")
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(handler)
    root_logger.propagate = False
    return root_logger
