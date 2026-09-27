"""Privacy-safe JSON exception serialization tests."""

from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
import tempfile
import threading
import unittest
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from pnc_automation.core.infra.diagnostics.buffered_logging import DiagnosticLogMode, emit_diagnostic_log
from pnc_automation.core.infra.diagnostics.logging_setup import (
    JsonLogFormatter,
    configure_logging,
    run_with_logging_shutdown,
    shutdown_logging,
)

from tests.support.paths import REPOSITORY_ROOT

SECRET_MESSAGE = "SECRET-MESSAGE-SENTINEL-9f4b"
SECRET_LOCAL = "SECRET-LOCAL-SENTINEL-71ac"
SECRET_DIRECTORY = "secret-dir-sentinel-52fd"
TEST_FILE_NAME = Path(__file__).name
TEST_DIRECTORY = str(Path(__file__).resolve().parent)


def _raise_secret_error() -> None:
    local_secret = SECRET_LOCAL
    raise ValueError(f"raised {SECRET_MESSAGE} with {local_secret}")


def _call_raising_helper() -> None:
    _raise_secret_error()


def _record(
    message: str = "diagnostic event",
    *,
    args: tuple[object, ...] = (),
    exc_info: Any = None,
    sinfo: str | None = None,
    **extras: Any,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="pnc_automation.test",
        level=logging.ERROR,
        pathname=str(Path(__file__).resolve()),
        lineno=1,
        msg=message,
        args=args,
        exc_info=exc_info,
        sinfo=sinfo,
    )
    for key, value in extras.items():
        setattr(record, key, value)
    return record


def _payload_strings(value: Any) -> Iterator[str]:
    """Yields every serialized key and string value inside a decoded payload."""

    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _payload_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _payload_strings(item)


