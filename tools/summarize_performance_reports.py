"""Ranks opt-in local PNC performance reports by workflow and measured stage."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
from typing import Any

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()


def summarize_reports(documents: list[dict[str, Any]], *, limit_spans: int = 8) -> dict[str, object]:
    """Rank measured span CPU work and keep concurrent wall spans distinguishable."""

    if limit_spans <= 0:
        raise ValueError("limit_spans must be positive.")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        workflow = document.get("workflow")
        elapsed = document.get("elapsed_seconds")
        spans = document.get("spans")
        if not isinstance(workflow, str) or not isinstance(elapsed, (int, float)):
            raise ValueError("Performance reports require a workflow and numeric elapsed_seconds.")
        if not isinstance(spans, list):
            raise ValueError(f"Performance report for {workflow!r} has no spans list.")
        attributes = document.get("attributes")
        runner_path = attributes.get("runner_path") if isinstance(attributes, dict) else None
        grouped[(workflow, runner_path if isinstance(runner_path, str) else "unknown")].append(document)

    workflows: list[dict[str, object]] = []
    for (workflow, runner_path), runs in grouped.items():
        elapsed_samples = [float(run["elapsed_seconds"]) for run in runs]
        stage_wall_sum_samples: dict[str, list[float]] = defaultdict(list)
        stage_wall_max_samples: dict[str, list[float]] = defaultdict(list)
        stage_cpu_samples: dict[str, list[float]] = defaultdict(list)
        wait_count = 0
        recovery_count = 0
        failed_spans = 0
        for run in runs:
            per_run_wall_sum: dict[str, float] = defaultdict(float)
            per_run_wall_max: dict[str, float] = defaultdict(float)
            per_run_cpu: dict[str, float] = defaultdict(float)
            for span in run["spans"]:
                if not isinstance(span, dict):
                    continue
                name = span.get("name")
                duration = span.get("duration_seconds")
                if not isinstance(name, str) or not isinstance(duration, (int, float)):
                    continue
                per_run_wall_sum[name] += float(duration)
                per_run_wall_max[name] = max(per_run_wall_max[name], float(duration))
                thread_cpu = span.get("thread_cpu_seconds")
                if isinstance(thread_cpu, (int, float)):
                    per_run_cpu[name] += float(thread_cpu)
                if name.endswith(".wait") or name == "navigation.wait":
                    wait_count += 1
                if "recovery" in name:
                    recovery_count += 1
                if span.get("outcome") == "error":
                    failed_spans += 1
            for name, duration in per_run_wall_sum.items():
                stage_wall_sum_samples[name].append(duration)
                stage_wall_max_samples[name].append(per_run_wall_max[name])
                if name in per_run_cpu:
                    stage_cpu_samples[name].append(per_run_cpu[name])

        stage_cpu_medians = {
            name: statistics.median(samples)
            for name, samples in stage_cpu_samples.items()
        }
        ranked_stages = sorted(stage_cpu_medians.items(), key=lambda item: item[1], reverse=True)
        workflows.append(
            {
                "workflow": workflow,
                "runner_path": runner_path,
                "sample_count": len(runs),
                "median_elapsed_seconds": statistics.median(elapsed_samples),
                "failed_runs": sum(run.get("outcome") == "error" for run in runs),
                "failed_spans": failed_spans,
                "wait_count": wait_count,
                "recovery_count": recovery_count,
                "median_stage_thread_cpu_seconds": dict(ranked_stages[:limit_spans]),
                "median_stage_span_wall_sum_seconds": {
                    name: statistics.median(stage_wall_sum_samples[name])
                    for name, _ in ranked_stages[:limit_spans]
                },
                "median_stage_max_span_wall_seconds": {
                    name: statistics.median(stage_wall_max_samples[name])
                    for name, _ in ranked_stages[:limit_spans]
                },
            }
        )
    workflows.sort(key=lambda item: float(item["median_elapsed_seconds"]), reverse=True)
    return {"report_count": len(documents), "workflows": workflows}


def load_performance_reports(directory: Path) -> list[dict[str, Any]]:
    """Load versioned span reports while ignoring benchmark result JSON files."""

    documents: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"JSON report must contain an object: {path}")
        if document.get("schema_version") == 1:
            documents.append(document)
    return documents


def main() -> None:
    """Prints a compact JSON ranking from local report files."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=root / ".local-data" / "performance-metrics" / "runs",
    )
    parser.add_argument("--limit-spans", type=int, default=8)
    arguments = parser.parse_args()
    documents = load_performance_reports(arguments.directory)
    print(json.dumps(summarize_reports(documents, limit_spans=arguments.limit_spans), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
