# Portable offline tests

`unittest` is authoritative. Run commands from the repository root with Python
3.13 or newer. On Windows, install the test extra in a virtual environment:

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install ".[test]"
.venv/Scripts/python.exe tools/run_tests.py full
```

The `test` extra pins Coverage.py to `7.10.7`. pytest/testmon are not required
and are not the selection authority. Any framework experiment must separately
prove inventory and outcome parity before adoption.

## Layout and commands

Portable modules live under `tests/unit`, `tests/contract`, `tests/integration`,
and `tests/architecture`. Below the tier, package directories describe the
owning component. `tests/support` contains shared offline fixtures and fakes.
Integration means offline integration here. Optional local screenshot fixtures
must skip with an explicit reason when unavailable. The runner sets
`PNC_TEST_FIXTURE_PROFILE=portable`: repository default fixtures can run, but
missing defaults skip without reading machine-local fixture configuration.

```powershell
# Complete portable inventory, including contract and architecture guards.
.venv/Scripts/python.exe tools/run_tests.py full

# A tier, component, qualified tier/component, or the api/vision aliases.
.venv/Scripts/python.exe tools/run_tests.py group unit
.venv/Scripts/python.exe tools/run_tests.py group unit.core.vision
.venv/Scripts/python.exe tools/run_tests.py group api
.venv/Scripts/python.exe tools/run_tests.py group test_harness

# Inspect affected selection without importing or executing test modules.
.venv/Scripts/python.exe tools/run_tests.py affected --base origin/main --dry-run --explain

# Execute affected selection and retain its reasoning and results.
.venv/Scripts/python.exe tools/run_tests.py affected --base origin/main --explain --json .test-impact/selection.json --results .test-impact/results.json --csv .test-impact/timings.csv

# Full instrumented run: branch coverage and per-test timing.
.venv/Scripts/python.exe tools/run_tests.py measure --csv .test-impact/measurement-timings.csv

# Full measurement with opt-in per-test contexts and empirical seed publication.
.venv/Scripts/python.exe tools/run_tests.py measure --contexts --csv .test-impact/measurement-timings.csv

# Optional context evidence can add tests to the static selection.
.venv/Scripts/python.exe tools/run_tests.py affected --base origin/main --contexts --explain

# Direct unittest execution for one isolated regression package.
.venv/Scripts/python.exe -m unittest discover -s tests/unit/test_harness -t . -v