class JsonLogFormatterTests(unittest.TestCase):
    """Proves JSON lines keep safe exception context without leaking secrets."""

    def _format(self, record: logging.LogRecord) -> tuple[str, dict[str, Any]]:
        line = JsonLogFormatter().format(record)
        self.assertNotIn("\n", line)
        return line, json.loads(line)

    def _raise_and_format(self, raiser: Callable[[], None]) -> tuple[str, dict[str, Any], logging.LogRecord]:
        try:
            raiser()
        except BaseException:
            record = _record("operation failed", exc_info=sys.exc_info())
        else:
            self.fail("expected the raiser to throw")
        line, payload = self._format(record)
        return line, payload, record

    def test_ordinary_record_emits_core_fields_without_exception_context(self) -> None:
        _line, payload = self._format(_record("cleanup %s finished", args=("daily",)))

        self.assertEqual("cleanup daily finished", payload["message"])
        self.assertEqual("ERROR", payload["level"])
        self.assertEqual("pnc_automation.test", payload["logger"])
        self.assertIn("timestamp", payload)
        self.assertNotIn("_exception", payload)
        self.assertNotIn("_stack", payload)

    def test_structured_extras_pass_through_while_reserved_fields_stay_out(self) -> None:
        line, payload = self._format(_record("event", castle_id="castle-1", attempt=3, note="line1\nline2"))

        self.assertEqual("castle-1", payload["castle_id"])
        self.assertEqual(3, payload["attempt"])
        self.assertEqual("line1\nline2", payload["note"])
        self.assertNotIn("\n", line)
        for reserved in ("pathname", "filename", "funcName", "lineno", "exc_info", "exc_text", "stack_info"):
            self.assertNotIn(reserved, payload)

    def test_exception_serializes_type_and_sanitized_frames(self) -> None:
        _line, payload, _record_out = self._raise_and_format(_call_raising_helper)

        exception = payload["_exception"]
        self.assertEqual("ValueError", exception["type"])
        frames = exception["frames"]
        self.assertEqual(
            ["_raise_and_format", "_call_raising_helper", "_raise_secret_error"],
            [frame["function"] for frame in frames],
        )
        for frame in frames:
            self.assertEqual({"file", "function", "line"}, set(frame))
            self.assertEqual(TEST_FILE_NAME, frame["file"])
            self.assertIsInstance(frame["line"], int)

    def test_exception_text_locals_and_paths_are_never_serialized(self) -> None:
        line, payload, _record_out = self._raise_and_format(_call_raising_helper)

        self.assertNotIn(SECRET_MESSAGE, line)
        self.assertNotIn(SECRET_LOCAL, line)
        serialized_strings = list(_payload_strings(payload))
        self.assertFalse(any(SECRET_MESSAGE in value or SECRET_LOCAL in value for value in serialized_strings))
        self.assertFalse(any(TEST_DIRECTORY in value for value in serialized_strings))
        self.assertNotIn(str(Path(__file__).resolve()), serialized_strings)

    def test_exception_frames_come_from_the_record_traceback(self) -> None:
        try:
            _call_raising_helper()
        except ValueError:
            exc_info = sys.exc_info()
        record = _record("captured", exc_info=exc_info)
        exc_info[1].__traceback__ = None

        _line, payload = self._format(record)

        exception = payload["_exception"]
        self.assertEqual("ValueError", exception["type"])
        functions = [frame["function"] for frame in exception["frames"]]
        self.assertEqual("_raise_secret_error", functions[-1])
        self.assertIn("_call_raising_helper", functions)

    def test_none_record_traceback_reports_no_frames_without_fallback(self) -> None:
        try:
            _call_raising_helper()
        except ValueError as error:
            record = _record("captured", exc_info=(type(error), error, None))

        _line, payload = self._format(record)

        self.assertEqual("ValueError", payload["_exception"]["type"])
        self.assertEqual([], payload["_exception"]["frames"])

    def test_explicit_cause_chain_preserves_chain_boundary(self) -> None:
        def raiser() -> None:
            try:
                _call_raising_helper()
            except ValueError:
                raise KeyError(SECRET_MESSAGE) from RuntimeError("hidden cause")

        _line, payload, _record_out = self._raise_and_format(raiser)

        exception = payload["_exception"]
        self.assertEqual("KeyError", exception["type"])
        self.assertEqual("raiser", exception["frames"][-1]["function"])
        self.assertEqual({"type": "RuntimeError", "frames": []}, exception["cause"])
        self.assertNotIn("context", exception)
        self.assertFalse(any(SECRET_MESSAGE in value for value in _payload_strings(payload)))

    def test_implicit_context_chain_preserves_chain_boundary(self) -> None:
        def raiser() -> None:
            try:
                _call_raising_helper()
            except ValueError:
                raise RuntimeError("outer failure")

        _line, payload, _record_out = self._raise_and_format(raiser)

        exception = payload["_exception"]
        self.assertEqual("RuntimeError", exception["type"])
        self.assertEqual("raiser", exception["frames"][-1]["function"])
        self.assertNotIn("cause", exception)
        context = exception["context"]
        self.assertEqual("ValueError", context["type"])
        context_functions = [frame["function"] for frame in context["frames"]]
        self.assertEqual("_raise_secret_error", context_functions[-1])
        self.assertIn("_call_raising_helper", context_functions)

    def test_stack_info_is_reduced_to_safe_frame_metadata(self) -> None:
        stack_info = (
            "Stack (most recent call last):\n"
            f'  File "C:\\{SECRET_DIRECTORY}\\runner.py", line 8, in outer_call\n'
            f'    token = "{SECRET_LOCAL}"\n'
            f'  File "{Path(__file__).resolve()}", line 42, in inner_call\n'
            f'    raise ValueError("{SECRET_MESSAGE}")\n'
        )

        line, payload = self._format(_record("with stack", sinfo=stack_info))

        self.assertEqual(
            [
                {"file": "runner.py", "function": "outer_call", "line": 8},
                {"file": TEST_FILE_NAME, "function": "inner_call", "line": 42},
            ],
            payload["_stack"],
        )
        self.assertNotIn(SECRET_DIRECTORY, line)
        self.assertNotIn(SECRET_LOCAL, line)
        self.assertNotIn(SECRET_MESSAGE, line)
        self.assertNotIn("token =", line)
        self.assertFalse(any(TEST_DIRECTORY in value for value in _payload_strings(payload)))

    def test_exc_info_without_active_exception_omits_exception(self) -> None:
        _line, payload = self._format(_record("no exception", exc_info=sys.exc_info()))

        self.assertNotIn("_exception", payload)

    def test_caller_extras_named_exception_and_stack_are_preserved(self) -> None:
        stack_info = (
            "Stack (most recent call last):\n"
            f'  File "{Path(__file__).resolve()}", line 42, in inner_call\n'
        )
        try:
            _call_raising_helper()
        except ValueError:
            record = _record(
                "collision check",
                exc_info=sys.exc_info(),
                sinfo=stack_info,
                exception="caller exception value",
                stack="caller stack value",
            )
        else:
            self.fail("expected the raiser to throw")

        _line, payload = self._format(record)

        self.assertEqual("caller exception value", payload["exception"])
        self.assertEqual("caller stack value", payload["stack"])
        self.assertEqual("ValueError", payload["_exception"]["type"])
        self.assertEqual(
            [{"file": TEST_FILE_NAME, "function": "inner_call", "line": 42}],
            payload["_stack"],
        )

    def test_exception_group_members_preserve_sanitized_errors(self) -> None:
        def raise_cleanup_error() -> None:
            local_secret = SECRET_LOCAL
            raise RuntimeError(f"raised {SECRET_MESSAGE} with {local_secret}")

        def raiser() -> None:
            errors: list[Exception] = []
            for raise_error in (_call_raising_helper, raise_cleanup_error):
                try:
                    raise_error()
                except Exception as error:
                    errors.append(error)
            raise ExceptionGroup(f"grouped {SECRET_MESSAGE}", errors)

        line, payload, _record_out = self._raise_and_format(raiser)

        exception = payload["_exception"]
        self.assertEqual("ExceptionGroup", exception["type"])
        self.assertEqual("raiser", exception["frames"][-1]["function"])
        members = exception["exceptions"]
        self.assertEqual(["ValueError", "RuntimeError"], [member["type"] for member in members])
        self.assertEqual("_raise_secret_error", members[0]["frames"][-1]["function"])
        self.assertEqual("raise_cleanup_error", members[1]["frames"][-1]["function"])
        serialized_strings = list(_payload_strings(payload))
        for secret in (SECRET_MESSAGE, SECRET_LOCAL):
            self.assertFalse(any(secret in value for value in serialized_strings))
        self.assertFalse(any(TEST_DIRECTORY in value for value in serialized_strings))
        self.assertNotIn(str(Path(__file__).resolve()), serialized_strings)

    def test_format_does_not_mutate_the_record(self) -> None:
        _line, _payload, record = self._raise_and_format(_call_raising_helper)
        before = dict(record.__dict__)

        self._format(record)

        self.assertEqual(before, record.__dict__)
        self.assertIsNone(record.exc_text)

    def test_logger_emit_serializes_stack_info_and_exception_lines(self) -> None:
        stream = io.StringIO()
        logger = logging.getLogger("pnc_automation.test_json_formatter")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(handler.close)

        logger.info("with stack", stack_info=True)
        try:
            _call_raising_helper()
        except ValueError:
            logger.error("with exception", exc_info=True)

        lines = stream.getvalue().splitlines()
        self.assertEqual(2, len(lines))
        stacked = json.loads(lines[0])
        stack = stacked["_stack"]
        self.assertEqual(
            "test_logger_emit_serializes_stack_info_and_exception_lines",
            stack[-1]["function"],
        )
        self.assertEqual(TEST_FILE_NAME, stack[-1]["file"])
        self.assertNotIn("_exception", stacked)
        failed = json.loads(lines[1])
        self.assertEqual("ValueError", failed["_exception"]["type"])
        self.assertNotIn(SECRET_MESSAGE, lines[1])
        self.assertNotIn(SECRET_LOCAL, lines[1])

    def test_configure_logging_handler_emits_exception_json_line(self) -> None:
        isolated_logger = logging.Logger("pnc_automation.test_configure_logging")
        with mock.patch.object(logging, "getLogger", return_value=isolated_logger):
            logger = configure_logging()
        self.assertIs(logger, isolated_logger)
        handler = logger.handlers[0]
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(handler.close)
        stream = io.StringIO()
        handler.stream = stream

        try:
            _call_raising_helper()
        except ValueError:
            logger.error("artifact failure", exc_info=True)

        output = stream.getvalue()
        self.assertEqual(1, len(output.splitlines()))
        payload = json.loads(output)
        self.assertEqual("artifact failure", payload["message"])
        self.assertEqual("ValueError", payload["_exception"]["type"])
        self.assertEqual("_raise_secret_error", payload["_exception"]["frames"][-1]["function"])
        self.assertNotIn(SECRET_MESSAGE, output)
        self.assertNotIn(SECRET_LOCAL, output)
        self.addCleanup(shutdown_logging)


