# Portable offline tests

`unittest` is authoritative. Run commands from the repository root with Python
3.13 or newer. On Windows, install the test extra in a virtual environment:

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install ".[test]"
.venv/Scripts/python.exe tools/run_tests.py group test_harness
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
# A tier, component, qualified tier/component, or the api/vision aliases.
.venv/Scripts/python.exe tools/run_tests.py group unit
.venv/Scripts/python.exe tools/run_tests.py group unit.core.vision
.venv/Scripts/python.exe tools/run_tests.py group api
.venv/Scripts/python.exe tools/run_tests.py group test_harness

# Complete portable inventory for a manual baseline.
.venv/Scripts/python.exe tools/run_tests.py full

# Inspect affected selection without importing or executing test modules.
.venv/Scripts/python.exe tools/run_tests.py affected --base origin/main --dry-run --explain

# Execute affected selection and retain its reasoning and results.
.venv/Scripts/python.exe tools/run_tests.py affected --base origin/main --explain --json .test-impact/selection.json --results .test-impact/results.json --csv .test-impact/timings.csv

# Full instrumented run: branch coverage and per-test timing.
.venv/Scripts/python.exe tools/run_tests.py measure --csv .test-impact/measurement-timings.csv

# Full measurement with opt-in per-test contexts and empirical seed publication.
.venv/Scripts/python.exe tools/run_tests.py measure --contexts --csv .test-impact/measurement-timings.csv

# Hybrid selection: component-owned units plus covered contract/integration tests.
.venv/Scripts/python.exe tools/run_tests.py affected --base origin/main --contexts --explain

# Direct unittest execution for one named regression module.
.venv/Scripts/python.exe -m unittest tests.unit.test_selection.test_planner

