# Miscellaneous Backlog

**Repository snapshot:** `1026535/pnc@14ba3cccb74b54e7bbc184d2a40ebcb5328f580a` (fetched from GitHub `main` and acknowledged by Pro).
**Consultation:** ChatGPT Pro in Chat mode reviewed the initial candidates and two focused follow-ups on item 3's asynchronous logging design and module boundary against this verified snapshot. No repository changes were made by Pro; Codex independently checked the follow-ups' module, caller, configuration, and plan references locally.
**Local overlay:** None. The original local `main` checkout was clean at `9b57a37d75dae4f0defe44cc1a714b3f0661b540`, four commits behind the fetched snapshot.
**Validation status:** Static code and plan review only. No tests were run; the commands below are proposed focused checks.

These are independent, offline slices selected for small implementation scope and low-to-medium reasoning. “Verified” describes the source or test behavior; expected value and unexecuted failure scenarios are inferences.

| Rank | Slice | Effort | Reasoning | Suggested fit |
| --- | --- | --- | --- | --- |
| 1 | Make the transcript-cleanup concurrency test fail on either worker's errors | Small; test-only | Medium | Luna xhigh |
| 2 | Preserve privacy-safe exception context in JSON logs | Small; one formatter and focused tests | Low–medium | Devin |
| 3 | Introduce an isolated bounded async diagnostic writer, then migrate logging ownership | Small isolated core; medium end-to-end integration and caller migration | Medium | Devin can own the isolated core; Luna xhigh is preferred for integration, or Devin after the delivery contract is fixed |

## 1. Make the transcript-cleanup concurrency test fail on either worker's errors

**Evidence — verified:** In `tests/integration/persistence/test_chat_transcript_cleanup.py`, `ChatTranscriptCleanupTests.test_cleanup_read_modify_write_is_serialized_with_concurrent_store_writer` captures the writer thread's exception, but runs the cleanup thread through an unguarded lambda. It joins both threads with timeouts without asserting that either thread terminated. The final assertion checks only that the writer's `kept row` exists; it does not prove cleanup completed or removed the targeted row.

**Failure scenario — inferred, not reproduced:** If cleanup raises after the test's synchronization point, Python reports the background-thread exception outside the parent test. The writer can still append successfully and satisfy the final assertion, leaving a false pass.

**Bounded slice:** Change only that test module. Capture cleanup's result and exception in the parent test, assert both workers terminate, and release the synchronization gate in a `finally` block. Do not change production locking.

**Acceptance:** The ordinary case proves cleanup removed the matching row, the writer appended its row, and both threads exited. A deterministic injected cleanup exception after synchronization fails the parent test even when the writer succeeds. A writer exception also fails the parent test, and a failed assertion cannot strand a worker.

**Assignment:** Small effort, medium reasoning; best fit Luna xhigh because the code is short but the concurrency proof needs care.

**Focused validation:** `py -3.13 -m unittest tests.integration.persistence.test_chat_transcript_cleanup`

**Overlap:** The existing test-modularity and archive plans do not specify this worker-error assertion repair. Keep it separate from production archive behavior and test-directory migration.

## 2. Preserve privacy-safe exception context in JSON logs

**Evidence — verified:** `pnc_automation/core/infra/diagnostics/logging_setup.py` defines `JsonLogFormatter.format` and reserves `exc_info`, `exc_text`, and `stack_info` without serializing their contents. `configure_logging` installs the formatter on both the stream handler and optional rotating JSONL handler. Existing tests mock logging configuration but do not directly exercise JSON exception formatting.

**Value — inferred:** Failure logs can omit the source location and exception type needed to diagnose an error. Pro recommended including the exception message and traceback; Codex narrows that design to honor `AGENTS.md`'s secret-redaction rule.

**Bounded slice:** Keep the production change in `logging_setup.py` and add `tests/unit/core/infra/diagnostics/test_logging_setup.py`. Serialize exception class and sanitized frame metadata (module or file name, function, and line), including chained exception frames and `stack_info`. Do not emit raw exception text, absolute paths, or local-variable values. Leave handler setup, rotation, call sites, and logging frequency unchanged.

