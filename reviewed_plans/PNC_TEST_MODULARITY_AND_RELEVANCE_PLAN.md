# PNC Test Modularity and Relevant-Test Selection Plan

## Context

This plan turns the current flat, mixed-responsibility test suite into component-owned test packages and adds conservative automatic relevance selection without making a framework migration the first dependency.

The plan is grounded in the clean repository commit `aabe85b007a74150303ac9ec43e0bf6fc1fc7e37`, which matched `origin/main` when this document was written. It also incorporates the GPT-6 Pro consultation performed against `68cec2daf35200f40d17ca764de01d065a6824f9`. The current commit is 41 changed paths and 4,079 insertions beyond that consultation baseline, including new popup-recovery and YOLO code and tests, so current repository evidence takes precedence where the two snapshots differ.

After the baseline test run and during plan review, unrelated concurrent work appeared in `script_runner.py`, the BlueStacks instance/resolver/session modules, and new session-cleanup/instance-shutdown modules. This plan did not author or validate those changes. Implementation must preserve them, reconcile their ownership with this plan, and rerun Phase 0 from the eventual feature-branch base before relying on the counts or timings below.

Evidence labels used below:

- **Observed**: read or executed against the current checkout.
- **Prior measurement**: produced locally against the earlier `68cec2d` baseline.
- **Pro review**: independently inspected in the repository-linked GPT-6 Pro consultation; its supplied coverage measurements were not rerun by Pro.
- **Inference**: a design conclusion that must be validated during implementation.

Internet guidance informing the design:

- Python `unittest` can select modules, classes, methods, and repeated `-k` patterns, so a new test framework is not required for named or computed subsets: <https://docs.python.org/3/library/unittest.html#command-line-interface>.
- Coverage.py dynamic contexts can answer which test executed a line, but initialization and code between test contexts can remain unattributed: <https://coverage.readthedocs.io/en/latest/contexts.html>.
- pytest can run existing `unittest.TestCase` tests, but does not support `load_tests`, and ordinary pytest fixtures/parametrization do not apply directly to `TestCase` methods: <https://docs.pytest.org/en/stable/how-to/unittest.html>.
- Testmon uses previously observed execution dependencies and code blocks, but does not track arbitrary static assets or external services: <https://www.testmon.org/> and <https://www.testmon.org/blog/determining-affected-tests/>.
- A healthy test portfolio has many small tests and progressively fewer broad tests; high-level tests should prove boundaries that lower levels cannot, rather than duplicate all cases: <https://martinfowler.com/articles/practical-test-pyramid.html>.
- Test size should reflect resources and isolation as well as naming; small tests should remain hermetic and local: <https://testing.googleblog.com/2010/12/test-sizes.html>.
- GitHub path filters can reduce workflow triggers, but this plan keeps selection inside a required workflow so unknown changes fail closed instead of silently skipping validation: <https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow>.

## Goals

- Give each production component an obvious, nearby unit, contract, integration, architecture, and live-test owner.
- Make an isolated API or component change run its own tests plus relevant downstream contracts, without running unrelated vision or workflow tests during normal development.
- Preserve full offline validation at the integration boundary: merge queue or final pre-merge candidate, every push to `main`, and a scheduled run.
- Improve the test pyramid by moving behavior cases downward, retaining only boundary-specific integration coverage, and keeping live smoke tests scarce and explicitly authorized.
- Add an explainable, conservative selector whose uncertainty produces a full run rather than a false green result.
- Keep `unittest` authoritative during migration and make a later pytest/testmon decision from measured evidence.

## Non-Goals

- Rewriting 1,208 tests into pytest-style functions.
- Using coverage percentage as a confidence score for relevance selection.
- Allowing selected offline tests to authorize, select, or suppress live BlueStacks tests.
- Splitting `pnc_automation` into independently published distributions.
- Performing a big-bang directory move or retaining permanent compatibility imports after migration.
- Optimizing test count at the expense of distinct behavioral contracts.

## Current State

### Measured baseline

