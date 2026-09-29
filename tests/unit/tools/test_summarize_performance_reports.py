"""Pure offline tests for the local performance report summarizer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from tests.support.paths import REPOSITORY_ROOT


class PerformanceReportSummaryTests(unittest.TestCase):
    """Ranks worker CPU and separates concurrent wall time from call counts."""

    def test_ranks_workflows_and_counts_waits_recovery_and_failures(self) -> None:
        module = _load_summarizer_module()
        summary = module.summarize_reports(
            [
                {
                    "workflow": "script_runner",
                    "elapsed_seconds": 3.0,
                    "outcome": "success",
                    "spans": [
                        {"name": "screenshot.capture", "duration_seconds": 1.0, "thread_cpu_seconds": 0.5, "outcome": "success"},
                        {"name": "navigation.wait", "duration_seconds": 0.4, "thread_cpu_seconds": 0.0, "outcome": "success"},
                        {"name": "recovery.interruption", "duration_seconds": 0.8, "thread_cpu_seconds": 0.1, "outcome": "success"},
                    ],
                },
                {
                    "workflow": "core_runtime",
                    "elapsed_seconds": 8.0,
                    "outcome": "error",
                    "spans": [
                        {"name": "core.workflow", "duration_seconds": 5.0, "thread_cpu_seconds": 1.0, "outcome": "error"},
                        {"name": "world_map.p2.wait", "duration_seconds": 2.0, "thread_cpu_seconds": 0.0, "outcome": "success"},
                    ],
                },
            ]
        )

        self.assertEqual(2, summary["report_count"])
        workflows = summary["workflows"]
        self.assertEqual("core_runtime", workflows[0]["workflow"])
        self.assertEqual(1, workflows[0]["failed_runs"])
        self.assertEqual(1, workflows[0]["wait_count"])
        self.assertEqual(1, workflows[1]["recovery_count"])
        self.assertEqual(
            0.4,
            workflows[1]["median_stage_span_wall_sum_seconds"]["navigation.wait"],
        )
        self.assertEqual(
            0.5,
            workflows[1]["median_stage_thread_cpu_seconds"]["screenshot.capture"],
        )

    def test_rejects_non_positive_span_limit(self) -> None:
        module = _load_summarizer_module()
        with self.assertRaisesRegex(ValueError, "limit_spans must be positive"):
            module.summarize_reports([], limit_spans=0)

    def test_loads_performance_reports_alongside_benchmark_result_json(self) -> None:
        module = _load_summarizer_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "span-report.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "workflow": "fixture_replay",
                        "elapsed_seconds": 1.0,
                        "spans": [],
                    }
                ),
                encoding="utf-8",
            )
            (directory / "benchmark-result.json").write_text(
                json.dumps({"version": 2, "frames": []}),
                encoding="utf-8",
            )

            reports = module.load_performance_reports(directory)

        self.assertEqual(1, len(reports))
        self.assertEqual("fixture_replay", reports[0]["workflow"])


def _load_summarizer_module() -> object:
    """Loads the standalone summarizer module without importing it as a package."""

    tools_directory = REPOSITORY_ROOT / "tools"
    sys.path.insert(0, str(tools_directory))
    try:
        module_path = tools_directory / "summarize_performance_reports.py"
        spec = importlib.util.spec_from_file_location("test_summarize_performance_reports_module", module_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load summarize_performance_reports.py for testing.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
