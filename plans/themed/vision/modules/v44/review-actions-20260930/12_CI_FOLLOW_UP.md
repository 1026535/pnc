# 12 — Repair remaining CI issues separately from V44 acceptance

> Supporting V44 case study from the first planning pass. The [velocity roadmap](README.md) and [cause assessment](00_ROOT_CAUSES.md) supersede its priority and current-status assumptions. Reconcile historical candidate, ownership and policy notes before execution; this document is not a live assignment.

Priority: separately owned infrastructure follow-up. Owner: existing test-performance/CI owner; persistence owner for any demonstrated archive defect. Review coverage: §4F, with §4C treated by 09.

## What is already implemented

At candidate `1d683cf8`, `.github/workflows/tests.yml` uses static `affected`, explicit base validation, four Windows shards, immediate verbose output, unique shard artifacts and an aggregate `Portable tests (affected)` check. It has no routine `measure` or `--contexts`. `tests/README.md` and [existing runtime slices](../../../../testing/PNC_CI_RUNTIME_INDEPENDENT_SLICES.md) describe the same design. Preserve it.

The [CI correction handoff](../../../../testing/PNC_CI_AFFECTED_TESTS_HANDOFF.md) and [later follow-up](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/v44-ci-affected-handoff-supplement-20260928.md) distinguish the first coverage run from the later affected run. The later affected run still selected 358 modules, hit the 30-minute limit and had one error/two failures. Progress near timeout does not establish a freeze; the last active test is not necessarily a failing test. Root build/egg-info artifact exclusions were already fixed. Historical failed/unfinished runs remain failed/unfinished.

The V epic's recorded hosted-CI waiver permits its authorized local acceptance path; it does not waive local checks or required final-candidate live proof. Current hosted health was not inspected for this plan. Do not infer an active defect from an old cancelled run or remove the waiver without its owner's decision.

## Deliverables

1. **Reconcile current CI work before changing code.** Check the existing CI owner/handbacks and later accepted commits. Determine whether each historical issue is already fixed. Use the exact run/candidate/log evidence for any still-open issue; inspect recent hosted runs only when executing this CI task, not by launching a fresh run for diagnosis.
2. **Triage named failures narrowly.** The follow-up identifies `tests.integration.persistence.test_chat_archive_recovery.ChatArchiveRecoveryTests`: `test_archive_day_preserves_host_local_legacy_path_resolution`, `test_dst_local_day_overlap_keeps_target_day_transcript_boundary`, and `test_midnight_overlap_state_starts_new_transcript_at_zero`. They passed later locally, so timezone portability is a hypothesis, not diagnosis. Capture full tracebacks under the relevant hosted conditions; use the smallest owning persistence group. Do not start with another full suite.
3. **Separate duration from correctness.** Read existing shard/module timing evidence. Determine whether current selection breadth, one long module, setup cost or a real failing test dominates. Route owned-fixture fallback work to 09. Shared matcher optimization belongs to its measured owner; do not lower vision gates or remove meaningful assertions to finish before timeout.
4. **Implement only a demonstrated defect.** Persistence fixes stay with persistence code/tests. Workflow wiring changes preserve event-base mapping, exit-code propagation, shard disjointness/completeness and required aggregate gate. If no current defect is demonstrated, close the historical follow-up with evidence or retain its exact observation gap rather than changing code speculatively.
5. **Validate the changed boundary.** Use `tools/run_tests.py group integration.persistence` for a reproduced archive failure; use `group unit.test_selection` / `group test_harness` for selector/sharding/runner changes. Workflow command-routing validation should execute the actual script with the test command stubbed, retaining real Git base checks. One finished-candidate affected gate follows any source/infrastructure fix; full fallback is expected for cross-cutting changes.
6. **Observe the next relevant hosted outcome.** If an authorized push naturally creates a run, inspect that exact candidate and all four shards. Confirm expected base, no generated-path pollution, static affected reasons, no routine measurement, retained named failures if any and aggregate result. A timeout after a meaningful fix is evidence for the next diagnosis; an unchanged broad rerun is not useful progress.

## Acceptance and boundaries

- [ ] Each historical failure has current reproduction/fix proof, a later passing same-scope disposition, or a precise remaining evidence gap.
- [ ] Current workflow contracts remain intact; no failed shard is ignored to make the aggregate green.
- [ ] Any claimed runtime improvement uses comparable existing or necessary new runs and distinguishes instrumentation from normal execution.
- [ ] Hosted success is claimed only for a completed observed run; no timeout is relabeled passing.
- [ ] V44's separate local/live acceptance and policy waiver remain accurately recorded.

No BlueStacks test is required for CI/test infrastructure. Do not touch rulesets, purchase capacity, increase timeout or dispatch hosted runs merely to clear a status without a justified implementation change and the appropriate task scope. These plans authorize preparation, not those external actions.