- **Observed:** 84 files match `tests/test_*.py`; `tests/test_support.py` is helper-only, so file count is not suite count.
- **Observed:** `py -m unittest discover -s tests` ran 1,208 tests in 59.591 seconds with 21 expected skips and no failures on `aabe85b`.
- **Observed:** eight `test_live*.py` modules are collected by ordinary discovery and skip through environment flags.
- **Observed:** `tests/test_capture_and_vision.py` is 6,328 physical lines with 153 directly declared test methods; `tests/test_flows_and_tasks.py` is 4,923 lines with 193 methods. Other broad modules include `test_world_map_search.py`, `test_mail_workflow.py`, and `test_automation_framework.py`.
- **Observed:** there is no tracked `.github` workflow and no pytest, testmon, or coverage configuration in `pyproject.toml`.
- **Observed:** `test_timings.csv` has 1,149 data rows and only `test_name`, `status`, and `duration_seconds`; it does not identify the commit, interpreter, dependency set, fixture profile, or whole-process duration.
- **Prior measurement:** on `68cec2d`, 1,165 tests passed with 18 skips; line coverage was 86.2%, branch coverage 68.8%, combined line-plus-branch coverage 81.7%, `app.automation` combined coverage 74.1%, and `app/entrypoints/api.py` combined coverage 71.0%. These numbers are useful directionally but are not the current baseline.

### Test-pyramid assessment

- Many tests are deterministic and fake-backed, which is a strong lower layer.
- File boundaries do not consistently reveal whether a test is unit, contract, integration, architecture, or live. Large files mix these purposes, making ownership and relevance inference unreliable.
- API facade behavior is substantial, but its tests are embedded mainly in `RuntimeCastleTargetingTests` and `ScheduledMailApiAndCliTests` rather than owned by a dedicated API contract suite.
- Integration coverage includes valuable reservation, cleanup, and composition behavior. Those checks should be moved, not replaced by forwarding-only mocks.
- Branch coverage lagged line coverage on the prior baseline, especially in automation and the API. The quality problem is missing decision and failure-path coverage in critical boundaries, not simply a repository-wide percentage.
- Live smoke tests are correctly opt-in, but placing them in the ordinary discovery namespace creates avoidable selection and initialization risk.

### Modularity and selection hazards

1. `tests/test_package_architecture.py` reads source files and parses their AST. Execution coverage and ordinary test imports cannot discover every file dependency of this test.
2. `pnc_automation/__init__.py::_LAZY_EXPORTS` introduces string-based dynamic imports that an `ast.Import`/`ast.ImportFrom` graph alone will miss.
3. YAML, JSON, PNG selector anchors, authored scripts, and optional local screenshots affect tests without Python import edges.
4. `tests/__init__.py` mutates `TMP`, `TEMP`, `tempfile.tempdir`, and `tempfile.TemporaryDirectory` process-wide. Runner initialization and import order are therefore part of the current contract.
5. `tests/test_support.py` imports core, authoring, PNC, vision, and runtime types. Its high fan-in makes a faithful reverse graph select broad portions of the suite.
6. `app/authoring/scripts/registry.py` owns both registry/preparation logic and concrete task construction.
7. `ConnectedClaimOnlyRunnerFactory.build()` imports the entrypoint composition root from inside `app/automation`.
8. castle identity and roster value types are owned by authored config but consumed by domain observations, persistence, and vision.
9. PNC vision imports observation policy values from `app/runtime`; the reusable value contracts and runtime implementation are not cleanly separated.
10. `core/infra/emulator/session.py` depends on the canonical BlueStacks lease registry. This is safety-critical and must be either explicitly accepted as infrastructure ownership or moved without weakening lease acquisition.

## Target Design

### Production ownership boundaries

The existing `core/` and `app/` split remains authoritative. This plan tightens four seams that directly improve test ownership and selection.

