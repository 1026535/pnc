"""Shared immediate and asynchronous diagnostics logging tests."""

from __future__ import annotations

import json
import logging
import threading
import unittest
from datetime import UTC, datetime
from typing import Any

from pnc_automation.core.infra.diagnostics.buffered_logging import DiagnosticLogMode, emit_diagnostic_log
from pnc_automation.core.infra.diagnostics.logging_setup import JsonLogFormatter, configure_logging, shutdown_logging


class BufferedLoggingTests(unittest.TestCase):
    """Validates producer-facing immediate and asynchronous structured logging behavior."""

    def setUp(self) -> None:
        configure_logging()

    def tearDown(self) -> None:
        shutdown_logging()

    def test_immediate_mode_writes_through_before_returning(self) -> None:
        """Leaves immediate logging synchronous for callers that need it."""

        logger, records, handler = _build_logger()
        self.addCleanup(_remove_logger_handler, logger.logger, handler)

        emit_diagnostic_log(
            logger=logger,
            mode=DiagnosticLogMode.IMMEDIATE,
            level=logging.INFO,
            message="immediate_event",
            extra={"step_index": 1},
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].msg, "immediate_event")
        self.assertEqual(records[0].step_index, 1)

    def test_async_queue_preserves_fifo_snapshot_and_producer_timestamp(self) -> None:
        """Queues prepared records once in order with merged extras copied at submission."""

        adapter_values: dict[str, Any] = {"items": ["adapter"]}
        event_values: dict[str, Any] = {"items": ["event"]}
        logger, records, _handler = _build_logger(
            extra={"source": "adapter", "adapter_detail": adapter_values}
        )
        self.addCleanup(_remove_logger_handler, logger.logger, _handler)

        emit_diagnostic_log(
            logger=logger,
            mode=DiagnosticLogMode.ASYNC_QUEUE,
            level=logging.INFO,
            message="first",
            extra={"step_index": 0, "source": "event", "event_detail": event_values},
        )
        emit_diagnostic_log(
            logger=logger,
            mode=DiagnosticLogMode.ASYNC_QUEUE,
            level=logging.INFO,
            message="second",
            extra={"step_index": 1},
        )
        adapter_values["items"].append("mutated")
        event_values["items"].append("mutated")
        self.assertEqual(records, [])

        shutdown_logging()

        self.assertEqual([record.msg for record in records], ["first", "second"])
        self.assertEqual([record.step_index for record in records], [0, 1])
        self.assertEqual(records[0].source, "event")
        self.assertEqual(records[0].adapter_detail, {"items": ["adapter"]})
        self.assertEqual(records[0].event_detail, {"items": ["event"]})
        expected_timestamp = datetime.fromtimestamp(records[0].created, tz=UTC).isoformat()
        payload = json.loads(JsonLogFormatter().format(records[0]))
        self.assertEqual(payload["timestamp"], expected_timestamp)

    def test_partial_async_batch_emits_without_a_later_submission(self) -> None:
        """Delivers a one-record partial batch when its batching deadline expires."""

        received = threading.Event()
        logger, records, handler = _build_logger(on_emit=received.set)
        self.addCleanup(_remove_logger_handler, logger.logger, handler)

        emit_diagnostic_log(
            logger=logger,
            mode=DiagnosticLogMode.ASYNC_QUEUE,
            level=logging.INFO,
            message="deadline_event",
        )

        self.assertTrue(received.wait(timeout=2))
        self.assertEqual([record.msg for record in records], ["deadline_event"])


def _build_logger(
    *,
    extra: dict[str, Any] | None = None,
    on_emit: Any = None,
) -> tuple[logging.LoggerAdapter, list[logging.LogRecord], logging.Handler]:
    """Builds a uniquely named in-memory logger adapter plus its records list."""

    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)
            if on_emit is not None:
                on_emit()

    logger = logging.getLogger(f"pnc_automation.tests.buffered_logging.{id(records)}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = _ListHandler()
    logger.addHandler(handler)
    return logging.LoggerAdapter(logger, extra=extra), records, handler


def _remove_logger_handler(logger: logging.Logger, handler: logging.Handler) -> None:
    """Removes and closes one in-memory test sink after the configured writer drains."""

    logger.removeHandler(handler)
    handler.close()


if __name__ == "__main__":
    unittest.main()
