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

Validated code commit: `d99fdb1389ffb5eed43e42c6e3a8c3c2aa16f795` (Python 3.13.5, Windows 11). Executable sources were committed; the previous generated timing CSV was the only dirty tracked file when validation began, and its bytes participate in the recorded candidate fingerprint. The subsequent evidence-only commit changes this report, the experiment decision note, and the timing CSV, not executable code. Final inventory is **1,363 tests in 241 modules**: 811 unit, 48 contract, 482 offline integration, and 22 architecture cases. Every original logical ID is preserved; the 175 additional cases protect the selector, harness, and production ownership boundaries.

Commands below use `.venv/Scripts/python.exe` from the feature worktree. All paths under `.test-impact/` are ignored generated evidence.

| Check | Result |
| --- | --- |
| `tools/run_tests.py full --json .test-impact/final-full-selection.json --results .test-impact/final-full-results.json --csv .test-impact/final-full-timings.csv` | **Passed:** 1,359 passes, four optional-fixture skips; 116.777 s including selection/collection/reporting |
| `tools/run_tests.py measure --json .test-impact/final-measured-selection.json --results .test-impact/final-measured-results.json --csv test_timings.csv` | **Passed:** same 1,363 IDs/outcomes; 272.648 s; 1,363 unique, provenance-bound CSV rows |
| `pytest.main(['tests/unit', 'tests/contract', 'tests/integration', 'tests/architecture', '-q', '--junitxml=.test-impact/pytest-parity.xml'])` with plugin autoload disabled, portable profile, and inherited live flags removed | **Passed:** 1,359 passes, four skips, 464 passing subtests; 117.22 s. Testmon was not loaded |
| `.test-impact/verify_final_evidence.py` | **Passed:** exact unittest/pytest test-ID and outcome parity; full/measure/CSV identity and provenance agree |
| `tools/run_tests.py group api --json .test-impact/api-final-selection.json --results .test-impact/api-final-results.json --csv .test-impact/api-final-timings.csv` | **Passed:** 36 tests in eight modules; 6.720 s total in this sample |
| `tools/run_tests.py group test_selection` | **Passed:** 106 selector cases, including the 45-case mutation matrix |
| `tools/run_tests.py group architecture` | **Passed:** 22 architecture cases |
| `tools/run_tests.py group test_harness` plus the final added `tests.unit.test_harness.test_runner_cli` module | **Passed:** 48 harness cases plus seven CLI cases; all 55 also passed in the final full run |
| `-m unittest tests.integration.workflows.test_daily_application_service -v` | **Passed:** four cases after the deterministic concurrency repair |
| `.test-impact/audit_test_migration.py` and `.test-impact/check_migration.py final --inventory-only` | **Passed:** 1,188 unique migrated IDs, 1,187 unchanged normalized methods, one explicitly documented repaired method; protected files and stdlib tempfile unchanged |
| Baseline worktree `.test-impact/measure_baseline.py` at `aabe85b` | **Passed:** 1,184 passes, four skips, no live modules imported; coverage baseline below |
| `tools/run_tests.py affected --base origin/main --dry-run --json .test-impact/final-audit-selection.json` then `tools/audit_test_selection.py .test-impact/final-audit-selection.json .test-impact/final-full-results.json --output .test-impact/final-audit-result.json` | **Passed:** same candidate/resource fingerprint, complete full execution, no observed misses. This cross-cutting feature correctly selects all modules; an all-passing run is not a recall proof |
| `tools/run_tests.py affected --base HEAD --contexts --dry-run --json .test-impact/context-seed-verification.json` | **Passed:** actual measured context seed accepted; the changed tracked CSV independently triggers the documented unknown-resource full fallback |
| `tools/experiment_test_selection.py` and `--refresh-native` | **Passed as an experiment:** 34 independent fault cases; native selector zero misses with 28 full fallbacks. Raw testmon had 12 false greens and a corrupt-cache error; adoption rejected |
| `git diff --check` / staged whitespace checks | **Passed** |
| Live smokes, ADB/BlueStacks validation, and `tools/validate_navigation_selectors.py` | **Skipped by explicit user instruction.** The selector validator is a live tool, not an offline check |
| Hosted GitHub Actions execution and required-check/ruleset activation | **Not performed:** workflow code is supplied; external repository settings were not changed |

Earlier development runs failed on then-incomplete selector/audit fixtures and the concurrency sleep. Those failures were investigated and superseded by the focused regression checks and the two complete passing runs above; they are not counted as passing evidence.

An in-memory API-body-only candidate selected **15/241 modules with no full fallback**, retaining every contract/architecture guard and unresolved dynamic consumers. Planning took 3.838 s in that sample; this is selection-only evidence, not execution of a mutated repository. Named API execution does not import the unrelated full inventory. Intermediate API timing samples ranged from 3.2 to 6.7 s total; these are observations, not a controlled benchmark or a promised speedup.

### Coverage comparison

| Production coverage | Pre-refactor `aabe85b` | Validated `d99fdb1` |
| --- | ---: | ---: |
| Covered / possible lines | 19,525 / 22,619 | 19,562 / 22,654 (86.35%) |
| Covered / possible branches | 5,419 / 7,848 | 5,421 / 7,850 (69.06%) |
| Missing lines / branches | 3,094 / 2,429 | 3,092 / 2,429 |
| Combined Coverage.py percentage | 81.8722% | 81.9007% |

No existing common file gained missing branches. The new application `__dir__` return remains one uncovered introspection line. The baseline and candidate used the same Python/Coverage.py tuple, coverage source, and portable fixture availability. Instrumented timing is not comparable to uninstrumented timing: the candidate also collects per-test contexts and has 175 additional cases. Candidate measurement overlapped the independent pytest run; do not infer a performance regression from its wall time versus the baseline's 170.18 s. Historical CSV schemas/environments are likewise not directly comparable.

Coverage is a baseline, not a claim of exhaustive behavioral assurance. About 31% of branch opportunities remain uncovered, and optional local screenshot cases remain explicitly skipped. No arbitrary percentage threshold was introduced. Static selection cannot prove dependencies from arbitrary reflection or unmodeled source-as-data; mandatory checks, explicit ownership, fault tests, and independent full validation remain necessary.

Detailed local evidence: `.test-impact/final-verification.json`, `.test-impact/final-full-results.json`, `.test-impact/final-measured-results.json`, `.test-impact/coverage.json`, `.test-impact/base-metadata.json`, `.test-impact/base-coverage.json`, `.test-impact/pytest-parity.xml`, `.test-impact/repository-selection-probe.json`, and `.test-impact/testmon-experiment/results.json`. The committed `test_timings.csv` retains the tested code SHA, source fingerprint, fixture profile, tool versions, outcome, and duration on every row.

## Use

```powershell
py tools/run_tests.py group api
py tools/run_tests.py group vision
py tools/run_tests.py affected --base origin/main --explain
py tools/run_tests.py full
py tools/run_tests.py measure --csv .test-impact/timings.csv
```

`group` is focused debugging; `affected` adds dependency and contract guards. `full` is the bypass and merge baseline. See `tests/README.md` for setup, groups, cache safety, audit limitations, and the exact-candidate external merge gate.