1. **Task registry:** `app/authoring/scripts/registry.py` retains `TaskRegistry` and script preparation against task contracts, but imports no concrete task classes. A new composition-owned builder under `app/entrypoints/task_registry.py` constructs the default tuple of concrete tasks and returns the canonical registry. There remains one `TaskId`, one parameter parser per task, and one registry contract.
2. **Daily composition:** `ConnectedClaimOnlyCastleRunner` remains under `app/automation/daily_maintenance`. Concrete construction of an `ApplicationRunner` moves to `app/entrypoints/daily_maintenance.py`; dependencies are passed inward. `ConnectedClaimOnlyRunnerFactory` in the automation layer is removed after callers migrate.
3. **Castle domain values:** `CastleIdentity`, `CastleRosterOrdering`, `PncAccountCastleRoster`, and `castle_identity_key` move to a canonical `app/pnc/domain/castles.py`. Authored config models may refer to these values, while domain, persistence, and vision stop importing authored configuration types. `AppConfig` and account/instance configuration remain in authoring.
4. **Observation policies:** immutable, PNC-neutral observation mode and artifact-policy contracts move to `core/vision/observation_policy.py`; `app/runtime` owns orchestration and artifact emission. If implementation inspection finds a PNC-specific policy value, it moves to `app/pnc/domain` instead of a generic `common` package.

Lease ownership is decided in its own slice. The default plan is to move only the reusable lease registry and lease value types into `core/infra/emulator/lease.py`, leave host monitoring/restart policy in `bluestacks_management`, and preserve session acquisition-before-ADB and close-on-failure behavior. If that separation creates a dependency back from the lease implementation into host policy, keep the current import and document it as an explicit allowed edge rather than duplicating the lease mechanism.

Architecture tests will enforce the resulting rules:

- `core` must not import `app`.
- `app/pnc` must not import `app/automation` or `app/runtime` implementations.
- authored script parsing/validation must not import concrete automation tasks.
- automation services must not import entrypoint composition roots.
- supported lazy exports must be declared and tested explicitly.
- the lease path must have exactly one process-scoped implementation.

### Test package taxonomy

Test purpose is the first directory level and canonical production owner is the second. Directory placement is the source of truth for normal group membership.

```text
tests/
  unit/
    core/
      infra/
      vision/
    app/
      authoring/
      pnc/
        domain/
        navigation/
        persistence/
        vision/
      automation/
        engine/
        tasks/
        daily_maintenance/
      runtime/
    bluestacks_management/
    tools/
  contract/
    entrypoints/
      test_automation_api.py
      test_cli.py
    public_exports/
  integration/
    entrypoints/
      test_automation_api_runner.py
    script_runner/
    persistence/
    vision/
    workflows/
    emulator/
  architecture/
  live/
  support/
    core/
    pnc/
    automation/
    runtime/
    entrypoints/
  data/
```

Rules for the split:

- A unit test may use in-memory fakes but does not build the application composition root, invoke ADB, initialize real OCR, or depend on local-only files.
- A contract test verifies a public facade, protocol, serialization format, or safety boundary using controlled dependencies.
- An integration test crosses at least one real internal boundary, such as API-to-runner, parser-to-registry, persistence-to-filesystem, or vision-to-real OCR. It names that boundary in the module name.
- An architecture test inspects source/package structure and is mandatory for relevant source changes.
- A live test is the only tier allowed to construct a real configured runtime or touch BlueStacks/ADB. It remains opt-in and separately authorized.
- “slow,” “real OCR,” and “local fixture” are execution attributes recorded in metadata, not ownership tiers.
- Newly created or split test modules should normally stay below 500 physical lines and 25 test methods. Exceptions require one cohesive responsibility and a short module-level explanation.

### Initial split map

- Move API facade methods from `test_runtime_castle_targeting.py` and `test_scheduled_mail.py` into `contract/entrypoints/test_automation_api.py`. Move the real-runner, reservation, lease-cleanup, and configuration-backed cases into `integration/entrypoints/test_automation_api_runner.py`.
- Split `test_capture_and_vision.py` into capture/storage units, generic template/OCR units, PNC selector/classifier units, real-OCR integration tests, and optional local-screenshot integration tests.
- Split `test_flows_and_tasks.py` by production task or navigation service; keep only cross-task workflow cases in `integration/workflows`.
- Split `test_automation_framework.py` by runner, action executor, observed executor, task context, and registry. Composition-root cases move to integration.
- Split `test_mail_workflow.py` into mail domain, vision extraction, task behavior, persistence, and end-to-end fake-transport integration.
- Split `test_world_map_search.py` by coordinate domain, planning, projection, segment execution, proof/artifact behavior, and production sweep integration.
- Move every current `test_live*.py` module under `tests/live/` without changing its explicit opt-in guard.
- Split `test_support.py` into owner-specific non-test modules. Migrate all imports in the same slice and delete the old high-fan-in module; do not leave a permanent re-export shim.
- Move the AST package checks to `tests/architecture/test_package_dependencies.py` and add focused tests for the selector’s own source-as-data behavior.