# Compare a saved affected plan with independent full/measure results.
.venv/Scripts/python.exe tools/audit_test_selection.py .test-impact/audit-selection.json .test-impact/results.json --output .test-impact/audit-result.json
```

`group` or a named test module is the focused development path. Run `affected`
once on the finished source candidate when downstream consumers need checking;
reuse a passing worker result for the same candidate and scope. Neither mode
automatically expands to unrelated tiers. `full` is the post-merge, nightly,
manual, and fail-closed baseline. `measure` runs the
full inventory with instrumentation; compare its timings separately from
uninstrumented `full`.
The runner limits collection to the four portable tiers. Existing opt-in live
tests and commands remain separate; none of these commands authorizes or starts
live testing. No emulator, ADB, account credentials, or live game state is needed.

The opt-in Chat smoke runs exactly one typed, receipt-confirmed send and then
requires the replacement workflow to return Home. Set
`PNC_RUN_LIVE_CHAT_SMOKE=1`, `PNC_LIVE_CHAT_CHANNEL=world` or `alliance`, and
`PNC_LIVE_CHAT_MESSAGE` explicitly before running
`py -m unittest tests.test_live_chat_workflow_smoke`. The account defaults to
the configured `testing` account and must have the `SMOKE_TEST` role;
`PNC_LIVE_CHAT_CONFIG`, `PNC_LIVE_CHAT_ACCOUNT`, and
`PNC_LIVE_SESSION_CLEANUP` may override the configured path, account, and phase
cleanup policy. Missing or invalid channel/message values fail before a live
connection is built. This smoke sends one message only; it does not generate a
default payload or exercise both channels in one run.

## Selection safety and limits

`affected` uses Git base/candidate source graphs, reverse imports, component
ownership, and `tests/selection_rules.yaml` resource rules. `--base` supplies
the comparison revision; when omitted the runner attempts its upstream merge
base. Local tracked and untracked changes participate in selection. Use an
explicit base SHA for reproducible CI evidence.

Without `--contexts`, code changes add mandatory contract and architecture
modules. With `--contexts`, production Python changes use directory-derived
unit ownership and the coverage seed for contract and integration modules;
architecture checks remain mandatory. A nonproduction Python helper or tool
change uses static selection instead, since the coverage seed records only
production files. A directly changed test module always runs. Only unchanged
or explicitly documented documentation-only changes may select no tests.
Unknown groups and unexpectedly empty collection are errors. `--dry-run`
proves selection only and produces no execution result.

Selection broadens to the full portable suite when it cannot establish safe
ownership: shared test infrastructure, packaging/dependencies, public contract
changes, added/deleted production modules, unresolved dynamic imports, unknown
resources, or unavailable base/analysis evidence. The selection JSON records
each module's reasons and every full fallback. Static imports cannot completely
describe reflection, plugins, source-as-data, or arbitrary external resources;
affected success is the merge-candidate gate, with the residual risk that an
unmodeled dependency could be missed until the post-merge full run.

`measure` always runs the full portable inventory and writes branch coverage and
timing evidence. It does not switch per-test Coverage contexts or manipulate
`.test-impact/contexts.json`. `measure --contexts` additionally records which
test module executes each production file and writes `.test-impact/contexts.json`
only after a successful, complete run; stale or incomplete context-learning
state is removed. Test collection uses a separate context and does not make an
imported production module appear covered by every feature test. Dynamic test
contexts begin before per-test setup and reset after cleanup; unattributed
class/module-fixture execution remains conservatively owned by every module.

For `affected --contexts`, coverage selects only contract and integration
modules when a partial plan changes production Python. It does not add unrelated
unit modules: low-level units continue to run by component ownership.
Architecture checks remain static because they inspect source rather than
execute it. Explicit non-Python resource ownership, a directly changed test,
and full-suite safety fallbacks also remain authoritative. Empty plans,
already-full plans, and changes without production Python do not read a seed.
For a partial production change, a missing, corrupt, stale, or incompatible
seed forces a full run. Compatibility
requires the base SHA, Python-source fingerprint, policy version, base test
inventory, Python/platform, and installed package versions to match. A newly
added test module may extend the inventory only when its path is in the change;
it is selected directly. A removed or unexplained module forces a full run.
Runtime observations do not establish dependencies on unexecuted branches or
non-Python files.

The context store is generated evidence, not release evidence. Pushes to `main`
and nightly runs create it from a successful full measurement and save it under
an exact commit-SHA cache key. Pull requests and merge groups restore only the
key for their base SHA; the runner independently revalidates every provenance
field and falls back to the full suite on a cache miss or mismatch. Neither
publishes a seed. Ordinary local runs use their local
`.test-impact/contexts.json`. Use separate output paths for independent runs;
atomic replacement prevents partial files but does not combine competing reports.

## Evidence and exit status

Default selection and result paths are `.test-impact/selection.json` and
`.test-impact/results.json`. `--json`, `--results`, and `--csv` override those
outputs. `measure` defaults its timing CSV to
`.local-data/reports/test_timings.csv` and writes coverage evidence under
`.test-impact/`. Generated evidence is local and ignored by Git. Use
`.local-data/reports/` for routine reports, timing CSVs, and similar outputs;
use `.test-impact/` for test-selection scratch evidence.

To retain a weekly full-run history instead of overwriting the latest evidence,
pass `--archive-report-dir`:

```powershell
.venv/Scripts/python.exe tools/run_tests.py full --archive-report-dir .local-data/reports/test-timing-weekly
```

Each completed run creates a UTC-stamped child directory containing
`results.json`, `timings.csv`, and `summary.json`. Archive persistence happens
after the timing snapshot, so its write time is not included in the run phases
or `total_run_seconds`.

Results retain the complete portable module inventory, discovered test IDs and
their module/class identities, outcomes, skip reasons, and setup-through-cleanup
durations. Result JSON also records selection, collection, execution, and
reporting phase durations, the sum of per-test durations, unattributed wall time,
and module-level timing/status summaries. Every outcome records its explicit
module owner, scope, fixture phase, and accounted-for test IDs. Class/module
setup errors or skips account for the discovered tests they prevented from
running; teardown outcomes do not excuse missing execution. Fixture IDs are not
parsed as ordinary test method IDs.

CSV rows repeat provenance: run ID, commit SHA, source fingerprint,
UTC timestamp, Python/tool versions, portable fixture profile, and total run
time, alongside phase totals, owner, tier/component, and per-test fields. The
reporting phase covers coverage finalization and report preparation; artifact
write overhead is measured outside the timing snapshot and is not included in
the run phases or `total_run_seconds`. The run/selection source fingerprint includes file-byte hashes for tracked
files and non-ignored untracked files, including resource and YAML changes. It
is separate from the Python-only source fingerprint used to validate coverage
context seeds. JSON publication is atomic.
Check both command status and result evidence; a selection-only artifact is
not a passing run. Exit codes are `0` for success (including a documented empty
selection), `1` for test failures/errors, and `2` for runner/configuration errors.

## CI and the external merge gate

`.github/workflows/tests.yml` uses hosted Windows and Python 3.13. It has no path
filters. PR and merge-group events restore the exact-base coverage map and run
`affected --contexts` on GitHub's merge candidate. Superseded PR runs cancel.
A missing or invalid map makes the selector run the full suite; this can occur
when a merge group's base includes earlier queued changes. Pushes to `main`
and nightly runs execute `measure --contexts` over the full portable inventory
and publish the trusted SHA-keyed map. Manual dispatches run `full`.
Before its measurement, the nightly job records a separate
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

A passing **affected check on the current merge candidate is required before
merge**. It runs the full suite when selection cannot establish safe ownership
or a compatible coverage seed. An administrator must configure the required
check/ruleset externally; adding this workflow alone does not enforce that
policy. Require `Portable tests (affected)` for PRs and, when a merge queue is
used, for queue candidates. The post-merge `main` run and nightly measurement
retain the independent full baseline. Manual `full` remains available when a
specific risk calls for it. If a ruleset still requires `Portable tests (full)`
for merge groups, update that requirement when this workflow is rolled out;
otherwise queued merges will wait for an obsolete check. Repository settings
are not changed here.

The event and checkout choices follow the official
[GitHub Actions event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
and [checkout ref documentation](https://github.com/actions/checkout#usage).
Context attribution uses the documented
[Coverage.py 7.10.7 API](https://coverage.readthedocs.io/en/7.10.7/api_coverage.html).
