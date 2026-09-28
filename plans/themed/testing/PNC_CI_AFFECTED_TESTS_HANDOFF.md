# CI timeout diagnosis and affected-test handoff

Date: 2026-09-28. Owner: V-series coordinator, task
`01a0ce79-51bb-7961-8687-14a8b099ed4f`.

## Finding

The available evidence supports an overlong, instrumented full-suite run. It does
not show a frozen runner or a deadlock. The number of tests and coverage overhead
both contributed work, but this run cannot quantify their individual costs.

The workflow explicitly chose `measure --contexts` for pushes to `main`. It did
not ask the affected-test selector which modules this push needed. Its uploaded
selection records `mode: measure`, all **358 portable modules**, an empty changed
path list, no fallback reasons, and identical base/head SHA. This was an explicit
full measurement, not an affected-selection fallback or a stale running game.

GitHub cancelled job `109029834000` in
[run 36452309439](https://github.com/1026535/pnc/actions/runs/36452309439)
for commit `51f66c85c4304965d5f40aca9d77e449568ef880`. The check annotation says:
“The job has exceeded the maximum execution time of 30m0s”.

| UTC time | Evidence |
|---|---|
| 16:36:56 | Job started |
| 16:39:31 | Test step started after checkout and installation |
| 16:48:04 | First buffered progress chunk: 701 result markers |
| 16:59:56 | Another 223 markers and an OCR warning |
| 17:02:19 | Another 50 markers and an OCR warning |
| 17:06:59 | Another 1,021 markers; cancellation interrupted Python |
| 17:07:06 | Job completed as cancelled |

The test step had approximately **27 minutes 30 seconds** of the job's 30-minute
budget. Progress chunks contain **1,995 terminal test markers** in total. Their
timestamps describe log flushing, not precise per-test completion times.

The cancellation traceback was executing
`tests.unit.app.pnc.domain.test_match3_decisions.BaselineRankingTests.test_stable_coordinate_tiebreak_picks_the_first_action`
through `decide(QUIET_5X5, RULES_PLAIN)`, swap evaluation and match-shape scanning.
The class was verified against the published source. This is active computation
at cancellation, not evidence that this test caused a deadlock.

## Important unresolved evidence

The first progress chunk includes **one `E` and two `F` markers**. Therefore this
run cannot be described as otherwise green or as having only a time-budget
problem. The remaining markers are 1,986 dots and six skips. Default unittest
output deferred the failure details until the end, which was never reached.
Only `selection.json` was uploaded; no final result JSON, timing CSV or coverage
map survived. The failing test identities and tracebacks are **unknown**. Do not
guess them from the final interrupted match-3 method.

The existing local broad results and the 83-test license correction check remain
separate evidence. The exact runtime `d5e74688` also passed the delegated live
Home/World/Home, normalization, Institute and return checks. Those results do
not erase the unresolved CI failure markers or establish a green CI run.

## Implemented workflow correction

`.github/workflows/tests.yml` now invokes only the existing **static affected**
runner for every event, without `--contexts`, `measure` or an unconditional
`full` command. Coverage-cache restore/publication and the automatic full-suite
nightly audit were removed from this workflow. Explicit offline measurement and
audit commands remain available for separately assigned work.

| Event | Base used for selection |
|---|---|
| Pull request | PR base SHA, against GitHub's merge candidate |
| Merge queue | Merge-group base SHA, against the queue candidate |
| Push | Event `before` SHA, covering every commit in the push |
| Scheduled | `HEAD^`, against default-branch HEAD |
| Manual | Required `base` input, against required candidate `ref` |

The workflow rejects missing, all-zero, unavailable and non-ancestor bases before
running tests. It does not silently compare a multi-commit push only with `HEAD^`.
Named test output is enabled with `--verbose`, so later interrupted runs identify
the active test and earlier failure names. The check is consistently named
`Portable tests (affected)`; repository rulesets are unchanged.

**Affected does not guarantee a small test set.** The repository's existing
selector still expands to the complete inventory for shared contracts, test
infrastructure or unknown dependency ownership. The CI workflow itself matches
the `.github/*` full-scope rule. Consequently the first run containing this
workflow change can legitimately select every module. It will run without the
previous coverage instrumentation. No ownership rule was weakened to make the
numbers smaller, and the 30-minute timeout was not increased to conceal slow work.

The scheduled affected run is no longer an independent full baseline. If a full
measurement is wanted, give it a separate explicit assignment and suitable
execution budget. A ruleset requiring the old `Portable tests (full)` check
needs an administrator update; the PR/queue affected check name is unchanged.

## Evidence locations

Primary checkout: `C:/Users/lebel/pnc`.

- `.local-data/devin-vision-pipeline/ci-diagnosis-36452309439/job.log`:
  downloaded log for the specific cancelled job, including command, progress and stack.
- `.local-data/devin-vision-pipeline/ci-diagnosis-36452309439/artifact/selection.json`:
  GitHub artifact `portable-tests-36452309439-1`, artifact ID `10984609606`.
- `.local-data/devin-vision-pipeline/ci-diagnosis-36452309439/progress-summary.json`:
  counts extracted from the four buffered progress chunks.
- `.local-data/devin-vision-pipeline/v44-publication-ci-timeout-20260928.json`:
  job/check annotations and terminal disposition.
- `.local-data/devin-vision-pipeline/status.json`:
  coordinator ledger; `v44_implementation_slices.publication_ci` and the CI correction record.

Raw logs and generated validation outputs remain ignored. Authored workflow and
this handoff are tracked. No emulator or live test is required for this CI change.

## Validation completed and next owner

YAML structure and the single affected command were checked. Ten offline
PowerShell command-routing cases passed: PR, merge group, multi-commit push,
scheduled, manual, failing-test exit propagation, and rejection of missing,
all-zero, unavailable and non-ancestor bases. These execute the actual workflow
script with only the Python test command stubbed; Git resolution is real.

The real runner dry-run against `51f66c85` returned `mode: affected`, 358 selected
modules, and exactly one full-scope reason:
`shared contract/infrastructure: .github/workflows/tests.yml`. This confirms the
first corrected workflow run can still be broad. No application tests or live
actions were executed for this workflow-wiring validation. `git diff --check`
passed. The source change is limited to this handoff, the workflow and matching
`tests/README.md` documentation.

Commands and generated results:

- `py -3 C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/validate_ci_affected_workflow.py`
- `py -3 tools/run_tests.py affected --base 51f66c85c4304965d5f40aca9d77e449568ef880 --dry-run --explain --json .local-data/ci-affected-validation/selection-dry-run.json`
- `.local-data/ci-affected-validation/routing-results.json` and
  `selection-dry-run.json` in the task-owned publication worktree.

The coordinator ledger records the final correction commit and push state. This
handoff does not claim a new hosted CI pass before that run actually completes.

On the first new CI run, confirm `mode: affected`, the expected pushed range,
selected-module reasons and absence of measurement/coverage execution. Inspect
any named failures rather than treating a timeout-only annotation as the whole
test outcome. A large affected selection can still exceed 30 minutes; the saved
evidence does not promise otherwise.

The test-performance task owns broader runtime optimization. V44-4, Main access,
resource spending and further live validation remain outside this handoff. The
V coordinator owns publication of this scoped CI correction and its evidence;
the original timed-out run must remain recorded as incomplete.