Each move records an old-to-new test-ID ledger during the migration. The ledger is an implementation artifact used to prove parity; it is removed after commands, documentation, and selection state use only new IDs.

### Canonical test runner

Create one repository runner at `tools/run_tests.py` with four public modes:

- `full`: all portable offline unit, contract, integration, and architecture tests; forcibly excludes live modules before importing them.
- `group <tier-or-component>`: explicit directory-derived groups such as `unit.app.pnc.vision`, `contract.entrypoints`, or `api`.
- `affected --base <revision>`: computes the conservative relevance plan and runs it.
- `measure`: runs the full portable suite with timing and line-plus-branch coverage outputs.

The runner uses `unittest` discovery and canonical `TestCase.id()` identifiers. It prints and writes a `SelectionPlan` containing changed paths, selected test IDs/groups, a reason for every selection, fallback reasons, baseline revision, and policy version. An unexplained zero-test result is an error.

### Relevance-selection algorithm

1. Resolve an explicit Git base or the merge base with the configured upstream. Read `git diff --name-status -z --find-renames` so spaces, renames, and deletions are unambiguous.
2. Build Python module/import graphs from both base and candidate revisions. Union their edges so deleted or removed imports still select former consumers.
3. Resolve absolute and relative imports, package `__init__.py` execution, re-exports, and the known `_LAZY_EXPORTS` table. Unknown dynamic import mechanisms trigger full fallback until explicitly modeled.
4. Start with changed/new tests, owning component unit tests, and transitive reverse consumers.
5. Add public contract tests when a public module, signature, default, export, serialized value, or error contract changes.
6. Add mandatory architecture tests for Python/package changes because those tests consume source as data.
7. Apply `tests/selection_rules.yaml` only for dependencies not represented by imports or directory ownership: YAML/JSON/PNG resources, authored scripts, local-fixture profiles, generated catalogs, public exports, and full-suite trigger paths. The schema is typed, validated, ordered by specificity, and rejects overlapping contradictory rules.
8. Union empirically observed per-test coverage dependencies after their cache provenance is validated. Coverage evidence may add tests; it never removes a test selected by ownership, contracts, architecture rules, or the static graph.
9. Fall back to `full` for unknown production/resource paths, `pyproject.toml` or dependency changes, package/build metadata, selection rules, runner/test infrastructure, shared contracts/models, corrupt or incompatible state, and ambiguous rename/delete handling.
10. Emit a stable machine-readable plan before execution. CI records both the plan and the result.

### Coverage-context state

Coverage-assisted selection is a second-stage enhancement, not a prerequisite for the static selector.

- The runner switches Coverage.py context from a custom `unittest.TestResult.startTest()` hook using the canonical `TestCase.id()`, so per-test `setUp` executes inside that context.
- Module/class setup, imports, and contextless execution are attributed conservatively to the owning module/group rather than guessed as one test’s dependency.
- Generated state is untracked under `.test-impact/` and contains the Coverage.py data plus metadata: schema/policy version, source commit, complete discovered inventory hash, Python/OS, resolved dependency versions, fixture profile, and coverage version.
- Cache loss, corruption, inventory mismatch, dependency mismatch, or an interrupted seed run causes a full portable run and rebuild.
- CI jobs use private cache copies. PR jobs cannot publish trusted `main` state, and concurrent jobs never mutate one shared database.

### Timing and coverage artifacts

`tools/run_tests.py measure` regenerates `test_timings.csv` through one code path. The CSV contains enough provenance to compare runs safely: schema version, run ID, commit SHA, UTC timestamp, Python version, resolved test-tool versions, fixture profile, total run seconds, canonical test ID, tier, component, status/skip reason, and test duration.

Coverage reporting records statements and branches separately. The first current measurement establishes ratchets; it does not inherit the `68cec2d` percentages as hard thresholds. Critical contracts—API account resolution/reservations, leases, authorizers, config validation, and mutation gates—also maintain explicit decision tables so a percentage cannot hide a missing safety case.