**Acceptance:** Each record remains one parseable JSON line. Exception type and sanitized frame metadata survive, including a chained cause and supplied stack information. A test exception containing a secret sentinel in its message and a local variable does not leak either value. Ordinary records, structured extras, and the input `LogRecord` remain unchanged.

**Assignment:** Small effort, low-to-medium reasoning; best fit Devin for a localized serializer with focused in-memory tests.

**Focused validation:** `py -3.13 -m unittest tests.unit.core.infra.diagnostics.test_logging_setup`

**Overlap:** The reviewed world-map follow-up covers which events callers emit and when they flush them. This item changes formatter output only; it does not alter those policies.

## 3. Introduce an isolated bounded async diagnostic writer, then migrate logging ownership

**Evidence — verified:** `pnc_automation/core/infra/diagnostics/buffered_logging.py` stores `BUFFERED_SEQUENCE` events in a list attached to per-search runtime state, then `flush_buffered_diagnostic_logs` calls the logger synchronously for each event. `_buffer` revalidates the accumulated list on access, and flush removes entries with `pop(0)`. The world-map search path, movement calibration service, and route-preview tool all flush through this helper. `pnc_automation/core/infra/diagnostics/logging_setup.py` installs a `StreamHandler` and optionally a `RotatingFileHandler`; `configure_logging` closes and replaces current handlers and does not own an asynchronous writer. `build_application_runner` configures logging, but there is no shared diagnostic-writer shutdown lifecycle. The separate P2 analysis worker is not the diagnostic writer. The reviewed world-map implementation plan explicitly requires sequence-boundary flush semantics.

**Impact — unmeasured:** Handler I/O at a sequence boundary runs on the search/calibration caller and may delay its return. Neither queue sizes nor sink latency have been measured, so this is a bounded asynchronous-delivery improvement, not a quantified traversal-speedup claim. Batching records for dispatch also does not imply one disk write per batch when the existing handlers still format and emit records individually.

**Bounded slice:** Deliver one end-to-end change in three stages; only the isolated core is independently complete. Keep movement, route generation, the P2 analysis queue, and quadratic route rebuilding unchanged.

1. **Isolated core:** Add `pnc_automation/core/infra/diagnostics/async_diagnostic_writer.py` as a small writer of already-prepared diagnostic records, with a bounded FIFO, one consumer thread, count/deadline batching, finite producer backpressure, visible failure state, and close/drain/join lifecycle. Inject a `write_batch(records)` callable. Use Python's synchronized [`queue.Queue`](https://docs.python.org/3.13/library/queue.html#queue.Queue); do not build a lock-free queue, general background-task framework, handler registry, or file-opening/logging setup into this module. It must not import configuration or traversal code. Test the real queue/thread behavior using controlled fake sinks and events/barriers; use a narrow deterministic deadline seam rather than arbitrary sleeps. These tests can prove FIFO delivery on one consumer, maximum batch size, partial-batch deadlines that a trickle cannot postpone, bounded admission timeout without overwriting accepted work, latched sink errors, and healthy/failing shutdown behavior. This stage is a reviewable intermediate result only: label it “core implemented; integration pending.”
2. **Logging integration:** Keep `buffered_logging.py` as the producer-facing facade for immediate versus queued delivery. Choose a mode name that describes asynchronous queueing, not sequence buffering. Prepare each record once before enqueueing, including its producer timestamp and merged adapter/event extras, with explicit snapshot behavior for supported mutable extras; update formatting to retain that producer timestamp instead of assigning a formatting-time timestamp. Keep `IMMEDIATE` synchronous and route each queued event to the configured sinks exactly once. `logging_setup.py` owns one configured writer and its real handlers: repeated identical configuration reuses a healthy owner; changed configuration stops old admission and drains/joins the old writer before replacing its sinks. Expose an explicit shutdown operation for tests and embedded callers, and wire application/process shutdown to stop producers, drain/join the writer, then flush/close owned handlers before standard logging teardown. Surface handler failures even when the default `handleError` path would otherwise swallow them; latch the first asynchronous failure, make later submission/shutdown report it, wake blocked producers, and never automatically replay a batch that may have been partly delivered.
3. **Caller migration and retirement:** Remove traversal flush calls from world-map search, movement calibration, and route preview; retire per-search buffer state and the old flush API. Preserve unrelated failure cleanup, profiling finalization, and the separate viewport-analysis queue's close. Update the narrow logging clauses in `plans/reviewed/world-map/PNC_WORLD_MAP_SEARCH_IMPLEMENTATION_PLAN.md` to remove sequence-flush semantics. Do not keep a no-op drain API or misleading per-search state/name compatibility. Activate stages 2 and 3 together so production does not temporarily mix asynchronous ownership with traversal-owned flush expectations.

