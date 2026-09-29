"""Collect a repeatable offline benchmark and compare weekly operation timings."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any

from _script_bootstrap import ensure_repo_root_on_path

ROOT = ensure_repo_root_on_path()
FIXTURE_NAMES = (
    "home_city_core.png",
    "world_map_core.png",
    "bag.png",
    "chat_alliance.png",
    "quest_daily_sep09.png",
)
REPLAY_COUNT = 5
LATENCY_STAGES = ("total", "visual", "content", "guard")


def metrics_directories(repository_root: Path) -> dict[str, Path]:
    """Return the isolated local destinations for all performance evidence."""

    metrics_root = repository_root / ".local-data" / "performance-metrics"
    return {
        "root": metrics_root,
        "runs": metrics_root / "runs",
        "benchmarks": metrics_root / "benchmarks",
        "weekly": metrics_root / "weekly",
    }


def summarize_benchmark(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Summarize per-fixture replay latencies, OCR work, and observed outcomes."""

    if document.get("warm_replays") != REPLAY_COUNT:
        raise ValueError(f"weekly benchmark must contain {REPLAY_COUNT} warm replays per fixture")
    frames = document.get("frames")
    if not isinstance(frames, list):
        raise ValueError("benchmark result must contain a frames list")

    fixture_results: dict[str, dict[str, Any]] = {}
    for frame in frames:
        if not isinstance(frame, dict) or not isinstance(frame.get("image"), str):
            raise ValueError("benchmark frames must contain an image name")
        image_name = frame["image"]
        if image_name in fixture_results:
            raise ValueError(f"benchmark result repeats fixture: {image_name}")
        replays = frame.get("warm_replays")
        if not isinstance(replays, list) or len(replays) != REPLAY_COUNT:
            raise ValueError(f"fixture {image_name!r} must contain {REPLAY_COUNT} warm replay records")

        latency_samples: dict[str, list[float]] = {stage: [] for stage in LATENCY_STAGES}
        ocr_work: dict[str, int | float] = defaultdict(float)
        for replay in replays:
            latency = replay.get("latency_ms") if isinstance(replay, dict) else None
            if not isinstance(latency, dict):
                raise ValueError(f"fixture {image_name!r} has a replay without latency measurements")
            for stage in LATENCY_STAGES:
                value = latency.get(stage)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    latency_samples[stage].append(float(value))
            ocr = replay.get("ocr")
            if isinstance(ocr, dict):
                for name, value in ocr.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        ocr_work[name] += value

        decision = frame.get("guarded_decision")
        decision = decision if isinstance(decision, dict) else {}
        fixture_results[image_name] = {
            "expected_screen": frame.get("expected_screen"),
            "final_guarded_screen": decision.get("screen"),
            "screen_matches_expected": decision.get("screen") == frame.get("expected_screen"),
            "wrong_actionable_classification": decision.get("wrong_actionable_classification"),
            "abstention": decision.get("abstention"),
            "latency_ms": {
                stage: _timing_summary(latency_samples[stage])
                for stage in LATENCY_STAGES
            },
            "ocr_work": dict(sorted(ocr_work.items())) or None,
        }

    if set(fixture_results) != set(FIXTURE_NAMES):
        missing = sorted(set(FIXTURE_NAMES) - set(fixture_results))
        extra = sorted(set(fixture_results) - set(FIXTURE_NAMES))
        raise ValueError(f"weekly benchmark fixture set changed; missing={missing}, extra={extra}")
    return {name: fixture_results[name] for name in FIXTURE_NAMES}


def summarize_recent_spans(directory: Path, *, now: datetime) -> list[dict[str, Any]]:
    """Summarize observed operation spans from reports collected in the last week."""

    cutoff = now - timedelta(days=7)
    grouped: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(report, dict) or report.get("schema_version") != 1:
            continue
        started_at = report.get("started_at_utc")
        if not isinstance(started_at, str):
            continue
        try:
            report_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if report_time < cutoff or report_time > now + timedelta(minutes=5):
            continue

        attributes = report.get("attributes")
        runner_path = attributes.get("runner_path") if isinstance(attributes, dict) else None
        runner_path = runner_path if isinstance(runner_path, str) else "unknown"
        workflow = report.get("workflow")
        if not isinstance(workflow, str):
            continue
        spans = report.get("spans")
        if not isinstance(spans, list):
            continue
        for span in spans:
            if not isinstance(span, dict) or not isinstance(span.get("name"), str):
                continue
            duration = span.get("duration_seconds")
            if not isinstance(duration, (int, float)) or isinstance(duration, bool):
                continue
            span_attributes = span.get("attributes")
            fixture = span_attributes.get("fixture") if isinstance(span_attributes, dict) else None
            fixture = fixture if isinstance(fixture, str) else None
            key = (workflow, runner_path, span["name"], fixture)
            bucket = grouped.setdefault(
                key,
                {"wall": [], "cpu": [], "runs": set(), "failures": 0},
            )
            bucket["wall"].append(float(duration))
            cpu = span.get("thread_cpu_seconds")
            if isinstance(cpu, (int, float)) and not isinstance(cpu, bool):
                bucket["cpu"].append(float(cpu))
            bucket["runs"].add(report.get("run_id", path.name))
            bucket["failures"] += int(span.get("outcome") == "error")

    operations: list[dict[str, Any]] = []
    for (workflow, runner_path, operation, fixture), bucket in grouped.items():
        operations.append(
            {
                "workflow": workflow,
                "runner_path": runner_path,
                "operation": operation,
                "fixture": fixture,
                "run_count": len(bucket["runs"]),
                "call_count": len(bucket["wall"]),
                "median_wall_seconds": statistics.median(bucket["wall"]),
                "max_wall_seconds": max(bucket["wall"]),
                "median_thread_cpu_seconds": (
                    statistics.median(bucket["cpu"]) if bucket["cpu"] else None
                ),
                "failed_calls": bucket["failures"],
            }
        )
    return sorted(
        operations,
        key=lambda item: (
            -float(item["median_wall_seconds"]),
            str(item["workflow"]),
            str(item["operation"]),
        ),
    )