### Execution policy

| Change or event | Required validation |
| --- | --- |
| Documentation-only | Relevant document/skill validator or `git diff --check`; runner records an explained no-test decision. |
| Isolated private implementation in one component | Owning unit group, reverse-dependent contracts, relevant integration boundary, architecture checks. |
| API facade body with unchanged public contract | API contract group, affected facade consumers, public-export checks, API-to-runner integration. |
| Public API signature/default/error/reservation change | API policy above plus all consumers and full portable suite. |
| YAML/JSON/PNG/selector/authored workflow | Explicit resource owners and architecture checks; full portable suite until every mapping has adversarial proof. |
| Shared domain model, registry, composition root, dependencies, packaging, or test infrastructure | Full portable suite. |
| Every PR update | `affected` fast feedback plus mandatory contract/architecture groups; concurrency cancels superseded runs. Unknown/high-risk changes automatically become full. |
| Merge queue / final merge candidate | Full portable suite on the exact candidate SHA. If merge queue is unavailable, a required manually triggered `full` check must match the current PR head SHA. |
| Push to `main` | Full portable suite and timing summary. |
| Nightly | Full portable suite, line-plus-branch coverage, timing trend, and selector audit comparing affected selection with the full result. |
| Live smoke | Separate explicit opt-in command under the live-testing safety workflow; never selected, skipped, or authorized by `.test-impact` state. |

Use one always-triggered PR workflow and make the runner decide the scope. Do not rely on workflow-level path exclusions for a required check: a new or unknown path must be visible to the selector and fail closed.

## Implementation Phases

### Phase 0 — Reproducible current baseline

Files/components: `tools/run_tests.py` measurement skeleton, `test_timings.csv`, `pyproject.toml` test-development extra, `.gitignore`, test documentation.

Work:

- Add a pinned/compatible test-development environment containing Coverage.py while leaving runtime dependencies unchanged.
- Implement full offline discovery, canonical ID capture, skip reasons, whole-process/per-test timing, and provenance-rich CSV output.
- Run ordinary and coverage-instrumented baselines separately on the current revision.
- Record count and ID inventory; investigate why the current 59.591-second run differs from the older 38.972-second timing aggregate before setting performance budgets.

Acceptance:

- The uninstrumented current baseline reproduces 1,208 tests and 21 skips or every discrepancy is explained.
- No live module is imported by the portable runner when inherited live flags are present.
- Timing and coverage artifacts identify the exact revision and environment.
- `py -m unittest discover -s tests` remains functional during migration.

### Phase 1 — Harness isolation and ownership foundations

Files/components: `tests/support/**`, `tests/__init__.py`, all imports of `tests.test_support`, test inventory/parity utility.

Work:

- Split shared fakes/builders by canonical owner and migrate consumers in bounded batches.
- Replace the process-global `TemporaryDirectory` monkeypatch with explicit workspace-backed helpers/base classes. Keep the old bootstrap only while callers remain, then remove it.
- Add inventory comparison that detects lost, duplicated, or unexpectedly renamed tests across each move.

Acceptance:

- `tests/test_support.py` is deleted with no re-export shim.
- Ordinary Python `tempfile` behavior is unchanged outside tests explicitly requesting the workspace helper.
- Every migration batch has identical logical cases and explained ID changes.
- Full portable suite passes after each support-owner batch.

### Phase 2 — Split tests by tier and component

Files/components: the target `tests/unit`, `contract`, `integration`, `architecture`, and `live` packages; current broad test modules; test command documentation.

Work, in order:

1. Create API contract/integration ownership and move existing cases without copying them.
2. Move live modules out of the canonical portable runner's discovery roots and prove explicit live discovery still works.
3. Split capture/vision and flow/task mega-modules.
4. Split automation framework, mail workflow, and world-map search modules.
5. Move the remaining focused files by tier/owner.

Acceptance:

- Portable and live inventories are disjoint and explicit.
- No moved logical test is lost or collected twice.
- New/split modules meet the normal size bounds or document a cohesive exception.
- Higher-level tests state the boundary they uniquely prove; duplicated case matrices are removed only after equivalent lower-level coverage passes.
- Full portable suite passes after every batch.

