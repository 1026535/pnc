# PNC Live-Test Performance and Instrumentation Plan

## Objective

Make slow live-test runs explainable across the runner paths used by multiple epics, rank their shared bottlenecks, and drive measured, correctness-preserving optimizations. The P1 capture benchmark is a calibration harness, not the end state.

ChatGPT Pro review baseline: `b0701df653fa774678ab96b3c293ac13eeb25b1e`. Implementation is based on `1c04b3130227ab0e0896a013c28913616de411c7` after refreshing the task branch. This is a plan; it does not authorize or perform a live emulator run.

## Current state

- `tools/run_tests.py measure` records offline suite phases and test timings, but enables branch coverage. Keep its results separate from ordinary `full` runs when comparing duration.
- `SubprocessCommandRunner` reports elapsed time in successful `CommandResult` values. A subprocess launch error or timeout can exit before a result exists, so its elapsed time is currently missing.
- `ScreenshotService` owns capture, decode, and optional artifact persistence. OCR contexts already expose call counts, cache/reuse counts, processed area, and engine time.
- `CoreRuntime` writes a per-run JSONL trace, but its ID and trace are created after connected-runtime construction. A collector attached only to `CoreRuntime.record()` misses setup and failed construction. Other live workflows also enter through `ScriptRunner`.
- `tools/benchmark_world_map_p1_capture.py` has a visible indentation/scope defect: the measurement block falls outside the connected-runtime context, then the output block is over-indented. Correct both together; fixing only the print indentation would leave the benchmark using services after cleanup. This is a source inspection finding; the script was not run.
- Existing screen-recognition and world-map benchmarks provide focused measurement owners. A repository-wide aggregate performance report was not found in this review; that absence was not exhaustively proven.

## Design

Repair and use the existing world-map P1 capture benchmark as a calibration harness, then attach one optional, run-scoped performance collector with a no-op default to the canonical live-test lifecycle. Scope this to supported offline/live test entry points, not always-on telemetry for routine automation. Enable collection only through an explicit benchmark/test option. Cover both authored/direct `ScriptRunner` executions and `CoreRuntime`/`CoreWorkflowRunner` executions built through the shared connected-runtime path. During implementation, inventory the live-test entry points and adapt a bypassing canonical seam if one exists; do not stop after measuring only the P1 tool. Start each outer wall timer before that run's application/runtime construction and preparation; finish it after cleanup, including exceptional exits. Do not claim to include Python imports that occur before the entry point.

Give each run a stable measurement ID and correlate it with the existing core trace when present; preserve parent/child identity where a preparation run precedes a workflow run. Keep reports separate from navigation events and emit one per-run summary under `.local-data/reports/performance/`. Add a small local summarizer that groups existing reports by workflow/runner path and ranks total duration, stage contribution, failure, wait, and recovery frequency. Do not write a report event on every trace record or add a hosted metrics backend.

Record only the first useful timing layers:

| Area | Existing owner | Minimum information |
| --- | --- | --- |
| Run lifecycle | Benchmark entry point, preparation, `ScriptRunner` connection and cleanup | Total wall time, phase durations, outcome |
| ADB | `CommandRunner` / `SubprocessCommandRunner.run` | Operation family, count, elapsed wall time, return/timeout/exception outcome |
| Screenshot | `ScreenshotService.capture` | Capture, decode, and persistence durations; counts and payload bytes |
| Observation and OCR | Core observation/perception and OCR context | Observation duration plus existing frame-local OCR metrics |
| Waits and recovery | Existing settling/polling and recovery owners | Reason, count, requested/actual wait, recovery/retry count and enclosing duration |

Use a monotonic clock for elapsed spans. Add process CPU time only as a separate supplementary value; label it host-process CPU, not Python-only CPU. ADB elapsed time combines process startup, transport, emulator scheduling, and device work. Do not label uninstrumented residual time or wall-minus-CPU as device wait. Keep parent/child spans so inclusive totals are not added together; retain thread identity so work performed by lazy worker-thread pipelines is visible.

Reuse existing OCR metrics once per context (or as deltas), rather than summing repeated cumulative snapshots. Instrument explicit wait owners instead of globally patching sleep. For failed ADB calls, measure in an exception-safe boundary and re-raise the existing exception unchanged.

Do not add a metrics backend, required profiler dependency, broad event tracing, or extra screenshots. Keep profiler installations and exports optional and local.

## Local use

- Set `PNC_PERFORMANCE_REPORTS=1` before invoking a supported `build_application_runner` entry point to write one local report per connected workflow lifecycle. Reports default to `.local-data/reports/performance/` and remain disabled otherwise.
- Run a representative saved-fixture baseline with `py tools/benchmark_screen_recognition.py --warm-replays 5 --measurement-profile post_d --sample home_city_core.png --sample world_map_core.png --sample bag.png --sample chat_alliance.png --sample quest_daily_sep09.png --output .local-data/reports/performance/screen-recognition-baseline.json`. This is host-only and does not use ADB; `--sample` validates all manifest metadata and split-isolation rules while decoding and hash-checking only selected images.
- Add `--performance-report` to capture nested observation, OCR-backend, and Home-camera scale spans with thread CPU time. Reports also record the current Git revision, a content-only dirty-source fingerprint, host identity, and relevant image/OCR dependency versions.
- For a separately authorized representative live P1 run, use `py tools/benchmark_world_map_p1_capture.py --performance-report`; all runtime-dependent measurements finish before the connected runtime closes.
- Rank collected runs with `py tools/summarize_performance_reports.py --directory .local-data/reports/performance`.

