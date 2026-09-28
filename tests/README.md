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
automatically expands to unrelated tiers. `full` is the explicit manual and
fail-closed baseline. CI invokes `affected` for every event; the selector can
still require the full inventory. `measure` runs the full inventory with
instrumentation; compare its timings separately from
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

The context store is generated evidence, not release evidence. An explicit
successful `measure --contexts` run produces a seed for that exact candidate.
Consumers must supply a compatible seed themselves. CI uses static affected
selection without `--contexts`; it neither depends on a cache nor runs coverage
measurement to populate one. Existing offline measurement and audit commands
remain available for separately requested timing or dependency-learning work.

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

`.github/workflows/tests.yml` uses hosted Windows and Python 3.13, with no path
filters. Every event runs `tools/run_tests.py affected --base <resolved-base>`
without coverage instrumentation or `--contexts`. Named test output (`--verbose`)
keeps the active test and earlier failures identifiable if execution is interrupted.
Superseded PR runs cancel. The job retains its 30-minute limit.

| Event | Candidate | Comparison base |
|---|---|---|
| Pull request | GitHub merge candidate | PR base SHA |
| Merge queue | GitHub queue candidate | Merge-group base SHA |
| Push to `main` | Pushed SHA | Event `before` SHA, covering the whole pushed range |
| Scheduled | Default-branch HEAD | `HEAD^`, the last commit's parent |
| Manual | Required `ref` input | Required `base` input |

The base must resolve locally to a commit and be an ancestor of the candidate.
Empty, all-zero, unavailable or non-ancestor bases fail before test execution;
use explicit manual inputs for a first push without a usable previous SHA.
Manual inputs may be branches/tags, but immutable SHAs give reproducible evidence.
The checkout fetches history and honors the requested candidate ref.

**Affected selection can still select every test.** Shared contracts, test
infrastructure, unknown resources or uncertain dependency ownership retain the
selector's documented safety fallback. CI does not force a smaller set by
ignoring those dependencies. Selection JSON records the exact range, selected
modules and reasons. A missing coverage cache no longer causes a fallback,
because CI does not use coverage-based selection.

There is no automatic `full`, `measure`, coverage-cache publication or full-suite
nightly audit in this workflow. The scheduled run is affected-only and is not an
independent full baseline. Use explicit offline `full`, `measure` and
`tools/audit_test_selection.py` assignments when those results are needed.

Selection JSON, result JSON and timing CSV are uploaded after success or failure
when present. A hard interruption may leave only selection JSON; it is not a
passing result. For the diagnosed timeout and limits of the available evidence,
see [the CI diagnosis handoff](../plans/themed/testing/PNC_CI_AFFECTED_TESTS_HANDOFF.md).

A passing **affected check on the current merge candidate is required before
merge**. An administrator must configure the required check/ruleset externally;
adding this workflow alone does not enforce it. The check name is
`Portable tests (affected)` for all events. Any ruleset that still requires
`Portable tests (full)` must be updated separately. Repository settings are not
changed here.