### Phase 3 — Tighten production boundaries

Files/components: `app/authoring/scripts/registry.py`, new entrypoint composition modules, daily-maintenance connected runner, castle domain/config/persistence/vision modules, observation policy modules, emulator session/lease modules, architecture tests.

Work:

- Separate concrete task construction from registry/script preparation.
- Move daily concrete factory wiring to the composition root and inject dependencies inward.
- Move shared castle values into the PNC domain and migrate loaders/callers atomically.
- Move observation policy contracts to their verified lower-level owner.
- Decide and implement or document the single lease dependency edge without changing its safety semantics.

Acceptance:

- Each unwanted edge is absent and a focused architecture test enforces its replacement.
- There is one canonical task registry, castle identity model, observation policy contract, and lease implementation.
- No temporary import wrapper remains after each slice.
- Focused tests, full portable tests, and the applicable live-validation matrix pass before unattended promotion.

### Phase 4 — Named groups and static affected selector

Files/components: `tools/test_selection/{models,git_changes,python_graph,ownership,planner,reporting}.py`, `tools/run_tests.py`, `tests/selection_rules.yaml`, selector unit/integration tests.

Work:

- Implement directory-derived named groups first.
- Add base/head graph union, rename/delete support, explicit non-Python ownership, mandatory checks, and full fallbacks.
- Add `--explain` text and JSON plans with deterministic ordering.
- Test the selector against synthetic repositories and real PNC change fixtures, including unknown files and source-as-data architecture tests.

Acceptance:

- Every selected test has at least one human-readable reason.
- Unknown or malformed inputs cannot produce a successful zero-test run.
- Representative API-only changes exclude unrelated heavy vision/workflow groups while retaining API contracts and integrations.
- Shared/test-infrastructure changes select full.
- Adversarial rename, delete, lazy export, YAML, PNG, and architecture-rule changes select the expected mandatory coverage.

### Phase 5 — Additive coverage-context learning

Files/components: custom unittest result/runner, `.test-impact` metadata/cache handling, coverage mapping tests.

Work:

- Seed contexts from the complete eligible portable suite.
- Union observed test dependencies with static selection.
- Implement provenance validation, atomic state replacement, private concurrent copies, and safe full fallback.
- Audit selection against an independent full run over at least 30 historical or realistic changes plus adversarial cases.

Acceptance:

- No known failure is missed in the audit corpus.
- Missing/corrupt/incompatible/interrupted state reliably runs full.
- Coverage evidence never removes a statically selected test.
- Median developer iteration improves at least 2× over the simple ownership-group workflow and saves a meaningful absolute budget; begin evaluation at 15 seconds per qualifying iteration.

If the savings gate fails, retain Phase 4 and remove the coverage-cache path rather than growing a custom selection database without demonstrated value.

### Phase 6 — CI rollout and selector auditing

Files/components: `.github/workflows/tests.yml`, test documentation, branch protection/merge queue configuration outside the repository.

Work:

- Add PR affected checks with mandatory contract/architecture groups and cancellation of superseded runs.
- Add exact-candidate full validation through merge queue or a SHA-bound pre-merge full check.
- Add push-to-main and nightly full/coverage/timing jobs.
- In nightly audit mode, compare the affected plan with failures from an independent full run and retain artifacts.

Acceptance:

- A selector crash, unknown mapping, or missing cache cannot turn a required check green without tests.
- The full job explicitly bypasses selection.
- Required checks apply to the current candidate SHA.
- Live flags are neutralized in all offline jobs and secrets/config are never required.

### Phase 7 — Bounded pytest/testmon experiment

Files/components: isolated optional test dependencies and experiment documentation only; existing test bodies remain unchanged.

Work:

- Pin a compatible pytest/Coverage.py/pytest-testmon tuple in an isolated environment.
- Compare `unittest full`, `unittest group`, `pytest full --no-testmon`, and `pytest --testmon` plus mandatory groups.
- Seed testmon from the complete portable inventory and preserve parent-state cache separately for each candidate change.
- Exercise API body/signature changes, class/session setup, shared helpers, lazy exports, source-scanning architecture rules, static resources, module/test rename/delete, and missing/corrupt/incompatible cache cases.