## Phases and acceptance

### 1. Repair and make the existing benchmark runnable offline

Fix the P1 capture benchmark's context scope so all measurements using the connected runtime happen before its cleanup, and the report is emitted after valid measurement results are available. Add a focused compile check and deterministic fake-context coverage for the lifetime boundary; do not execute the live benchmark in this phase.

**Accept when:** the module compiles; offline coverage proves measurements run inside the connected-runtime lifetime and cleanup still occurs on errors; no emulator access is needed.

### 2. Instrument and prove coverage across the shared live-run paths

Implement the collector and connect the entry-point, connected-runtime, ADB, screenshot, observation/OCR, explicit wait, and recovery measurements above. Enable it for the P1 benchmark and the canonical `ScriptRunner` and `CoreRuntime` run shapes. Disabled collection must preserve existing behavior. Capture failures and cleanup as outcomes, and correlate each report with its core trace or mark that trace as unavailable. Verify every live entry point found in the phase-one inventory either flows through these seams or has a focused adapter.

**Accept when:** focused offline tests cover normal, timeout/exception, failed construction, recovery, cleanup, nested spans, and worker-thread identity; fake runs through both runner shapes produce correctly correlated summaries; and the local summarizer can rank reports across workflow paths. Reports remain low-volume, contain no credentials or config secrets, and write under `.local-data/reports/performance/`. Measure disabled and enabled overhead against the same uninstrumented workload.

### 3. Establish cross-workflow baselines and prioritize optimizations

Use saved screen-recognition fixtures for repeatable host-side comparison and apply them to each supported observation path where fixtures exist. Separate cold initialization from warm fixture replay. For a candidate comparison, use the same fixture set, settings, and pipeline mode on baseline and candidate revisions; begin with about five matched replay pairs in alternating order, increasing repetitions only if variance prevents a decision. Preserve raw samples, including failures and recovery-heavy samples.

Record revision and dirty-source fingerprint, Python/dependency versions, Windows/hardware identity, fixture hashes, workload counts, OCR/backend settings, persistence/debug flags, and profiler/coverage state. Keep `full`, `measure`, and profiler-enabled runs in separate result series. Report sample count, median, spread, paired differences, absolute seconds saved, and percentage change. Do not present five samples as reliable p95 evidence.

Use **Pyinstrument first** on a narrowly scoped saved-fixture replay when the question is which Python-visible call paths consume wall time. Its sampling includes time blocked inside a sampled call, so it can point at an ADB caller but cannot split ADB startup, emulator transport, and device execution. It can miss short calls. Use built-in **cProfile** when exact call counts or self/cumulative function time are the question; its call-event overhead can distort call-heavy workloads. Use **VizTracer** only when event ordering, repeated sequences, or thread overlap is the unanswered question; capture volume and overhead depend on event density and filtering. None of these profiles BlueStacks internals. The lazy P2 observation path runs on a worker thread, so verify the selected profiler captures that workload. Measure profiler slowdown and export time separately; never compare a profiled baseline with an unprofiled candidate.

Use the summarizer to identify bottlenecks common across the covered runner paths and bottlenecks isolated to one workflow. Rank candidates by expected seconds saved per representative run multiplied by expected repetition frequency, then account for implementation and validation cost. Evaluate the highest-return shared candidate first, then continue the optimize/measure loop for other material contributors; do not treat one pilot optimization as resolving a cross-epic performance blocker. After baseline data establishes current duration, set an explicit target with the affected epic owners rather than choosing an arbitrary speed threshold in advance. A speedup in a small stage may have little end-to-end effect.

**Accept when:** the baseline report covers both runner shapes and ranks the dominant contributors with sample counts; fixture outcomes and required work remain unchanged; each unprofiled candidate improves reproducibly under matched conditions; and workload counts (captures, OCR calls/area, retries, and required artifacts) explain the gain rather than showing work was skipped. Unknown or unmeasured runner paths remain visible as gaps, not inferred as fast.

### 4. Revalidate only a changed live boundary

Fixture replay cannot establish real ADB latency, emulator readiness, or live recovery frequency. First collect reports from already-authorized live runs across the covered runner paths where available; do not launch extra live runs solely to fill the matrix. If a path lacks live timing and its priority warrants a baseline, request one representative, non-spending live check through a separate authorized assignment. For changes to capture transport, interaction timing, settling, or recovery, validate only the changed boundary with the smallest representative live check. Record the same lifecycle phases plus the live environment (ADB/BlueStacks versions, resolution, starting screen, and whether the instance was already running). Preserve failures and timeouts in the report.

A pure host-side optimization with fixture parity may not need another live run beyond the project's existing required validation. Do not rerun an epic-wide live suite. If actual live cost shares have not been measured, establish them in the first later-authorized representative run before claiming end-to-end savings. Track progress against the baseline and the agreed epic-level target; keep iterating on material shared bottlenecks until that target is met or the remaining time is shown to be outside Python's control.

## References

- [Python 3.13 profiling documentation](https://docs.python.org/3.13/library/profile.html) — cProfile and profiling limits.
- [Python 3.13 time documentation](https://docs.python.org/3.13/library/time.html) — monotonic, process, and thread clocks.
- [Pyinstrument: how sampling works](https://pyinstrument.readthedocs.io/en/latest/how-it-works.html) — sampled call stacks and wall-time behavior.
- [Pyinstrument user guide](https://pyinstrument.readthedocs.io/en/stable/guide.html) — CLI reports and sampling interval.
- [VizTracer documentation](https://viztracer.readthedocs.io/en/latest/) — execution timeline and platform/setup details.
