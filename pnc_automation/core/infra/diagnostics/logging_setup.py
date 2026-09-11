"""Structured logging configuration for automation runs."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
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