Adoption gate:

- Same logical inventory, outcomes, and explained skips under unittest and pytest.
- No missed known failures in the experiment and at least 30 representative changes.
- Safe full fallback for cache and environment problems.
- At least 2× median improvement with meaningful absolute savings over Phase 4, not merely over full discovery.
- One documented owner, one bypass command, and no weakening of full or live gates.

If the gate passes, adopt testmon first as an optional local accelerator while `unittest full` remains authoritative. Converting tests to pytest fixtures/parametrization is a separate future decision. If the gate fails, remove the experiment dependencies and keep the repository-native group/static selector.

## Slice-by-Slice Live Validation Matrix

Test moves, support isolation, selector implementation, coverage learning, and CI changes do not change production runtime behavior; they require offline validation only. The following Phase 3 slices touch runtime composition or safety-sensitive imports.

The implementation agent must resolve the configured `testing` BlueStacks display and currently active eligible castle at execution time. No castle switching or resource-changing action is authorized by this plan. Every applicable matrix cell must be recorded as `passed`, `applicability_skip`, or `blocked` with artifacts and the exact remaining command.

| Runtime slice | Offline gate | Smallest live gate | Mutation boundary and expected state | Promotion rule |
| --- | --- | --- | --- | --- |
| Default task-registry construction moves to entrypoints | Registry, script-loader, application composition, API contract tests; then full portable suite | `PNC_RUN_LIVE_SMOKE=1 py -m unittest tests.live.test_live_account_navigation_smoke` | Read-only construction and account/session preparation; remain on or recover to Home, no task mutation | Registry import/lookup parity plus one read-only canonical-runtime pass |
| Daily connected factory moves outward | Daily coordinator/factory/lease/authorization tests; then full portable suite | `PNC_RUN_LIVE_DAILY_TASK_SMOKE=1 py -m unittest tests.live.test_live_daily_task_smoke` only after exact target/action/budget authorization | Stop before any claim or other mutation unless separately authorized; expected precondition and journal state must be captured | Remains blocked for unattended promotion until the authorized daily smoke records a valid postcondition |
| Castle domain values move out of authoring | Config loader, roster store, observation, API targeting, serialization tests; then full portable suite | Same read-only account-navigation smoke | Load configured identity and observe current castle without switching; end in Home | Config/serialization parity and read-only identity proof |
| Observation policy contracts move lower | Observation policy, capture/vision, classifier, navigation tests; then full portable suite and selector validator | `PNC_RUN_LIVE_SMOKE=1 py -m unittest tests.live.test_live_spatial_surface_smoke` | Read-only capture/classification; no navigation beyond the smoke’s existing bounded recovery | Pre/post observation artifacts show unchanged policy behavior |
| Lease implementation ownership changes | Instance lease, emulator session, resolver, API reservation, failure cleanup tests; then full portable suite | Read-only account-navigation smoke | Acquire canonical process lease before ADB, reject conflicts, release on exit/failure; no castle switch | Lease tests plus live acquisition/release evidence; never bypass lease for graph cleanliness |

For each live gate: verify target and role, acquire the canonical lease, use bounded waits, preserve screenshots/OCR/log summaries, stop on unexpected state, and convert any live-discovered defect to a deterministic offline regression before retrying. A process exit code without pre/post observations is not a pass.

## Data, Config, and Migration Notes

- `tests/selection_rules.yaml` is authored and tracked; generated `.test-impact/` state is ignored.
- Selection rules contain only non-import dependencies, mandatory checks, and full-fallback paths. They do not duplicate normal package ownership derived from test directories.
- Rule loading is typed and fail-fast. Unknown keys, missing targets, overlapping contradictory patterns, and references to nonexistent test groups fail validation.
- Test moves update repository docs and commands in the same slice. The temporary ID ledger prevents silent loss but is removed after migration.
- Existing local-only fixture configuration remains untouched. The selector records only a non-secret fixture profile identifier.
- Timing history is comparable only when schema, environment, and fixture profile match. Otherwise the report labels the runs incomparable.
- Coverage and test-impact databases are disposable accelerators, never release evidence.