# Compare a saved affected plan with independent full/measure results.
.venv/Scripts/python.exe tools/audit_test_selection.py .test-impact/audit-selection.json .test-impact/results.json --output .test-impact/audit-result.json
```

`full` is the routine portable baseline. `group` is a focused debugging command
and does not automatically add other tiers. `measure` runs the full inventory
with instrumentation; compare its timings separately from uninstrumented `full`.
The runner limits collection to the four portable tiers. Existing opt-in live
tests and commands remain separate; none of these commands authorizes or starts
live testing. No emulator, ADB, account credentials, or live game state is needed.

## Selection safety and limits

`affected` uses Git base/candidate source graphs, reverse imports, component
ownership, and `tests/selection_rules.yaml` resource rules. `--base` supplies
the comparison revision; when omitted the runner attempts its upstream merge
base. Local tracked and untracked changes participate in selection. Use an
explicit base SHA for reproducible CI evidence.

For code changes the runner adds mandatory contract and architecture modules.
Only unchanged or explicitly documented documentation-only changes may select
no tests. Unknown groups and unexpectedly empty collection are errors.
`--dry-run` proves selection only and produces no execution result.

Selection broadens to the full portable suite when it cannot establish safe
ownership: shared test infrastructure, packaging/dependencies, public contract
changes, added/deleted production modules, unresolved dynamic imports, unknown
resources, or unavailable base/analysis evidence. The selection JSON records
each module's reasons and every full fallback. Static imports cannot completely
describe reflection, plugins, source-as-data, or arbitrary external resources;
affected success is fast feedback and cannot replace the pre-merge full check.

`measure` always runs the full portable inventory and writes branch coverage and
timing evidence. It does not switch per-test Coverage contexts or manipulate
`.test-impact/contexts.json`. `measure --contexts` additionally switches
contexts and writes `.test-impact/contexts.json` only after a successful,
complete run; stale or incomplete context-learning state is removed.
Dynamic test contexts begin before per-test setup and reset after cleanup;
unattributed import/class/module-fixture execution belongs conservatively to
every module. With `--contexts`, observed dependencies are unioned with the
static selection and mandatory guards; they never remove tests. Missing,
corrupt, stale, or incompatible seeds force a full run. Compatibility requires
the base SHA, Python-source fingerprint, policy version, complete test module
inventory, Python/platform, and installed package versions to match. These
checks deliberately make evidence from a different environment ineligible.
Runtime observations do not establish dependencies on unexecuted branches or
non-Python files. Resource ownership and full fallbacks still apply.

The context store is generated evidence, not a trusted shared CI cache. PR and
ordinary local runs do not restore or publish context seeds; the nightly
`measure --contexts` job publishes its empirical seed alongside the other
measurement artifacts. Use separate output paths for independent concurrent
runs; atomic replacement prevents partial files but does not combine competing
reports.

## Evidence and exit status

Default selection and result paths are `.test-impact/selection.json` and
`.test-impact/results.json`. `--json`, `--results`, and `--csv` override those
outputs. `measure` defaults its timing CSV to
`.local-data/reports/test_timings.csv` and writes coverage evidence under
`.test-impact/`. Generated evidence is local and ignored by Git. Use
`.local-data/reports/` for routine reports, timing CSVs, and similar outputs;
use `.test-impact/` for test-selection scratch evidence.

Results retain the complete portable module inventory, discovered test IDs and
their module/class identities, outcomes, skip reasons, and setup-through-cleanup
durations. Every outcome records its explicit module owner, scope, fixture phase,
and accounted-for test IDs. Class/module setup errors or skips account for the
discovered tests they prevented from running; teardown outcomes do not excuse
missing execution. Fixture IDs are not parsed as ordinary test method IDs.

CSV rows repeat provenance: run ID, commit SHA, source fingerprint,
UTC timestamp, Python/tool versions, portable fixture profile, and total run
time, alongside owner, tier/component, and per-test fields. The run/selection
source fingerprint includes file-byte hashes for tracked files and non-ignored
untracked files, including resource and YAML changes. It is separate from the Python-only source
fingerprint used to validate coverage context seeds. JSON publication is atomic.
Check both command status and result evidence; a selection-only artifact is
not a passing run. Exit codes are `0` for success (including a documented empty
selection), `1` for test failures/errors, and `2` for runner/configuration errors.

## CI and the external merge gate

`.github/workflows/tests.yml` uses hosted Windows and Python 3.13. It has no path
filters. PR events run `affected` against the event's base SHA on GitHub's merge
candidate, with mandatory guards owned by the runner. Superseded PR runs cancel.
Merge groups, pushes to `main`, and manual dispatches run `full`. Nightly runs
at 07:23 UTC run `measure --contexts` over the full portable inventory for
branch coverage, timing evidence, and the empirical context map. Before
measuring, the nightly job records a separate
`affected --base HEAD^ --dry-run` plan in `.test-impact/audit-selection.json`.
Recording that plan is informational: a failure is visible but does not suppress
the independent full measurement. The full measurement's exit status remains
gating. After measurement, even if tests failed, the nightly job runs
`tools/audit_test_selection.py` when both the audit plan and full result files
exist. It requires matching candidate SHAs and full source/resource fingerprints
across the affected plan, result metadata, and full selection. The result must
come from `full` or `measure`, select the complete matching portable inventory,
and account for every discovered test with a terminal outcome or a matching
setup error/skip. Empty, stale, duplicate, unfinished, or incomplete evidence is
rejected. A complete failing run remains eligible for comparison.
Failed tests, errors, and unexpected successes outside the selection are listed
as missed failure IDs in `.test-impact/audit-result.json`; observed misses make
the audit command fail with exit code `1`. Invalid evidence returns `2` and
replaces any prior audit report with `audit_valid: false`; it cannot leave a stale
success report. A valid comparison with no observed misses returns `0`.
Missing input artifacts skip comparison and provide no audit evidence.

Zero observed misses is evidence about this run, not a proof of future selector
correctness: an all-passing full run cannot expose a missed failing test.
No numerical coverage threshold is enforced by this workflow.

Selection JSON, result JSON, timing CSV, nightly coverage JSON, the audit plan,
and the comparison report are uploaded even after a test failure;
install/collection failures may leave some artifacts absent.

Manual dispatch requires a `ref` input (commit SHA, branch, or tag). Checkout
uses that exact input, not an unconditional `main` checkout. For an auditable
final candidate, pass an immutable full commit SHA and verify the reported
`metadata.commit_sha` matches it. A branch/tag input resolves at checkout time.

A passing **full portable baseline on the current merge candidate is required
before merge**. An administrator must configure the required check/ruleset
externally; adding this workflow alone does not enforce that policy. With a
merge queue, require `Portable tests (full)` for the queue candidate. PR fast
feedback is named `Portable tests (affected)`.

Without a merge queue, the external merge policy must require a successful full
run bound to the current candidate SHA and invalidate it whenever that SHA
changes. GitHub attaches a dispatched workflow's check to its dispatch ref,
which can differ from the custom checkout input. Dispatch the workflow at a ref
whose SHA matches the requested candidate, and verify both check SHA and result
SHA, or use an external gate that validates the artifact's candidate SHA. Merely
running `full` on another branch, or checking it after a push to `main`, does not
satisfy the pre-merge requirement. Repository settings are not changed here.

The event and checkout choices follow the official
[GitHub Actions event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
and [checkout ref documentation](https://github.com/actions/checkout#usage).
Context attribution uses the documented
[Coverage.py 7.10.7 API](https://coverage.readthedocs.io/en/7.10.7/api_coverage.html).