class LoggingLifecycleTests(unittest.TestCase):
    """Validates the configured writer's sink ownership and shutdown contract."""

    def setUp(self) -> None:
        shutdown_logging()
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.addCleanup(shutdown_logging)

    def test_identical_configuration_reuses_writer_and_reconfiguration_drains_old_sinks(self) -> None:
        """Reuses one healthy owner and finishes its accepted records before replacing sinks."""

        import pnc_automation.core.infra.diagnostics.logging_setup as logging_setup

        old_root = Path(self.temp_directory.name) / "old"
        new_root = Path(self.temp_directory.name) / "new"
        logger = configure_logging(log_file_root=old_root)
        old_owner = logging_setup._OWNER
        self.assertIsNotNone(old_owner)
        old_writer = old_owner.writer
        stream = io.StringIO()
        old_owner.handlers[0].stream = stream

        same_logger = configure_logging(log_file_root=Path(str(old_root)))
        self.assertIs(same_logger, logger)
        self.assertIs(logging_setup._OWNER.writer, old_writer)

        emit_diagnostic_log(
            logger=logging.LoggerAdapter(logger, extra={}),
            mode=DiagnosticLogMode.ASYNC_QUEUE,
            level=logging.INFO,
            message="old_sink_record",
        )
        new_logger = configure_logging(log_file_root=new_root)
        new_owner = logging_setup._OWNER

        self.assertIs(new_logger, logger)
        self.assertIsNotNone(new_owner)
        self.assertIsNot(new_owner.writer, old_writer)
        self.assertTrue(old_writer.closed)
        self.assertEqual(1, len(stream.getvalue().splitlines()))
        old_file_lines = (old_root / "bluestacks_management.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual("old_sink_record", json.loads(old_file_lines[0])["message"])

        new_stream = io.StringIO()
        new_owner.handlers[0].stream = new_stream
        emit_diagnostic_log(
            logger=logging.LoggerAdapter(new_logger, extra={}),
            mode=DiagnosticLogMode.ASYNC_QUEUE,
            level=logging.INFO,
            message="new_sink_record",
        )
        shutdown_logging()
        self.assertEqual("new_sink_record", json.loads(new_stream.getvalue())["message"])

    def test_producers_do_not_wait_for_sink_drain_under_the_owner_lock(self) -> None:
        """Allows a producer to observe closed admission while shutdown waits on a blocked sink."""

        import pnc_automation.core.infra.diagnostics.logging_setup as logging_setup

        from pnc_automation.core.infra.diagnostics.async_diagnostic_writer import AsyncDiagnosticWriterClosedError

        sink_entered = threading.Event()
        release_sink = threading.Event()
        close_entered = threading.Event()
        shutdown_errors: list[BaseException] = []
        producer_errors: list[BaseException] = []
        producer_finished = threading.Event()

        class GatedStream:
            def write(self, _value: str) -> None:
                sink_entered.set()
                if not release_sink.wait(timeout=3):
                    raise TimeoutError("test sink was not released")

            def flush(self) -> None:
                pass

        with (
            mock.patch.object(logging_setup, "_QUEUE_CAPACITY", 1),
            mock.patch.object(logging_setup, "_MAX_BATCH_SIZE", 1),
            mock.patch.object(logging_setup, "_ADMISSION_TIMEOUT_SECONDS", 0.1),
        ):
            logger = configure_logging()
            owner = logging_setup._OWNER
            self.assertIsNotNone(owner)
            writer = owner.writer
            owner.handlers[0].stream = GatedStream()

            class CloseSignalingWriter:
                def submit(self, record: Any) -> None:
                    writer.submit(record)

                def close(self) -> None:
                    try:
                        writer.close(timeout=0)
                    except TimeoutError:
                        pass
                    close_entered.set()
                    writer.close()

                @property
                def failure(self) -> BaseException | None:
                    return writer.failure

                @property
                def closed(self) -> bool:
                    return writer.closed

            owner.writer = CloseSignalingWriter()
            adapter = logging.LoggerAdapter(logger, extra={})

            def submit(message: str) -> None:
                emit_diagnostic_log(
                    logger=adapter,
                    mode=DiagnosticLogMode.ASYNC_QUEUE,
                    level=logging.INFO,
                    message=message,
                )

            submit("blocked_sink_record")
            self.assertTrue(sink_entered.wait(timeout=2))
            submit("queued_record")

            def shutdown() -> None:
                try:
                    shutdown_logging()
                except BaseException as error:
                    shutdown_errors.append(error)

            shutdown_thread = threading.Thread(target=shutdown, daemon=True)
            shutdown_thread.start()
            self.assertTrue(close_entered.wait(timeout=2))

            def submit_after_close() -> None:
                try:
                    submit("rejected_record")
                except BaseException as error:
                    producer_errors.append(error)
                finally:
                    producer_finished.set()

            producer_thread = threading.Thread(target=submit_after_close, daemon=True)
            producer_thread.start()
            try:
                self.assertTrue(
                    producer_finished.wait(timeout=0.5),
                    "producer waited for the sink drain instead of observing closed admission",
                )
                self.assertEqual(1, len(producer_errors))
                self.assertIsInstance(producer_errors[0], AsyncDiagnosticWriterClosedError)
            finally:
                release_sink.set()
                shutdown_thread.join(timeout=2)
                producer_thread.join(timeout=2)

            self.assertFalse(shutdown_thread.is_alive())
            self.assertFalse(producer_thread.is_alive())
            self.assertEqual([], shutdown_errors)

    def test_process_boundary_propagates_a_final_batch_sink_failure(self) -> None:
        """Returns a failing process status when the final queued record fails during explicit shutdown."""

        result = subprocess.run(
            [sys.executable, "-c", _PROCESS_EXIT_FAILURE_CHECK],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("AsyncDiagnosticWriterError", result.stderr)

    def test_process_boundary_preserves_the_application_error_when_shutdown_fails(self) -> None:
        """Keeps an active application error primary when explicit logging shutdown also fails."""

        from pnc_automation.core.infra.diagnostics.async_diagnostic_writer import AsyncDiagnosticWriterError

        application_error = RuntimeError("movement failed")
        shutdown_error = AsyncDiagnosticWriterError("sink failed")

        def fail_application() -> int:
            raise application_error

        with mock.patch(
            "pnc_automation.core.infra.diagnostics.logging_setup.shutdown_logging",
            side_effect=shutdown_error,
        ):
            with self.assertRaises(RuntimeError) as raised:
                run_with_logging_shutdown(fail_application)

        self.assertIs(raised.exception, application_error)
        self.assertTrue(any("Logging shutdown also failed" in note for note in application_error.__notes__))

    def test_async_record_reaches_each_configured_sink_once(self) -> None:
        """Routes a queued record once to both the owned stream and JSONL file handlers."""

        root = Path(self.temp_directory.name) / "sinks"
        logger = configure_logging(log_file_root=root)
        import pnc_automation.core.infra.diagnostics.logging_setup as logging_setup

        owner = logging_setup._OWNER
        stream = io.StringIO()
        owner.handlers[0].stream = stream

        emit_diagnostic_log(
            logger=logging.LoggerAdapter(logger, extra={}),
            mode=DiagnosticLogMode.ASYNC_QUEUE,
            level=logging.INFO,
            message="once_per_sink",
            extra={"step_index": 3},
        )
        shutdown_logging()

        stream_lines = stream.getvalue().splitlines()
        file_lines = (root / "bluestacks_management.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, len(stream_lines))
        self.assertEqual(1, len(file_lines))
        self.assertEqual("once_per_sink", json.loads(stream_lines[0])["message"])
        self.assertEqual("once_per_sink", json.loads(file_lines[0])["message"])

    def test_handler_failure_is_reported_and_latched_when_raise_exceptions_is_false(self) -> None:
        """Ensures a real handler failure reaches shutdown and rejects later submissions."""

        result = subprocess.run(
            [sys.executable, "-c", _HANDLER_FAILURE_CHECK],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_process_exit_drains_partial_batch_before_standard_logging_shutdown(self) -> None:
        """Uses the atexit owner to persist a partial batch before stdlib closes its handlers."""

        root = Path(self.temp_directory.name) / "process_exit"
        result = subprocess.run(
            [sys.executable, "-c", _PROCESS_EXIT_CHECK, str(root)],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        lines = (root / "bluestacks_management.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, len(lines))
        self.assertEqual("process_exit_record", json.loads(lines[0])["message"])


_HANDLER_FAILURE_CHECK = """
import logging
from pnc_automation.core.infra.diagnostics.async_diagnostic_writer import AsyncDiagnosticWriterError
from pnc_automation.core.infra.diagnostics.buffered_logging import DiagnosticLogMode, emit_diagnostic_log
from pnc_automation.core.infra.diagnostics import logging_setup

class FailingStream:
    def write(self, _value):
        raise OSError('expected sink failure')
    def flush(self):
        pass

logger = logging_setup.configure_logging()
owner = logging_setup._OWNER
owner.handlers[0].stream = FailingStream()
logging.raiseExceptions = False
emit_diagnostic_log(logger=logging.LoggerAdapter(logger, extra={}), mode=DiagnosticLogMode.ASYNC_QUEUE, level=logging.INFO, message='fails at sink')
try:
    logging_setup.shutdown_logging()
except AsyncDiagnosticWriterError as error:
    assert isinstance(error.__cause__, OSError)
else:
    raise AssertionError('shutdown did not report the asynchronous sink failure')
try:
    emit_diagnostic_log(logger=logging.LoggerAdapter(logger, extra={}), mode=DiagnosticLogMode.ASYNC_QUEUE, level=logging.INFO, message='later submit')
except AsyncDiagnosticWriterError:
    pass
else:
    raise AssertionError('later submission did not report the latched failure')
logging_setup._OWNER = None
"""


_PROCESS_EXIT_CHECK = """
import logging
from pathlib import Path
import sys
from pnc_automation.core.infra.diagnostics import logging_setup
from pnc_automation.core.infra.diagnostics.buffered_logging import DiagnosticLogMode, emit_diagnostic_log

logging_setup._BATCH_INTERVAL_SECONDS = 60
logger = logging_setup.configure_logging(log_file_root=Path(sys.argv[1]))
emit_diagnostic_log(logger=logging.LoggerAdapter(logger, extra={}), mode=DiagnosticLogMode.ASYNC_QUEUE, level=logging.INFO, message='process_exit_record')
"""


_PROCESS_EXIT_FAILURE_CHECK = """
import logging
from pnc_automation.core.infra.diagnostics import logging_setup
from pnc_automation.core.infra.diagnostics.buffered_logging import DiagnosticLogMode, emit_diagnostic_log

class FailingStream:
    def write(self, _value):
        raise OSError('expected final-batch sink failure')
    def flush(self):
        pass

logging_setup._BATCH_INTERVAL_SECONDS = 60
logger = logging_setup.configure_logging()
logging_setup._OWNER.handlers[0].stream = FailingStream()
emit_diagnostic_log(logger=logging.LoggerAdapter(logger, extra={}), mode=DiagnosticLogMode.ASYNC_QUEUE, level=logging.INFO, message='final_batch_record')
logging_setup.run_with_logging_shutdown(lambda: 0)
"""


if __name__ == "__main__":
    unittest.main()
