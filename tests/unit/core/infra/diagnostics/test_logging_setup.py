"""Privacy-safe JSON exception serialization tests."""

from __future__ import annotations

import io
import json
import logging
import sys
import unittest
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from pnc_automation.core.infra.diagnostics.logging_setup import JsonLogFormatter, configure_logging

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


if __name__ == "__main__":
    unittest.main()
