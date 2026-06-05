"""Shared buffered diagnostics logging tests."""

from __future__ import annotations

import logging
import unittest

from pnc_automation.core.infra.diagnostics.buffered_logging import (
    DiagnosticLogMode,
    emit_diagnostic_log,
    flush_buffered_diagnostic_logs,
)


class BufferedLoggingTests(unittest.TestCase):
    """Validates the shared immediate-vs-buffered structured logging helper."""

    def test_immediate_mode_writes_through_without_buffering(self) -> None:
        """Leaves immediate logging behavior unchanged for normal runtime flows."""

        logger, records = _build_logger()

        emit_diagnostic_log(
            logger=logger,
            runtime_state={},
            mode=DiagnosticLogMode.IMMEDIATE,
            level=logging.INFO,
            message="immediate_event",
            extra={"step_index": 1},
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].msg, "immediate_event")
        self.assertEqual(records[0].step_index, 1)

    def test_buffered_mode_flushes_in_sequence_order(self) -> None:
        """Buffers sequence logs until the caller explicitly flushes the completed traversal."""

        logger, records = _build_logger()
        runtime_state: dict[str, object] = {}

        emit_diagnostic_log(
            logger=logger,
            runtime_state=runtime_state,
            mode=DiagnosticLogMode.BUFFERED_SEQUENCE,
            level=logging.INFO,
            message="first",
            extra={"step_index": 0},
        )
        emit_diagnostic_log(
            logger=logger,
            runtime_state=runtime_state,
            mode=DiagnosticLogMode.BUFFERED_SEQUENCE,
            level=logging.INFO,
            message="second",
            extra={"step_index": 1},
        )

        self.assertEqual(records, [])
        flush_buffered_diagnostic_logs(logger=logger, runtime_state=runtime_state)
        self.assertEqual([record.msg for record in records], ["first", "second"])
        self.assertEqual([record.step_index for record in records], [0, 1])


def _build_logger() -> tuple[logging.LoggerAdapter, list[logging.LogRecord]]:
    """Builds one in-memory logger adapter plus the emitted records list."""

    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("pnc_automation.tests.buffered_logging")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(_ListHandler())
    return logging.LoggerAdapter(logger, extra={}), records


if __name__ == "__main__":
    unittest.main()