## Validation Plan

For every implementation slice:

1. Run the selector’s own focused unit tests or the smallest owning test group.
2. Run contract/integration tests for the boundary being changed.
3. Run `py -m unittest discover -s tests` while that command remains the migration authority.
4. After the new runner is authoritative, run `py tools/run_tests.py full` and periodically compare it with raw unittest discovery until parity is retired by an explicit decision.
5. Run `git diff --check` and architecture checks.
6. For selector/navigation/runtime changes, run the existing repository validator required by `AGENTS.md`.
7. Run the applicable live matrix only through the live-testing workflow and only within its authorization boundary.

Coverage quality gates after the current baseline is regenerated:

- Repository line and branch coverage do not regress unintentionally; ratchets use covered/possible counts, not averaged percentages.
- Changed critical contracts have complete decision-table coverage and targeted failure-path tests.
- New high-level tests identify the boundary they uniquely prove.
- A higher-level failure without a lower-level failure produces a lower-level regression test when feasible.

Selector quality gates:

- Selection recall is evaluated by seeded faults or known failing candidate revisions, then checked with an independent full run.
- Performance includes Git diff, graph construction, discovery, instrumentation, cache validation, mandatory groups, and execution.
- Reports track selected-test ratio, elapsed time, fallback frequency/reason, cache rebuilds, and any missed failure.

## Risks and Mitigations

- **False negatives from Python dynamism:** model known lazy exports, union base/head graphs, make coverage additive, and fall back on unknown dynamic imports.
- **False negatives from data files:** keep explicit typed resource ownership and full fallback until adversarial tests prove each rule.
- **Selection becomes a second build system:** begin with directory groups and a static graph; keep coverage learning optional and remove it if value is not demonstrated.
- **Test IDs break during moves:** compare logical inventory per batch and invalidate all selection state after accepted moves.
- **Global test initialization hides dependencies:** remove the process-wide tempfile replacement and attribute shared setup conservatively.
- **Broad helper fan-in keeps selection broad:** split helpers by owner before tuning graph precision.
- **Coverage overhead exceeds savings:** measure end-to-end time and require savings over simple groups.
- **CI cache poisoning or races:** use provenance, atomic replacement, private copies, and only promote state produced from trusted full `main` runs.
- **Required checks are skipped by path filters:** keep the workflow present for all PR changes and let the fail-closed runner choose scope.
- **Runtime refactor weakens safety:** preserve lease, role, reservation, authorization, and journal contracts; require the slice-specific offline/live promotion gate.
- **Framework experiment becomes an accidental migration:** keep test bodies and `unittest full` intact; pytest-only fixtures are outside the experiment.

## Open Questions

- Is GitHub merge queue available for this repository? If not, choose and document the SHA-bound final-candidate full-check mechanism before CI rollout.
- What is the current line/branch coverage profile at `aabe85b`? Phase 0 must regenerate it before coverage ratchets are set.
- Which optional local screenshot fixture profiles are routinely available in CI or developer worktrees? Until known, they remain explicit optional integration groups and never become required portable evidence.
- How frequently are changes truly isolated to one component, and what absolute feedback-time saving matters to the user? Phase 4 telemetry sets the final adoption budget.
- Does an external CI service or user-local hook exist outside the tracked repository? The current checkout proves only that no tracked GitHub workflow exists.

## Execution Checklist

1. Create a feature branch from the latest fetched target before implementation; preserve unrelated work.
2. Implement Phase 0 and commit a current, provenance-rich baseline.
3. Split support/temp behavior and prove inventory parity.
4. Create API contract and integration ownership first.
5. Move live tests out of the canonical portable runner's discovery roots.
6. Split the large vision, flow/task, automation, mail, and world-map modules in bounded batches.
7. Tighten one production dependency boundary at a time with its architecture and live-promotion gate.
8. Add named groups, then the base/head static selector and explicit resource rules.
9. Roll out PR affected checks and exact-candidate/main/nightly full checks.
10. Add coverage-context learning only after static selection metrics exist.
11. Run the bounded pytest/testmon experiment without converting tests.
12. Record the adoption decision, rollback command, performance evidence, fallback rate, and known selection limits.
