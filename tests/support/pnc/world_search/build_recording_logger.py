"""Synthetic build_recording_logger fixture."""

from __future__ import annotations

import logging



def _build_recording_logger(name: str) -> tuple[logging.LoggerAdapter, list[logging.LogRecord]]:
    """Builds one in-memory logger adapter plus the structured records it emits."""

    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(f"pnc_automation.tests.{name}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(_ListHandler())
    return logging.LoggerAdapter(logger, extra={}), records
