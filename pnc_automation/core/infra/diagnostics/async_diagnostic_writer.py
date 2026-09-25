"""Bounded single-consumer delivery for prepared diagnostic records."""

from __future__ import annotations

import math
import queue
import threading
import time
from collections.abc import Callable, Sequence
from typing import Generic, TypeVar, cast

RecordT = TypeVar("RecordT")
_BATCH_DEADLINE = object()
_STOP = object()


class AsyncDiagnosticWriterError(RuntimeError):
    """Raised when the asynchronous diagnostic writer has failed."""


class AsyncDiagnosticWriterClosedError(RuntimeError):
    """Raised when a record is submitted after the writer starts closing."""


class DiagnosticWriterBackpressureError(TimeoutError):
    """Raised when the bounded queue stays full for the admission timeout."""


class AsyncDiagnosticWriter(Generic[RecordT]):
    """Write accepted records in bounded FIFO batches on one consumer thread.

    The writer does not prepare, format, or otherwise interpret records. Its
    owner supplies the sink and must call :meth:`close` to drain accepted work
    and join the consumer.
    """

    def __init__(
        self,
        write_batch: Callable[[Sequence[RecordT]], None],
        *,
        queue_capacity: int,
        max_batch_size: int,
        batch_interval: float,
        admission_timeout: float,
        _monotonic: Callable[[], float] = time.monotonic,
        _condition_wait: Callable[[threading.Condition, float | None], None] | None = None,
    ) -> None:
        """Start a writer with bounded queueing and timed batch dispatch."""

        if isinstance(queue_capacity, bool) or not isinstance(queue_capacity, int) or queue_capacity <= 0:
            raise ValueError("queue_capacity must be a positive integer")
        if isinstance(max_batch_size, bool) or not isinstance(max_batch_size, int) or max_batch_size <= 0:
            raise ValueError("max_batch_size must be a positive integer")
        self._validate_duration("batch_interval", batch_interval, allow_zero=False)
        self._validate_duration("admission_timeout", admission_timeout, allow_zero=True)

        self._write_batch = write_batch
        self._queue: queue.Queue[RecordT] = queue.Queue(maxsize=queue_capacity)
        self._max_batch_size = max_batch_size
        self._batch_interval = batch_interval
        self._admission_timeout = admission_timeout
        self._monotonic = _monotonic
        self._condition_wait = (
            _condition_wait if _condition_wait is not None else self._wait_for_condition
        )
        self._condition = threading.Condition()
        self._accepting = True
        self._closing = False
        self._closed = False
        self._failure: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run,
            name="async-diagnostic-writer",
            daemon=True,
        )
        self._thread.start()

    @staticmethod
    def _validate_duration(name: str, value: float, *, allow_zero: bool) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or (value == 0 and not allow_zero)
        ):
            qualifier = "non-negative" if allow_zero else "positive"
            raise ValueError(f"{name} must be finite and {qualifier}")

    @staticmethod
    def _wait_for_condition(condition: threading.Condition, timeout: float | None) -> None:
        condition.wait(timeout=timeout)

    @property
    def failure(self) -> BaseException | None:
        """Return the first latched sink or worker failure, if any."""

        with self._condition:
            return self._failure

    @property
    def is_alive(self) -> bool:
        """Return whether the single consumer thread is still running."""

        return self._thread.is_alive()

    @property
    def closed(self) -> bool:
        """Return whether the consumer thread has stopped."""

        with self._condition:
            return self._closed

    def submit(self, record: RecordT) -> None:
        """Accept one record or raise if the queue stays full too long."""

        deadline = self._monotonic() + self._admission_timeout
        with self._condition:
            while self._queue.full():
                self._raise_if_failed_locked()
                self._raise_if_closed_locked()
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise DiagnosticWriterBackpressureError(
                        "diagnostic writer queue remained full until the admission timeout"
                    )
                self._condition_wait(self._condition, remaining)

            self._raise_if_failed_locked()
            self._raise_if_closed_locked()
            self._queue.put_nowait(record)
            self._condition.notify_all()

    def close(self, *, timeout: float | None = None) -> None:
        """Stop admission, drain accepted records, and join the consumer.

        A timed-out close leaves the writer closing; a later call can wait for
        completion. Sink failures are raised after the consumer has stopped.
        """

        if timeout is not None:
            self._validate_duration("timeout", timeout, allow_zero=True)
        with self._condition:
            self._accepting = False
            self._closing = True
            self._condition.notify_all()

        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            raise TimeoutError("diagnostic writer did not drain before the close timeout")

        failure = self.failure
        if failure is not None:
            raise AsyncDiagnosticWriterError("asynchronous diagnostic writer failed") from failure

    def _raise_if_failed_locked(self) -> None:
        if self._failure is not None:
            raise AsyncDiagnosticWriterError("asynchronous diagnostic writer failed") from self._failure

    def _raise_if_closed_locked(self) -> None:
        if not self._accepting:
            raise AsyncDiagnosticWriterClosedError("diagnostic writer is closing or closed")

    def _next_item(self, deadline: float | None) -> RecordT | object:
        with self._condition:
            while True:
                try:
                    record = self._queue.get_nowait()
                except queue.Empty:
                    if self._closing:
                        return _STOP
                    if deadline is None:
                        self._condition_wait(self._condition, None)
                        continue
                    remaining = deadline - self._monotonic()
                    if remaining <= 0:
                        return _BATCH_DEADLINE
                    self._condition_wait(self._condition, remaining)
                else:
                    self._condition.notify_all()
                    return record

    def _run(self) -> None:
        batch: list[RecordT] = []
        deadline: float | None = None
        try:
            while True:
                item = self._next_item(deadline)
                if item is _STOP:
                    self._write_pending(batch)
                    break
                if item is _BATCH_DEADLINE:
                    self._write_pending(batch)
                    batch = []
                    deadline = None
                    continue

                if batch and deadline is not None and self._monotonic() >= deadline:
                    self._write_pending(batch)
                    batch = []
                    deadline = None

                batch.append(cast(RecordT, item))
                if len(batch) >= self._max_batch_size:
                    self._write_pending(batch)
                    batch = []
                    deadline = None
                elif deadline is None:
                    deadline = self._monotonic() + self._batch_interval
        except BaseException as error:
            self._latch_failure(error)
        finally:
            with self._condition:
                self._accepting = False
                self._closing = True
                self._closed = True
                self._condition.notify_all()

    def _write_pending(self, batch: list[RecordT]) -> None:
        if batch:
            self._write_batch(tuple(batch))

    def _latch_failure(self, error: BaseException) -> None:
        with self._condition:
            if self._failure is None:
                self._failure = error
            self._accepting = False
            self._closing = True
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._condition.notify_all()


__all__ = [
    "AsyncDiagnosticWriter",
    "AsyncDiagnosticWriterClosedError",
    "AsyncDiagnosticWriterError",
    "DiagnosticWriterBackpressureError",
]