def build_comparison(
    fixture_timings: dict[str, dict[str, Any]],
    live_operations: list[dict[str, Any]],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare current medians with the preceding compatible weekly report."""

    if previous is None:
        return {"status": "baseline", "message": "No prior compatible weekly run."}

    prior_fixtures = previous.get("fixture_timings", {})
    fixture_deltas: dict[str, dict[str, Any]] = {}
    for fixture, current in fixture_timings.items():
        prior = prior_fixtures.get(fixture, {}) if isinstance(prior_fixtures, dict) else {}
        stage_deltas: dict[str, Any] = {}
        for stage in LATENCY_STAGES:
            current_summary = current["latency_ms"].get(stage)
            prior_latency = prior.get("latency_ms", {}) if isinstance(prior, dict) else {}
            prior_summary = prior_latency.get(stage) if isinstance(prior_latency, dict) else None
            current_median = current_summary.get("median") if isinstance(current_summary, dict) else None
            prior_median = prior_summary.get("median") if isinstance(prior_summary, dict) else None
            stage_deltas[stage] = _delta(current_median, prior_median)
        fixture_deltas[fixture] = stage_deltas

    prior_operations = previous.get("live_operation_timings", [])
    prior_by_key = {
        _operation_key(item): item
        for item in prior_operations
        if isinstance(item, dict)
    } if isinstance(prior_operations, list) else {}
    operation_deltas = []
    for operation in live_operations:
        prior_operation = prior_by_key.get(_operation_key(operation))
        if prior_operation is None:
            continue
        operation_deltas.append(
            {
                "workflow": operation["workflow"],
                "runner_path": operation["runner_path"],
                "operation": operation["operation"],
                "fixture": operation["fixture"],
                "current_median_wall_seconds": operation["median_wall_seconds"],
                "prior_median_wall_seconds": prior_operation.get("median_wall_seconds"),
                **_delta(
                    operation["median_wall_seconds"],
                    prior_operation.get("median_wall_seconds"),
                ),
            }
        )
    return {
        "status": "compared",
        "previous_collected_at_utc": previous.get("collected_at_utc"),
        "fixture_deltas_ms": fixture_deltas,
        "live_operation_deltas": operation_deltas,
    }


def _timing_summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "sample_count": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
        "range": max(values) - min(values),
    }


def _delta(current: Any, previous: Any) -> dict[str, float | None]:
    if not isinstance(current, (int, float)) or isinstance(current, bool):
        return {"delta": None, "percent_change": None}
    if not isinstance(previous, (int, float)) or isinstance(previous, bool):
        return {"delta": None, "percent_change": None}
    change = float(current) - float(previous)
    percent = None if previous == 0 else change / float(previous) * 100
    return {"delta": change, "percent_change": percent}


def _operation_key(operation: dict[str, Any]) -> tuple[Any, ...]:
    return (
        operation.get("workflow"),
        operation.get("runner_path"),
        operation.get("operation"),
        operation.get("fixture"),
    )


def _latest_compatible_report(directory: Path, settings: dict[str, Any]) -> dict[str, Any] | None:
    for path in sorted(directory.glob("weekly-*.json"), reverse=True):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(document, dict) and document.get("benchmark_settings") == settings:
            document["_report_path"] = str(path)
            return document
    return None


def _read_performance_environment(report_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    document = json.loads(report_path.read_text(encoding="utf-8"))
    environment = document.get("environment", {})
    environment = environment if isinstance(environment, dict) else {}
    repository = environment.get("repository", {})
    repository = repository if isinstance(repository, dict) else {}
    source = {
        "revision": repository.get("revision"),
        "dirty_source_sha256": repository.get("dirty_source_sha256"),
    }
    concise_environment = {
        key: environment.get(key)
        for key in ("python", "platform", "machine", "processor", "dependencies")
    }
    return source, concise_environment


def _print_report(document: dict[str, Any], report_path: Path) -> None:
    print(f"Weekly performance report: {report_path}")
    comparison = document["comparison"]
    if comparison["status"] == "baseline":
        print(comparison["message"])
    fixture_deltas = comparison.get("fixture_deltas_ms", {})
    for fixture, result in document["fixture_timings"].items():
        timings = result["latency_ms"]
        total = timings["total"]
        content = timings["content"]
        total_text = "unavailable" if total is None else f"{total['median']:.1f} ms (range {total['range']:.1f})"
        content_text = "unavailable" if content is None else f"{content['median']:.1f} ms"
        total_delta = fixture_deltas.get(fixture, {}).get("total", {})
        delta = total_delta.get("delta")
        percent = total_delta.get("percent_change")
        change_text = (
            ""
            if not isinstance(delta, (int, float))
            else f"; total change {delta:+.1f} ms"
            + (f" ({percent:+.1f}%)" if isinstance(percent, (int, float)) else "")
        )
        print(
            f"{fixture}: total {total_text}; content {content_text}{change_text}; "
            f"OCR work {result['ocr_work']}"
        )
    correctness = document["benchmark_correctness"]
    print(
        "Fixture correctness: "
        f"{correctness['frame_count']} frames; "
        f"wrong classifications {correctness['wrong_actionable_classification_count']}; "
        f"manual comparison failures {correctness['manual_comparison_failure_count']}; "
        f"baseline recovery regressions {correctness['baseline_recovery_regression_count']}"
    )
    live_deltas = {
        _operation_key(item): item
        for item in comparison.get("live_operation_deltas", [])
        if isinstance(item, dict)
    }
    for operation in document["live_operation_timings"][:8]:
        delta = live_deltas.get(_operation_key(operation), {}).get("delta")
        change_text = f"; change {delta:+.3f}s" if isinstance(delta, (int, float)) else ""
        print(
            f"{operation['workflow']}/{operation['operation']}: "
            f"{operation['median_wall_seconds']:.3f}s median "
            f"({operation['call_count']} calls, {operation['run_count']} runs){change_text}"
        )


def main() -> int:
    """Run the fixed offline benchmark, persist raw data, and compare trends."""

    directories = metrics_directories(ROOT)
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
    benchmark_path = directories["benchmarks"] / f"benchmark-{stamp}.json"
    benchmark_tool = ROOT / "tools" / "benchmark_screen_recognition.py"
    command = [
        sys.executable,
        str(benchmark_tool),
        "--warm-replays",
        str(REPLAY_COUNT),
        "--measurement-profile",
        "post_d",
        "--performance-report",
        "--output",
        str(benchmark_path),
    ]
    for fixture in FIXTURE_NAMES:
        command.extend(("--sample", fixture))
    benchmark_process = subprocess.run(command, cwd=ROOT, check=False)
    if not benchmark_path.is_file():
        raise subprocess.CalledProcessError(benchmark_process.returncode, command)

    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    performance_report_value = benchmark.get("performance_report")
    if not isinstance(performance_report_value, str):
        raise ValueError("benchmark did not record its nested performance report path")
    performance_report_path = Path(performance_report_value)
    if not performance_report_path.is_file() or not performance_report_path.is_relative_to(directories["runs"]):
        raise ValueError("benchmark performance report was not written beneath the metrics runs folder")

    fixture_timings = summarize_benchmark(benchmark)
    collected_at = datetime.now(UTC)
    settings = {
        "selected_fixtures": list(FIXTURE_NAMES),
        "fixture_manifest_sha256": hashlib.sha256(
            (ROOT / "tests" / "data" / "screen_recognition" / "manifest.json").read_bytes()
        ).hexdigest(),
        "warm_replays_per_fixture": REPLAY_COUNT,
        "measurement_profile": "post_d",
        "visual_only": False,
    }
    previous = _latest_compatible_report(directories["weekly"], settings)
    source, environment = _read_performance_environment(performance_report_path)
    live_operations = summarize_recent_spans(directories["runs"], now=collected_at)
    document: dict[str, Any] = {
        "schema_version": 1,
        "collected_at_utc": collected_at.isoformat(),
        "benchmark_settings": settings,
        "source": source,
        "environment": environment,
        "benchmark_result": str(benchmark_path),
        "span_report": str(performance_report_path),
        "benchmark_command_exit_code": benchmark_process.returncode,
        "benchmark_correctness": {
            "frame_count": benchmark.get("frame_count"),
            "wrong_actionable_classification_count": benchmark.get("wrong_actionable_classification_count"),
            "manual_comparison_failure_count": benchmark.get("manual_comparison_failure_count"),
            "baseline_recovery_regression_count": benchmark.get("baseline_recovery_regression_count"),
        },
        "fixture_timings": fixture_timings,
        "live_operation_timings": live_operations,
        "comparison": build_comparison(fixture_timings, live_operations, previous),
    }
    if previous is not None:
        document["comparison"]["previous_report"] = previous.get("_report_path")
    report_path = directories["weekly"] / f"weekly-{stamp}.json"
    report_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print_report(document, report_path)
    return benchmark_process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
