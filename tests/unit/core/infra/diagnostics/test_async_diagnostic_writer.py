"""Concurrency and lifecycle tests for the bounded diagnostic writer."""

from __future__ import annotations

import queue
import threading
import unittest
from collections.abc import Sequence

from pnc_automation.core.infra.diagnostics.async_diagnostic_writer import (
    AsyncDiagnosticWriter,
    AsyncDiagnosticWriterClosedError,
    AsyncDiagnosticWriterError,
    DiagnosticWriterBackpressureError,
)


class _ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, amount: float) -> None:
        self.value += amount


class _ControlledConditionWait:
    """Lets tests advance writer deadlines without wall-clock sleeps."""

    def __init__(self) -> None:
        self.timeouts: queue.Queue[float] = queue.Queue()

    def __call__(self, condition: threading.Condition, timeout: float | None) -> None:
        if timeout is not None:
            self.timeouts.put(timeout)
        condition.wait()

    def next_timeout(self) -> float:
        return self.timeouts.get(timeout=2)

    def advance(
        self,
        condition: threading.Condition,
        clock: _ManualClock,
        amount: float,
    ) -> None:
        with condition:
            clock.advance(amount)
            condition.notify_all()


class _ObservedConditionWait:
    """Signals when a producer is waiting for bounded queue capacity."""

    def __init__(self) -> None:
        self.waiting = threading.Event()

    def __call__(self, condition: threading.Condition, timeout: float | None) -> None:
        if timeout is not None:
            self.waiting.set()
        condition.wait(timeout=timeout)


