"""Tests for opt-in run-scoped performance accounting."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from pnc_automation.core.infra.adb.client import AdbClient
from pnc_automation.core.infra.adb.command_result import CommandResult
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrReadPurpose,
    OcrResult,
)
from pnc_automation.core.infra.diagnostics.performance import (
    PerformanceReportWriter,
    current_performance_run,
    performance_run_scope,
    performance_span,
    performance_wait,
)


class PerformanceTests(unittest.TestCase):
    """Proves local report output, nested spans, failures, and disabled behavior."""

    def test_nested_spans_write_one_report_and_keep_failure_type_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            writer = PerformanceReportWriter(Path(temporary_directory))
            with performance_run_scope(writer, "fixture_replay") as run:
                self.assertIsNotNone(run)
                self.assertIs(run, current_performance_run())
                with performance_span("adb.command", attributes={"operation": "exec-out"}) as outer:
                    self.assertIsNotNone(outer)
                    with performance_span("screenshot.decode"):
                        pass
                    outer.set_attribute("payload_bytes", 2048)
                with self.assertRaisesRegex(ValueError, "private marker"):
                    with performance_span("recovery.retry"):
                        raise ValueError("private marker")

            self.assertIsNone(current_performance_run())
            reports = list(Path(temporary_directory).glob("*.json"))
            self.assertEqual(1, len(reports))
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual("fixture_replay", report["workflow"])
            self.assertEqual("success", report["outcome"])
            spans = {span["name"]: span for span in report["spans"]}
            self.assertEqual("exec-out", spans["adb.command"]["attributes"]["operation"])
            self.assertEqual(2048, spans["adb.command"]["attributes"]["payload_bytes"])
            self.assertEqual(spans["adb.command"]["span_id"], spans["screenshot.decode"]["parent_id"])
            self.assertEqual("error", spans["recovery.retry"]["outcome"])
            self.assertEqual("ValueError", spans["recovery.retry"]["error_type"])
            self.assertNotIn("private marker", reports[0].read_text(encoding="utf-8"))

    def test_explicit_context_activation_records_worker_thread_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            writer = PerformanceReportWriter(Path(temporary_directory))
            run = writer.begin_run("worker_replay")
            worker_ids: list[int] = []

            def measure_worker() -> None:
                with run.activate():
                    with performance_span("p2.analysis"):
                        worker_ids.append(threading.get_ident())

            with run.activate():
                worker = threading.Thread(target=measure_worker, name="performance-test-worker")
                worker.start()
                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())
            report_path = run.finish("success")

            self.assertIsNotNone(report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            span = report["spans"][0]
            self.assertEqual(worker_ids[0], span["thread_id"])
            self.assertNotEqual(threading.get_ident(), span["thread_id"])

    def test_disabled_spans_do_not_create_reports(self) -> None:
        with performance_span("unmeasured") as span:
            self.assertIsNone(span)
        self.assertIsNone(current_performance_run())

    def test_environment_opt_in_is_explicit(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(PerformanceReportWriter.from_environment(Path("reports")))
        with patch.dict("os.environ", {"PNC_PERFORMANCE_REPORTS": "1"}, clear=True):
            self.assertIsNotNone(PerformanceReportWriter.from_environment(Path("reports")))

    def test_adb_spans_capture_results_and_failures_without_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            writer = PerformanceReportWriter(Path(temporary_directory))
            command_runner = _CommandRunner()
            client = AdbClient(adb_path="adb", runner=command_runner)
            with performance_run_scope(writer, "adb_fixture"):
                result = client.run_device("private-device-id", "exec-out", "screencap", "-p")
                self.assertEqual(b"png", result.stdout)
                command_runner.failure = TimeoutError("private command details")
                with self.assertRaisesRegex(TimeoutError, "private command details"):
                    client.run_device("private-device-id", "shell", "sensitive-argument")

            report_path = next(Path(temporary_directory).glob("*.json"))
            report_text = report_path.read_text(encoding="utf-8")
            report = json.loads(report_text)
            adb_spans = [span for span in report["spans"] if span["name"] == "adb.command"]
            self.assertEqual("exec-out", adb_spans[0]["attributes"]["family"])
            self.assertEqual(3, adb_spans[0]["attributes"]["stdout_bytes"])
            self.assertEqual("error", adb_spans[1]["outcome"])
            self.assertEqual("TimeoutError", adb_spans[1]["error_type"])
            self.assertNotIn("private-device-id", report_text)
            self.assertNotIn("sensitive-argument", report_text)
            self.assertNotIn("private command details", report_text)

    def test_screenshot_capture_records_transport_decode_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload_stream = BytesIO()
            Image.new("RGB", (3, 2), color="blue").save(payload_stream, format="PNG")
            payload = payload_stream.getvalue()
            screenshot_service = ScreenshotService(
                artifact_store=ArtifactStore(root=Path(temporary_directory) / "artifacts")
            )
            session = SimpleNamespace(
                capture_screenshot_frame=lambda: SimpleNamespace(payload=payload, frame_ref=None)
            )
            writer = PerformanceReportWriter(Path(temporary_directory) / "reports")
            with performance_run_scope(writer, "screenshot_fixture"):
                capture = screenshot_service.capture(
                    session,
                    artifact_directory="fixture",
                    label="capture",
                    persist=True,
                )

            self.assertIsNotNone(capture.artifact_path)
            report_path = next((Path(temporary_directory) / "reports").glob("*.json"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            spans = {span["name"]: span for span in report["spans"]}
            self.assertEqual(len(payload), spans["screenshot.capture"]["attributes"]["payload_bytes"])
            for name in ("screenshot.transport", "screenshot.decode", "screenshot.persist"):
                self.assertEqual(spans["screenshot.capture"]["span_id"], spans[name]["parent_id"])

    def test_ocr_backend_spans_identify_workload_without_storing_read_details(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            image = Image.new("RGB", (12, 8), color="white")
            backend = SimpleNamespace(
                read_result=lambda source, region: OcrResult(lines=(), words=())
            )
            context = ObservationOcrContext(image, backend, None, "fixture-ocr")
            writer = PerformanceReportWriter(Path(temporary_directory))
            with performance_run_scope(writer, "ocr_fixture"):
                context.read_result(
                    image,
                    Bounds(2, 1, 5, 3),
                    purpose=OcrReadPurpose.CONTENT,
                    detail="private fixture note",
                )

            report_path = next(Path(temporary_directory).glob("*.json"))
            report_text = report_path.read_text(encoding="utf-8")
            report = json.loads(report_text)
            span = next(item for item in report["spans"] if item["name"] == "ocr.backend_call")
            self.assertEqual("content", span["attributes"]["purpose"])
            self.assertEqual(12, span["attributes"]["input_width"])
            self.assertEqual(8, span["attributes"]["input_height"])
            self.assertEqual(5, span["attributes"]["region_width"])
            self.assertEqual(3, span["attributes"]["region_height"])
            self.assertEqual(15, span["attributes"]["processed_pixel_area"])
            self.assertNotIn("private fixture note", report_text)

    def test_explicit_wait_records_requested_and_actual_duration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            writer = PerformanceReportWriter(Path(temporary_directory))
            observed_seconds: list[float] = []
            with performance_run_scope(writer, "wait_fixture"):
                performance_wait("fixture_poll", 0.25, observed_seconds.append)

            report_path = next(Path(temporary_directory).glob("*.json"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            wait = next(span for span in report["spans"] if span["name"] == "navigation.wait")
            self.assertEqual([0.25], observed_seconds)
            self.assertEqual("fixture_poll", wait["attributes"]["reason"])
            self.assertEqual(0.25, wait["attributes"]["requested_seconds"])
            self.assertGreaterEqual(wait["attributes"]["actual_seconds"], 0)


class _CommandRunner:
    """Returns a small result and can then fail to prove the AdbClient boundary is exception-safe."""

    def __init__(self) -> None:
        self.failure: BaseException | None = None

    def run(self, command: tuple[str, ...], *, timeout_seconds: float | None = None) -> CommandResult:
        del timeout_seconds
        if self.failure is not None:
            raise self.failure
        return CommandResult(
            command=command,
            returncode=0,
            stdout=b"png",
            stderr=b"",
            duration_seconds=0.001,
        )
