"""Offline checks for weekly performance report aggregation and comparison."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from tests.support.paths import REPOSITORY_ROOT


class WeeklyPerformanceReportTests(unittest.TestCase):
    """Keeps local evidence isolated and trend calculations stable."""

    def test_metrics_directories_use_the_separate_local_root(self) -> None:
        module = _load_module()
        directories = module.metrics_directories(Path("C:/repo"))

        self.assertEqual(Path("C:/repo/.local-data/performance-metrics"), directories["root"])
        self.assertEqual(directories["root"] / "runs", directories["runs"])
        self.assertEqual(directories["root"] / "benchmarks", directories["benchmarks"])
        self.assertEqual(directories["root"] / "weekly", directories["weekly"])

    def test_summarizes_five_fixture_replays_and_compares_medians(self) -> None:
        module = _load_module()
        benchmark = {
            "warm_replays": 5,
            "frames": [
                {
                    "image": fixture,
                    "expected_screen": "PNC_HOME_CITY",
                    "guarded_decision": {
                        "screen": "PNC_HOME_CITY",
                        "wrong_actionable_classification": False,
                        "abstention": False,
                    },
                    "warm_replays": [
                        {
                            "latency_ms": {
                                "total": total,
                                "visual": total / 3,
                                "content": total / 2,
                                "guard": total / 4,
                            },
                            "ocr": {"requests": 1, "engine_calls": 1, "processed_pixel_area": 500},
                        }
                        for total in range(10, 15)
                    ],
                }
                for fixture in module.FIXTURE_NAMES
            ],
        }

        current = module.summarize_benchmark(benchmark)
        first = current[module.FIXTURE_NAMES[0]]
        self.assertEqual(12.0, first["latency_ms"]["total"]["median"])
        self.assertEqual(4.0, first["latency_ms"]["total"]["range"])
        self.assertEqual(5, first["latency_ms"]["total"]["sample_count"])
        self.assertEqual(5, first["ocr_work"]["requests"])
        self.assertTrue(first["screen_matches_expected"])

        prior = {
            "collected_at_utc": "2026-09-22T09:00:00+00:00",
            "fixture_timings": {
                fixture: {
                    **result,
                    "latency_ms": {
                        stage: ({**summary, "median": summary["median"] - 2} if summary else None)
                        for stage, summary in result["latency_ms"].items()
                    },
                }
                for fixture, result in current.items()
            },
            "live_operation_timings": [],
        }
        comparison = module.build_comparison(current, [], prior)

        self.assertEqual("compared", comparison["status"])
        self.assertEqual(2.0, comparison["fixture_deltas_ms"][module.FIXTURE_NAMES[0]]["total"]["delta"])

    def test_summarizes_recent_operation_wall_and_thread_cpu_time(self) -> None:
        module = _load_module()
        now = module.datetime.now(module.UTC)
        report = {
            "schema_version": 1,
            "run_id": "run-1",
            "workflow": "core_runtime",
            "started_at_utc": now.isoformat(),
            "attributes": {"runner_path": "weekly_fixture"},
            "spans": [
                {
                    "name": "observation.build",
                    "duration_seconds": 0.5,
                    "thread_cpu_seconds": 0.2,
                    "outcome": "success",
                    "attributes": {"fixture": "home_city_core.png"},
                },
                {
                    "name": "observation.build",
                    "duration_seconds": 0.7,
                    "thread_cpu_seconds": 0.4,
                    "outcome": "error",
                    "attributes": {"fixture": "home_city_core.png"},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "span.json").write_text(json.dumps(report), encoding="utf-8")

            operations = module.summarize_recent_spans(directory, now=now)

        self.assertEqual(1, len(operations))
        self.assertEqual(2, operations[0]["call_count"])
        self.assertEqual(1, operations[0]["run_count"])
        self.assertEqual(0.6, operations[0]["median_wall_seconds"])
        self.assertAlmostEqual(0.3, operations[0]["median_thread_cpu_seconds"])
        self.assertEqual(1, operations[0]["failed_calls"])


def _load_module() -> object:
    tools_directory = REPOSITORY_ROOT / "tools"
    sys.path.insert(0, str(tools_directory))
    try:
        module_path = tools_directory / "weekly_performance_report.py"
        spec = importlib.util.spec_from_file_location("test_weekly_performance_report_module", module_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load weekly_performance_report.py for testing.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