class AsyncDiagnosticWriterTests(unittest.TestCase):
    """Proves FIFO batching, backpressure, deadlines, and shutdown behavior."""

    def test_count_batches_are_bounded_fifo_and_use_one_consumer(self) -> None:
        batches: list[tuple[int, ...]] = []
        consumer_ids: set[int] = set()
        first_batch_written = threading.Event()

        def write_batch(records: Sequence[int]) -> None:
            batches.append(tuple(records))
            consumer_ids.add(threading.get_ident())
            if len(batches) == 1:
                first_batch_written.set()

        writer = AsyncDiagnosticWriter(
            write_batch,
            queue_capacity=8,
            max_batch_size=2,
            batch_interval=60,
            admission_timeout=0.1,
        )
        for record in range(2):
            writer.submit(record)
        self.assertTrue(first_batch_written.wait(2))
        self.assertEqual([(0, 1)], batches)

        for record in range(2, 5):
            writer.submit(record)

        writer.close(timeout=2)

        self.assertEqual([(0, 1), (2, 3), (4,)], batches)
        self.assertEqual(1, len(consumer_ids))
        self.assertFalse(writer.is_alive)
        self.assertTrue(writer.closed)
        with self.assertRaises(AsyncDiagnosticWriterClosedError):
            writer.submit(5)

    def test_oldest_record_deadline_flushes_partial_batch_despite_trickle(self) -> None:
        clock = _ManualClock()
        waiter = _ControlledConditionWait()
        written = threading.Event()
        batches: list[tuple[str, ...]] = []

        def write_batch(records: Sequence[str]) -> None:
            batches.append(tuple(records))
            written.set()

        writer = AsyncDiagnosticWriter(
            write_batch,
            queue_capacity=4,
            max_batch_size=4,
            batch_interval=10,
            admission_timeout=0.1,
            _monotonic=clock,
            _condition_wait=waiter,
        )
        try:
            writer.submit("first")
            self.assertEqual(10, waiter.next_timeout())

            with writer._condition:
                clock.advance(4)
                writer.submit("second")
            self.assertEqual(6, waiter.next_timeout())

            with writer._condition:
                clock.advance(4)
                writer.submit("third")
            self.assertEqual(2, waiter.next_timeout())

            waiter.advance(writer._condition, clock, 2)
            self.assertTrue(written.wait(2))
        finally:
            writer.close(timeout=2)

        self.assertEqual([("first", "second", "third")], batches)

    def test_expired_batch_deadline_flushes_before_draining_queued_records(self) -> None:
        clock = _ManualClock()
        waiter = _ControlledConditionWait()
        first_batch_written = threading.Event()
        batches: list[tuple[str, ...]] = []

        def write_batch(records: Sequence[str]) -> None:
            batches.append(tuple(records))
            if len(batches) == 1:
                first_batch_written.set()

        writer = AsyncDiagnosticWriter(
            write_batch,
            queue_capacity=4,
            max_batch_size=4,
            batch_interval=10,
            admission_timeout=0.1,
            _monotonic=clock,
            _condition_wait=waiter,
        )
        try:
            writer.submit("first")
            self.assertEqual(10, waiter.next_timeout())

            with writer._condition:
                clock.advance(10)
                writer.submit("later-1")
                writer.submit("later-2")
                writer.submit("later-3")

            self.assertTrue(first_batch_written.wait(2))
            self.assertEqual([("first",)], batches)
        finally:
            writer.close(timeout=2)

        self.assertEqual(
            [("first",), ("later-1", "later-2", "later-3")],
            batches,
        )

    def test_full_queue_times_out_without_replacing_accepted_record(self) -> None:
        sink_started = threading.Event()
        release_sink = threading.Event()
        batches: list[tuple[str, ...]] = []

        def write_batch(records: Sequence[str]) -> None:
            batch = tuple(records)
            batches.append(batch)
            if batch == ("first",):
                sink_started.set()
                if not release_sink.wait(2):
                    raise AssertionError("test did not release the blocked sink")

        writer = AsyncDiagnosticWriter(
            write_batch,
            queue_capacity=1,
            max_batch_size=1,
            batch_interval=60,
            admission_timeout=0,
        )
        writer.submit("first")
        self.assertTrue(sink_started.wait(2))
        writer.submit("kept")
        with self.assertRaises(DiagnosticWriterBackpressureError):
            writer.submit("rejected")

        release_sink.set()
        writer.close(timeout=2)

        self.assertEqual([("first",), ("kept",)], batches)

    def test_positive_admission_wait_accepts_record_when_capacity_frees(self) -> None:
        sink_started = threading.Event()
        release_sink = threading.Event()
        producer_done = threading.Event()
        waiter = _ObservedConditionWait()
        batches: list[tuple[str, ...]] = []
        producer_errors: list[BaseException] = []

        def write_batch(records: Sequence[str]) -> None:
            batch = tuple(records)
            batches.append(batch)
            if batch == ("first",):
                sink_started.set()
                if not release_sink.wait(2):
                    raise AssertionError("test did not release the blocked sink")

        writer = AsyncDiagnosticWriter(
            write_batch,
            queue_capacity=1,
            max_batch_size=1,
            batch_interval=60,
            admission_timeout=5,
            _condition_wait=waiter,
        )
        writer.submit("first")
        self.assertTrue(sink_started.wait(2))
        writer.submit("queued")

        def submit_when_space_frees() -> None:
            try:
                writer.submit("admitted")
            except BaseException as error:
                producer_errors.append(error)
            finally:
                producer_done.set()

        producer = threading.Thread(target=submit_when_space_frees)
        producer.start()
        try:
            self.assertTrue(waiter.waiting.wait(2))
            release_sink.set()
            self.assertTrue(producer_done.wait(2))
        finally:
            release_sink.set()
            producer.join(timeout=2)
            writer.close(timeout=2)

        self.assertFalse(producer.is_alive())
        self.assertEqual([], producer_errors)
        self.assertEqual([("first",), ("queued",), ("admitted",)], batches)

    def test_positive_admission_timeout_is_not_reset_by_notification(self) -> None:
        clock = _ManualClock()
        waiter = _ControlledConditionWait()
        sink_started = threading.Event()
        release_sink = threading.Event()
        producer_done = threading.Event()
        producer_errors: list[BaseException] = []
        batches: list[tuple[str, ...]] = []

        def write_batch(records: Sequence[str]) -> None:
            batch = tuple(records)
            batches.append(batch)
            if batch == ("first",):
                sink_started.set()
                if not release_sink.wait(2):
                    raise AssertionError("test did not release the blocked sink")

        writer = AsyncDiagnosticWriter(
            write_batch,
            queue_capacity=1,
            max_batch_size=1,
            batch_interval=60,
            admission_timeout=5,
            _monotonic=clock,
            _condition_wait=waiter,
        )
        writer.submit("first")
        self.assertTrue(sink_started.wait(2))
        writer.submit("kept")

        def submit_until_timeout() -> None:
            try:
                writer.submit("rejected")
            except BaseException as error:
                producer_errors.append(error)
            finally:
                producer_done.set()

        producer = threading.Thread(target=submit_until_timeout)
        producer.start()
        try:
            self.assertEqual(5, waiter.next_timeout())
            waiter.advance(writer._condition, clock, 0)
            self.assertEqual(5, waiter.next_timeout())
            waiter.advance(writer._condition, clock, 5)
            self.assertTrue(producer_done.wait(2))
        finally:
            release_sink.set()
            producer.join(timeout=2)
            writer.close(timeout=2)

        self.assertFalse(producer.is_alive())
        self.assertEqual(1, len(producer_errors))
        self.assertIsInstance(producer_errors[0], DiagnosticWriterBackpressureError)
        self.assertEqual([("first",), ("kept",)], batches)

    def test_sink_failure_is_latched_and_wakes_blocked_producers(self) -> None:
        sink_started = threading.Event()
        release_sink = threading.Event()
        producer_done = threading.Event()
        waiter = _ObservedConditionWait()
        sink_error = OSError("sink failed")
        batches: list[tuple[str, ...]] = []
        producer_errors: list[BaseException] = []

        def write_batch(records: Sequence[str]) -> None:
            batches.append(tuple(records))
            sink_started.set()
            if not release_sink.wait(2):
                raise AssertionError("test did not release the blocked sink")
            raise sink_error

        writer = AsyncDiagnosticWriter(
            write_batch,
            queue_capacity=1,
            max_batch_size=1,
            batch_interval=60,
            admission_timeout=5,
            _condition_wait=waiter,
        )
        writer.submit("failing")
        self.assertTrue(sink_started.wait(2))
        writer.submit("discarded after failure")

        def submit_while_full() -> None:
            try:
                writer.submit("blocked producer")
            except BaseException as error:
                producer_errors.append(error)
            finally:
                producer_done.set()

        producer = threading.Thread(target=submit_while_full)
        producer.start()
        self.assertTrue(waiter.waiting.wait(2))
        release_sink.set()

        self.assertTrue(producer_done.wait(2))
        producer.join(timeout=2)
        with self.assertRaises(AsyncDiagnosticWriterError) as shutdown_error:
            writer.close(timeout=2)
        with self.assertRaises(AsyncDiagnosticWriterError) as later_error:
            writer.submit("after failure")

        self.assertFalse(producer.is_alive())
        self.assertFalse(writer.is_alive)
        self.assertIs(sink_error, writer.failure)
        self.assertIs(sink_error, shutdown_error.exception.__cause__)
        self.assertIs(sink_error, later_error.exception.__cause__)
        self.assertEqual(1, len(producer_errors))
        self.assertIsInstance(producer_errors[0], AsyncDiagnosticWriterError)
        self.assertIs(sink_error, producer_errors[0].__cause__)
        self.assertEqual([("failing",)], batches)

    def test_close_drains_partial_batch_and_joins_consumer(self) -> None:
        batches: list[tuple[str, ...]] = []
        writer = AsyncDiagnosticWriter(
            lambda records: batches.append(tuple(records)),
            queue_capacity=2,
            max_batch_size=4,
            batch_interval=60,
            admission_timeout=0.1,
        )
        writer.submit("partial")

        writer.close(timeout=2)

        self.assertEqual([("partial",)], batches)
        self.assertTrue(writer.closed)
        self.assertFalse(writer.is_alive)

    def test_timed_out_close_rejects_waiting_producers_then_drains_on_retry(self) -> None:
        sink_started = threading.Event()
        release_sink = threading.Event()
        producer_done = threading.Event()
        waiter = _ObservedConditionWait()
        batches: list[tuple[str, ...]] = []
        producer_errors: list[BaseException] = []

        def write_batch(records: Sequence[str]) -> None:
            batch = tuple(records)
            batches.append(batch)
            if batch == ("first",):
                sink_started.set()
                if not release_sink.wait(2):
                    raise AssertionError("test did not release the blocked sink")

        writer = AsyncDiagnosticWriter(
            write_batch,
            queue_capacity=1,
            max_batch_size=1,
            batch_interval=60,
            admission_timeout=5,
            _condition_wait=waiter,
        )
        writer.submit("first")
        self.assertTrue(sink_started.wait(2))
        writer.submit("queued")

        def submit_after_close_starts() -> None:
            try:
                writer.submit("blocked")
            except BaseException as error:
                producer_errors.append(error)
            finally:
                producer_done.set()

        producer = threading.Thread(target=submit_after_close_starts)
        producer.start()
        try:
            self.assertTrue(waiter.waiting.wait(2))
            with self.assertRaises(TimeoutError):
                writer.close(timeout=0)

            self.assertTrue(producer_done.wait(2))
            self.assertEqual(1, len(producer_errors))
            self.assertIsInstance(producer_errors[0], AsyncDiagnosticWriterClosedError)
            with self.assertRaises(AsyncDiagnosticWriterClosedError):
                writer.submit("after close")

            release_sink.set()
            writer.close(timeout=2)
        finally:
            release_sink.set()
            producer.join(timeout=2)
            if writer.is_alive:
                writer.close(timeout=2)

        self.assertFalse(producer.is_alive())
        self.assertEqual([("first",), ("queued",)], batches)
        self.assertTrue(writer.closed)
        self.assertFalse(writer.is_alive)


if __name__ == "__main__":
    unittest.main()