Use a finite queue-admission wait and report timeout to the producer if capacity stays full. Do not silently drop/overwrite, grow an unbounded overflow buffer, or fall back to synchronous writes that can reorder queued events. The FIFO guarantee is among accepted queued records; synchronous immediate records may interleave with queued output. A sink failure after acceptance cannot be returned to its original producer, so it must be reported by subsequent submissions and shutdown. No automatic batch retry is safe when delivery may have reached some handlers before failing. No wall-clock performance threshold or claim of coalesced disk writes is required.

**Acceptance:** Stage 1's focused unit module proves the core contract with an injected sink, deterministic deadlines, bounded queue/backpressure, failure visibility, and shutdown/race behavior. After integration, tests prove immediate logging stays synchronous; accepted async events arrive in FIFO order through one consumer, once per configured sink, retaining producer-time timestamps and snapshotted merged extras. Partial batches emit without a later submission, and a continuous trickle cannot postpone the oldest record. A full queue times out visibly without evicting accepted events. Real handler errors remain visible even with `logging.raiseExceptions` disabled. Reconfiguration drains to old sinks before replacement and never leaves two active writers. An offline process-exit check proves the application owner drains before handlers close. Search/calibration/preview no longer flush on traversal boundaries; accepted diagnostics still drain after traversal failure, and logging shutdown failure does not replace a movement exception. The old buffered-logging and flush-spy expectations are replaced with the new producer/lifecycle contract. No live validation is needed.

**Assignment:** The isolated writer and fake-sink tests are a small low-to-medium reasoning slice suitable for Devin. The full change is medium effort and medium reasoning because lifecycle, handler routing, and caller migration must agree; Luna xhigh is preferred for that integration, or Devin after these semantics are fixed in the assignment. Do not delegate this as a list-to-`QueueListener` substitution.

**Focused validation:** `py -3.13 -m unittest tests.unit.core.infra.diagnostics.test_async_diagnostic_writer` for stage 1. On integrated completion, run `py -3.13 -m unittest tests.integration.persistence.test_buffered_logging tests.integration.workflows.test_world_search_movement_proof tests.unit.app.pnc.navigation.test_world_map_movement_calibration tests.unit.tools.test_preview_world_map_search_route tests.unit.core.infra.diagnostics.test_logging_setup` plus a focused offline subprocess shutdown check (`test_async_diagnostic_writer` and `test_logging_setup` are proposed new modules.)

**Overlap and local gate:** The reviewed world-map follow-up discusses caller flush placement; this item replaces those flush boundaries while excluding its separate route-rebuilding concern. Before activation, map actual process and embedded-application shutdown paths and add the narrow lifecycle coverage needed for each. The existing plan's sequence-flush requirement must be amended as part of integration so guidance agrees with application-owned writer lifetime. No live validation is needed.

## Codex review of the Pro findings

- Accepted the cleanup-worker blind spot and JSON formatter omission as grounded candidates. Pro recommends a separate injected-sink writer core tested in isolation, with logging ownership and caller migration integrated afterward as one end-to-end item. Producer stalls, partial sink delivery, shutdown, and reconfiguration remain integration risks; practical traversal impact is unmeasured.
- Applied the repository's redaction rule to the logging recommendation: preserve exception types and safe frame locations, not raw exception messages or local values.
- Dropped archive hashing as a candidate because the current chat archive already stores and validates transcript length and SHA-256 evidence, with recovery tests for tampering.
- Before assigning any item, check active local branches and worktrees for unpublished ownership. Queue-size distributions and the practical performance gain remain unknown.
