# Offline test modularity implementation

Implemented on `codex/test-components`, starting at `aabe85b007a74150303ac9ec43e0bf6fc1fc7e37` in an isolated worktree. The original checkout and its unrelated work are preserved.

## Scope and decision

The user's latest instruction supersedes the plan's live-validation matrix: **offline validation only; no live testing work now**. Existing opt-in live test files remain unchanged and outside the portable runner's collection roots. No BlueStacks, ADB, live navigation, or resource-changing validation was performed. Runtime ownership changes are not presented as live promotion evidence.

Keep `unittest` authoritative. Use named component groups and a repository-native conservative affected selector for development. Keep an independent full portable check before merge and nightly. Coverage contexts are optional, additive evidence, not a default selection dependency. pytest/testmon are an isolated experiment, not production test dependencies or a replacement runner.

## Delivered slices

- Preserved all 1,188 original tests outside the unchanged live files, with a unique old-to-new ID ledger and normalized AST audit. Split the five broadest suites and shared support by component. The original methods now occupy 226 focused modules: 650 unit, 48 contract, 482 integration, and eight architecture cases. New selector, harness, and architecture regressions add to that inventory.
- Removed the global tempfile monkeypatch from `tests/__init__.py`. Portable execution excludes optional machine-local fixture configuration while retaining tracked default screenshot fixtures and explicit skips.
- Moved concrete task-registry and daily-runner construction to entrypoints, castle values to the domain, and neutral observation mode to core vision. P&C-specific observation-artifact policy remains domain-owned. Public application exports load lazily; obsolete internal observation modules were removed and callers migrated. The existing canonical instance lease owner is deliberately unchanged.
- Added `tools/run_tests.py full|group|affected|measure`, directory-derived ownership, resource rules, unioned base/candidate AST dependencies, named lazy exports, and explanations. Unknown mappings and shared/public changes broaden selection; unresolved test/tool consumers are conservatively included. Contract and source-scanning architecture checks are mandatory for non-document changes.
- Added per-test outcome/timing CSV, branch coverage, opt-in coverage contexts, exact candidate/resource fingerprints, and atomic generated reports. Incompatible or interrupted measurement evidence cannot seed selection.
- Added PR affected checks and full merge-group/main/manual/nightly checks. Nightly audit requires complete independent execution and matching source/inventory evidence; fixture errors retain explicit ownership. GitHub branch-protection/ruleset activation remains an administrator action outside repository code.
- Added a repeatable isolated fault experiment and documented the testmon decision in `PNC_TESTMON_EXPERIMENT.md`.

## Review-driven hardening

Regression coverage addresses constructor/type-alias changes, unresolved dynamic test dependencies, executable files under documentation directories, filename-safe Git blob retrieval, stale or incomplete audit evidence, and unittest class/module fixture failures. Production source-scanning ownership checks live in the mandatory architecture tier.

An instrumented full run exposed an existing timing-sensitive concurrency test. Its 20 ms sleep was replaced with an opt-in, bounded event rendezvous that still fails if independent workers cannot overlap; serialization assertions remain unchanged. This is an explicit post-migration test hardening, not an assertion of byte-identical migration for that method.

Nine cohesive suites retain documented size exceptions rather than splitting one fixture/contract arbitrarily. The migration ledger and intermediate diagnostics remain ignored local evidence under `.test-impact/`.

## Validation evidence

Final execution counts, timing, coverage comparison, and reviewed commit are recorded below after the stable candidate completes validation. Full instrumented timings are not directly comparable to uninstrumented component timings or historical CSVs with different schemas/environments.

## Use

```powershell
py tools/run_tests.py group api
py tools/run_tests.py group vision
py tools/run_tests.py affected --base origin/main --explain
py tools/run_tests.py full
py tools/run_tests.py measure --csv .test-impact/timings.csv
```

`group` is focused debugging; `affected` adds dependency and contract guards. `full` is the bypass and merge baseline. See `tests/README.md` for setup, groups, cache safety, audit limitations, and the exact-candidate external merge gate.
