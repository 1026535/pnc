# Supporting measures — Batch delay, repair and accepted output

Priority: supporting measurement for the five primary [velocity plans](README.md), populated during normal work. Owner: V coordinator; workers supply actual execution timestamps. Review coverage: every §6 metric and the unmeasured-benefit caveat in §4/§5.

## Design

Use existing batch records, curated `evidence.json`, coordinator review timestamps and `tools/run_tests.py` result/timing artifacts. `tools/test_selection/reporting.py` already records test/module timing and summary information. Do not add a profiler, host utilization agent, dashboard or another measurement run for this task. This measures delivery flow; the existing [live-performance instrumentation plan](../../../../testing/PNC_LIVE_TEST_PERFORMANCE_INSTRUMENTATION_PLAN.md) owns detailed runtime profiling.

Add one small `delivery` record per batch in the canonical coordinator record from 11, with links to source evidence. Start with the next batch and backfill only recent records whose timestamps are unambiguous. Missing historical timestamps stay null/unknown.

## Required fields

| Field | Definition / source |
|---|---|
| batch ID, package ID, candidate, attempt | Existing assignment/run identity; separate corrected attempts without double-counting the route |
| submitted_at / ready_at | Submission versus time all execution prerequisites are met; they differ when evidence or authority is still pending |
| started_at / terminal_at | Actual executor start and terminal handback, not callback delivery or file modification time |
| review_started_at / disposition_at | Coordinator acceptance review and its terminal disposition |
| wait intervals | Start/end plus one primary reason: CPU, live lease, evidence, authority, dependency, or coordinator review; secondary reasons may be annotations |
| repair_required / findings | Whether handback needed repair, concrete finding IDs and repaired boundary; distinguish package omissions from a newly discovered implementation defect |
| test evidence | Selection/results paths, mode/instrumentation, inventory and selected modules, fallback reasons, actual elapsed runtime and completion status |
| route outcomes | Newly accepted route-unit IDs; still pending IDs; repeated case IDs with reason and link to changed implementation/state |
| retained proof | Existing accepted cases deliberately reused, with unchanged-scope rationale |

For new assignments under the recorded non-Main policy, do not log a collection-approval wait merely because an old template says pending. A rejected runtime capability is an implementation dependency; a foreign lease is a lease wait. Correct classification is necessary to identify the actual bottleneck.

## Steps

1. **Define field semantics in the existing QA template.** Coordinator owns readiness/wait/review fields; executor supplies start/terminal and receipt/result evidence. Store UTC timestamps with explicit timezone. Historical worker turn numbers, filesystem modification times and inferred process starts must not masquerade as observed timestamps.
2. **Populate from normal work.** At each package readiness, execution start, terminal handback and review disposition, update the existing record once. Avoid repeated polling/status messages. Preserve failed/incomplete batches; do not measure only accepted successes.
3. **Reconcile durations.** `ready_wait = started_at - ready_at`, `execution = terminal_at - started_at`, `review_delay = review_started_at - terminal_at`, and `review_turnaround = disposition_at - terminal_at`. These are phase measures; overlapping CPU/lease waits cannot be summed as if mutually exclusive. Use interval unions or one primary wait reason for totals. Record missing or invalid boundaries instead of negative durations.
4. **Compute a compact report from saved data.** Per completed cohort, show batch count, observed ready-to-disposition duration, waits by reason, repair count/rate, selected/full-fallback counts and test runtime, newly accepted routes, pending routes and repeats by reason. Give sample count and range/median when useful; do not report a stable percentile from a few batches. Compare like workloads/candidate stages, keeping `measure` separate from ordinary runs.
5. **Turn the dominant observed delay into one action.** Examples: broad resource selection feeds B (09); import fan-out feeds A (14); repeated capture preparation/owner transfers feed C (15); mechanical handback errors feed D (11); capacity/review queueing feeds E (10). Do not promise percentage savings before comparable evidence exists. Keep raw reports under `.local-data/`; test-selection scratch stays `.test-impact/`.

## Acceptance

Take the next completed batch and trace each reported timestamp/result/count to its existing artifact. One coordinator should be able to answer: what waited, why, who owned it, whether handback needed repair, how much testing ran, and which routes became accepted. Reconcile repeated cases and retained proof so throughput is not inflated by revalidation.

For a prose/template-only change, validate fields/links and `git diff --check`. If a small summarizer is later justified by repeated manual work, extend existing reporting rather than creating a service; test one complete record, a missing-time record, overlapping waits and a repaired/repeated case. No unit/live/benchmark run is required simply to begin recording these fields.
