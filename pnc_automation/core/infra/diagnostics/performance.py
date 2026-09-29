"""Opt-in, run-scoped performance spans and local JSON reports."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import logging
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from threading import Lock, get_ident
from time import perf_counter_ns, process_time_ns, thread_time_ns
from typing import Iterator, Mapping, TypeAlias
from uuid import uuid4

PerformanceValue: TypeAlias = str | int | float | bool | None
_ACTIVE_RUN: ContextVar[PerformanceRun | None] = ContextVar("pnc_performance_run", default=None)
_ACTIVE_SPANS: ContextVar[tuple[tuple[str, str], ...]] = ContextVar("pnc_performance_spans", default=())
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PerformanceSpanRecord:
    """One completed inclusive timing span."""

    span_id: str
    parent_id: str | None
    name: str
    thread_id: int
    started_ns: int
    duration_seconds: float
    thread_cpu_seconds: float
    outcome: str
    error_type: str | None
    attributes: dict[str, PerformanceValue]


@dataclass(slots=True)
class _PerformanceSpan:
    """Mutable handle used while a span is open."""

    span_id: str
    attributes: dict[str, PerformanceValue] = field(default_factory=dict)

    def set_attribute(self, name: str, value: PerformanceValue) -> None:
        """Adds a small, JSON-safe measurement attribute."""

        if not name or not isinstance(value, (str, int, float, bool, type(None))):
            raise TypeError("performance span attributes require a name and a JSON scalar value")
        self.attributes[name] = value


class PerformanceReportWriter:
    """Writes one atomic JSON summary per opted-in workflow run."""

    def __init__(self, output_directory: Path) -> None:
        """Configure the local-only report directory."""

        self.output_directory = output_directory

    @classmethod
    def from_environment(cls, output_directory: Path) -> PerformanceReportWriter | None:
        """Enable collection only when the explicit opt-in variable is set."""

        enabled = os.environ.get("PNC_PERFORMANCE_REPORTS", "").strip().lower()
        return cls(output_directory) if enabled in {"1", "true", "yes"} else None

    def begin_run(
        self,
        workflow: str,
        *,
        attributes: Mapping[str, PerformanceValue] | None = None,
    ) -> PerformanceRun:
        """Starts a report whose duration includes subsequent setup and cleanup."""

        return PerformanceRun(self, workflow, attributes=attributes)

    def write(self, *, run_id: str, started_at: datetime, workflow: str, document: dict[str, object]) -> Path:
        """Atomically writes one unique report beneath the configured directory."""

        self.output_directory.mkdir(parents=True, exist_ok=True)
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        target = self.output_directory / f"{timestamp}_{workflow}_{run_id}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(target)
        return target


class PerformanceRun:
    """Collects thread-safe nested spans for one workflow run."""

    def __init__(
        self,
        writer: PerformanceReportWriter,
        workflow: str,
        *,
        attributes: Mapping[str, PerformanceValue] | None = None,
    ) -> None:
        """Begin timing immediately so callers can include construction work."""

        if not workflow or not workflow.replace("_", "").replace("-", "").isalnum():
            raise ValueError("workflow must be a non-empty filesystem-safe identifier")
        self.writer = writer
        self.run_id = uuid4().hex
        self.workflow = workflow
        self.started_at = datetime.now(tz=UTC)
        self._started_ns = perf_counter_ns()
        self._process_cpu_started_ns = process_time_ns()
        self._attributes = _validated_attributes(attributes or {})
        self._attributes.setdefault("core_trace_available", False)
        self._spans: list[PerformanceSpanRecord] = []
        self._spans_lock = Lock()
        self._finished = False
        self.report_path: Path | None = None

    @contextmanager
    def activate(self) -> Iterator[PerformanceRun]:
        """Make this run visible to instrumented owners in the current context."""

        token: Token[PerformanceRun | None] = _ACTIVE_RUN.set(self)
        try:
            yield self
        finally:
            _ACTIVE_RUN.reset(token)

    def set_attribute(self, name: str, value: PerformanceValue) -> None:
        """Adds a run-level correlation field before the report is finalized."""

        if not name or not isinstance(value, (str, int, float, bool, type(None))):
            raise TypeError("performance run attributes require a name and a JSON scalar value")
        with self._spans_lock:
            if self._finished:
                raise RuntimeError("cannot update a finished performance run")
            self._attributes[name] = value

    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: Mapping[str, PerformanceValue] | None = None,
    ) -> Iterator[_PerformanceSpan]:
        """Record inclusive wall and host-thread CPU time, retaining failures."""

        if not name:
            raise ValueError("performance span name cannot be empty")
        stack = _ACTIVE_SPANS.get()
        span_id = uuid4().hex
        parent_id = stack[-1][1] if stack and stack[-1][0] == self.run_id else None
        span = _PerformanceSpan(span_id, _validated_attributes(attributes or {}))
        started_ns = perf_counter_ns()
        thread_cpu_started_ns = thread_time_ns()
        stack_token = _ACTIVE_SPANS.set(stack + ((self.run_id, span_id),))
        outcome = "success"
        error_type: str | None = None
        try:
            yield span
        except BaseException as error:
            outcome = "error"
            error_type = type(error).__name__
            raise
        finally:
            _ACTIVE_SPANS.reset(stack_token)
            record = PerformanceSpanRecord(
                span_id=span_id,
                parent_id=parent_id,
                name=name,
                thread_id=get_ident(),
                started_ns=started_ns,
                duration_seconds=(perf_counter_ns() - started_ns) / 1_000_000_000,
                thread_cpu_seconds=(thread_time_ns() - thread_cpu_started_ns) / 1_000_000_000,
                outcome=outcome,
                error_type=error_type,
                attributes=dict(span.attributes),
            )
            with self._spans_lock:
                self._spans.append(record)

    def finish(self, outcome: str) -> Path | None:
        """Finalize once; report I/O failures without changing workflow behavior."""

        with self._spans_lock:
            if self._finished:
                return self.report_path
            self._finished = True
            spans = sorted(self._spans, key=lambda span: span.started_ns)
        if outcome == "success" and any(
            span.name in {"core.workflow", "script.execution"} and span.outcome == "error"
            for span in spans
        ):
            outcome = "error"

        ended_ns = perf_counter_ns()
        document: dict[str, object] = {
            "schema_version": 1,
            "run_id": self.run_id,
            "workflow": self.workflow,
            "started_at_utc": self.started_at.isoformat(),
            "elapsed_seconds": (ended_ns - self._started_ns) / 1_000_000_000,
            "host_process_cpu_seconds": (process_time_ns() - self._process_cpu_started_ns) / 1_000_000_000,
            "outcome": outcome,
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor() or None,
                "repository": _repository_metadata(self.writer.output_directory),
                "dependencies": _dependency_versions(),
            },
            "attributes": self._attributes,
            "spans": [
                {
                    "span_id": span.span_id,
                    "parent_id": span.parent_id,
                    "name": span.name,
                    "thread_id": span.thread_id,
                    "started_ns": span.started_ns,
                    "duration_seconds": span.duration_seconds,
                    "thread_cpu_seconds": span.thread_cpu_seconds,
                    "outcome": span.outcome,
                    "error_type": span.error_type,
                    "attributes": span.attributes,
                }
                for span in spans
            ],
        }
        try:
            self.report_path = self.writer.write(
                run_id=self.run_id,
                started_at=self.started_at,
                workflow=self.workflow,
                document=document,
            )
        except OSError:
            _LOGGER.warning("Could not write local performance report for %s", self.workflow, exc_info=True)
        return self.report_path


def current_performance_run() -> PerformanceRun | None:
    """Return the report active in this execution context, if any."""

    return _ACTIVE_RUN.get()


def performance_span(
    name: str,
    *,
    attributes: Mapping[str, PerformanceValue] | None = None,
):
    """Return a measured span or a zero-work context manager when disabled."""

    run = current_performance_run()
    return nullcontext(None) if run is None else run.span(name, attributes=attributes)


def performance_wait(
    reason: str,
    seconds: float,
    sleep: Callable[[float], None],
    *,
    span_name: str = "navigation.wait",
) -> None:
    """Runs one explicit wait and records its requested and measured duration when enabled."""

    if current_performance_run() is None:
        sleep(seconds)
        return
    started = time.perf_counter()
    with performance_span(
        span_name,
        attributes={"reason": reason, "requested_seconds": seconds},
    ) as measured:
        sleep(seconds)
        if measured is not None:
            measured.set_attribute("actual_seconds", time.perf_counter() - started)


@contextmanager
def performance_run_scope(
    writer: PerformanceReportWriter | None,
    workflow: str,
    *,
    attributes: Mapping[str, PerformanceValue] | None = None,
) -> Iterator[PerformanceRun | None]:
    """Start a root report or add a nested workflow span to the active report."""

    active = current_performance_run()
    if active is not None:
        with active.span("workflow", attributes={"name": workflow}):
            yield active
        return
    if writer is None:
        yield None
        return
    run = writer.begin_run(workflow, attributes=attributes)
    with run.activate():
        try:
            yield run
        except BaseException:
            run.finish("error")
            raise
        else:
            run.finish("success")


def _validated_attributes(
    values: Mapping[str, PerformanceValue],
) -> dict[str, PerformanceValue]:
    """Copy JSON scalar attributes and reject accidental raw objects."""

    result: dict[str, PerformanceValue] = {}
    for name, value in values.items():
        if not name or not isinstance(value, (str, int, float, bool, type(None))):
            raise TypeError("performance attributes require names and JSON scalar values")
        result[name] = value
    return result


def _repository_metadata(output_directory: Path) -> dict[str, str | None]:
    """Record a revision and content-only dirty fingerprint when reports are in a repo."""

    repository_root = next(
        (parent for parent in (output_directory, *output_directory.parents) if (parent / ".git").exists()),
        None,
    )
    if repository_root is None:
        return {"revision": None, "dirty_source_sha256": None}
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--"],
            cwd=repository_root,
            check=True,
            capture_output=True,
        ).stdout
        digest = hashlib.sha256(diff)
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=repository_root,
            check=True,
            capture_output=True,
        ).stdout
        for raw_path in untracked.split(b"\0"):
            if not raw_path:
                continue
            path = repository_root / Path(os.fsdecode(raw_path))
            digest.update(raw_path)
            if path.is_symlink():
                digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
            elif path.is_file() and path.resolve().is_relative_to(repository_root.resolve()):
                digest.update(path.read_bytes())
        return {"revision": revision, "dirty_source_sha256": digest.hexdigest()}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty_source_sha256": None}


def _dependency_versions() -> dict[str, str | None]:
    """Return versions of libraries that materially shape image observations."""

    versions: dict[str, str | None] = {}
    for distribution in ("rapidocr", "onnxruntime", "opencv-python", "Pillow", "numpy"):
        try:
            versions[distribution] = package_version(distribution)
        except PackageNotFoundError:
            versions[distribution] = None
    return versions
