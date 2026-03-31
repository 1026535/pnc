# Review: runtime castle targeting implementation

Commit reviewed: `b7e00c90e94861a2c4e9fdf101fffad0c75eb43b` (`Complete runtime castle targeting plan`)

Scope reviewed:

- config/model/schema changes for runtime castle targeting,
- runner/task/session-preparation wiring,
- select-castle and refresh-castle-roster behavior,
- new Python API and CLI entry points,
- updated tests and example scripts.

## Findings

### 1. High: `refresh_castle_roster` can mark a stale or wrongly ordered cache as `full_scan`

Evidence:

- [_sync_castle_roster()](/c:/Users/lebel/pnc/pnc_automation/vision/observation_builder.py#L305)
- [_merge_partial_window()](/c:/Users/lebel/pnc/pnc_automation/config/castle_roster_store.py#L148)
- [_finalize_full_scan()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/refresh_castle_roster_task.py#L175)

Why this is a problem:

- Every Manage Char observation is still passively merged through `CastleRosterStore.sync(..., ordering=UNKNOWN)`.
- Partial sync preserves any pre-existing order and any pre-existing unseen castles.
- `refresh_castle_roster` then finalizes by calling `replace_full_scan(..., context.castle_roster.castles)`, which reads back that already-merged cache instead of a scan-local ordered result.
- If the cache was already stale or misordered before the refresh started, the task can persist that stale order, keep obsolete castles, and still mark the result as trusted `full_scan`.
- That directly breaks the off-screen castle-targeting contract, because later scroll direction decisions trust `full_scan`.

I reproduced this locally with a small harness: starting from an unknown cache ordered as `Main, Stale, Alpha, Bravo`, then scanning windows `Alpha/Bravo` and `Bravo/Main`, the task-equivalent finalize path preserved `Main, Stale, Alpha, Bravo` and upgraded it to `full_scan`.

Clean fix:

1. Make `refresh_castle_roster` own its ordered scan state explicitly in `runtime_state` instead of finalizing from the passive store snapshot.
2. Record the ordered full-scan sequence from the observed windows themselves, deduplicated by stable castle identity, and pass that scan-local tuple to `replace_full_scan(...)`.
3. Treat any pre-existing cache only as optional enrichment for missing `castle_level`, never as the source of scan ordering or membership during a refresh.
4. Add regression tests for:
   - refresh starting from a stale cache with an obsolete castle,
   - refresh starting from a wrongly ordered partial cache,
   - refresh proving that the persisted `full_scan` result exactly matches the windows seen in the scan.

### 2. High: explicit castle selection still accepts ambiguous name-only current-castle evidence

Evidence:

- [_lord_info_name_to_current_castle()](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L1536)
- [_resolve_current_castle()](/c:/Users/lebel/pnc/pnc_automation/vision/observation_builder.py#L330)
- [castle_identities_match()](/c:/Users/lebel/pnc/pnc_automation/pnc/observation.py#L215)
- [SelectCastleTask.plan()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/select_castle_task.py#L42)
- [SelectCastleTask.verify()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/select_castle_task.py#L66)

Why this is a problem:

- Lord Info only produces `CastleIdentity(kingdom="", castle_name=...)`.
- `castle_identities_match()` treats an empty kingdom as a wildcard.
- That wildcard evidence is then carried back onto home-adjacent screens and is also accepted as a terminal success condition directly on Lord Info.
- If two castles share the same name in different kingdoms, an explicit target can be reported as already selected even when the kingdom is wrong.
- The plan explicitly says explicit targeting must fail fast instead of guessing from ambiguous evidence; this path still guesses.

I reproduced this locally with:

- `castle_identities_match(CastleIdentity(kingdom="", castle_name="Main"), CastleIdentity(kingdom="K230", castle_name="Main")) == True`
- `castle_identities_match(CastleIdentity(kingdom="", castle_name="Main"), CastleIdentity(kingdom="K999", castle_name="Main")) == True`

That is enough for `SelectCastleTask` to short-circuit on the wrong castle.

Clean fix:

1. Split "current castle observed" into evidence strength levels instead of treating every `CastleIdentity` as equally trustworthy.
2. Do not let name-only Lord Info evidence satisfy an explicit runtime target by itself.
3. For explicit target verification, require either:
   - a Manage Char selected row whose kingdom/name match the target, or
   - name-only evidence that is proven unambiguous against the cached roster for the verified account.
4. If the roster makes the name ambiguous, fail fast with a clear error instead of silently accepting the match.
5. Add regression tests for duplicate castle names across kingdoms and for Lord Info name-only evidence that must not terminate selection successfully.

### 3. Medium: the new public direct-call API reintroduces a second castle-targeting path

Evidence:

- [AutomationApi.run_task()](/c:/Users/lebel/pnc/pnc_automation/api.py#L127)
- [ApplicationRunner.run_task()](/c:/Users/lebel/pnc/pnc_automation/app.py#L52)
- [ScriptRunner.run_task()](/c:/Users/lebel/pnc/pnc_automation/automation/script_runner.py#L75)

Why this is a problem:

- The new convenience wrappers (`building_upgrade()`, `research()`, `gathering()`, and so on) correctly use current-castle semantics.
- But the public generic `run_task(..., castle=...)` path still lets callers inject an explicit castle target directly into one generated step.
- That bypasses the stated contract that direct function calls should operate on the current live session state and should not silently switch castles.
- It also leaves the codebase with two public castle-target entry points:
  - `use_account(..., castle=...)`
  - `run_task(..., castle=...)`

This is not a runner bug, but it is a contract inconsistency and unnecessary surface area.

Clean fix:

1. Decide which public contract is canonical.
2. If the intended contract is "direct calls use current-castle semantics", remove the public `castle` parameter from `run_task()` and keep explicit alignment only in authored steps and `use_account(...)`.
3. If the low-level generated-step API is intentionally public, document that explicitly and update the plan text and tests so the contract is no longer contradictory.
4. In either case, keep only one clearly documented public path for "prepare and optionally align castle" semantics.

### 4. Medium: account-scoped artifact naming can silently collide across distinct account ids

Evidence:

- [format_account_artifact_directory()](/c:/Users/lebel/pnc/pnc_automation/artifact_naming.py#L15)
- [AccountConfig.artifact_directory_name](/c:/Users/lebel/pnc/pnc_automation/config/models.py#L84)
- [validate_app_config()](/c:/Users/lebel/pnc/pnc_automation/config/validation.py#L12)

Why this is a problem:

- Artifact directories are now derived from a normalized snake-case form of `account.id`.
- Config validation only enforces raw `account.id` uniqueness, not normalized artifact-directory uniqueness.
- Distinct ids such as `ColdDuke`, `cold_duke`, and `cold duke` all normalize to `cold_duke`.
- When that happens, different accounts write screenshots and diagnostics into the same artifact directory.

I reproduced this locally:

- `ColdDuke -> cold_duke`
- `cold_duke -> cold_duke`
- `cold duke -> cold_duke`

Clean fix:

1. Add startup validation that derived `artifact_directory_name` values are unique across accounts.
2. If human-readable normalization must stay, fail fast on collisions with both conflicting account ids in the error.
3. If rejecting collisions is too restrictive, include a stable disambiguator in the directory name, for example a short hash suffix derived from the raw account id.
4. Add config-loader tests covering normalized-name collisions.

## Simplification notes

- [PreparedScriptStep.castle_target_policy](/c:/Users/lebel/pnc/pnc_automation/scripts/models.py#L33) is currently stored but never consumed by the runner. Either remove it as dead data or use it in [_align_step_castle_target()](/c:/Users/lebel/pnc/pnc_automation/automation/runner.py#L148) so the "synthetic select only for optional tasks" rule is encoded once instead of implied.
- [main()](/c:/Users/lebel/pnc/pnc_automation/cli.py#L16) and [_run_legacy_command()](/c:/Users/lebel/pnc/pnc_automation/cli.py#L47) duplicate CLI wiring and JSON-print behavior. Folding those through one shared execution path would make future command additions safer.

## Validation performed

- Ran `py -3 -m unittest tests.test_runtime_castle_targeting tests.test_flows_and_tasks tests.test_config_loader tests.test_runner_end_to_end tests.test_castle_roster_store`
- Result: `Ran 70 tests` / `OK`
- Also reproduced:
  - stale full-scan contamination with a small `CastleRosterStore` harness,
  - ambiguous name-only castle matching with a direct `castle_identities_match()` harness,
  - artifact-directory collisions with a direct `format_account_artifact_directory()` harness.

