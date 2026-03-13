# Puzzles & Conquest Runtime Castle Targeting Sub-Plan

## 1. Purpose

This document defines the canonical refactor that removes castle selection from authored account configuration and makes castle choice a runtime concern.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which owns bootstrap, login, and castle-switch behavior,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable navigation flows,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns bounded feature-task slices.

This file owns one architectural correction:

- `selected_castle` must stop being part of `accounts.yaml`,
- the list of castles must live in one canonical roster store keyed by `pnc_account_id`,
- task execution must be able to target an explicit castle at runtime,
- tasks with no target must use the currently selected castle without switching.

## 2. Current context

The current runtime already has the right raw building blocks, but the ownership boundary is wrong.

Today the platform has:

- `config/accounts.yaml` for instances, credentials, and a per-account `selected_castle`,
- `config/castles.yaml` for a per-`pnc_account_id` discovered roster cache,
- `AccountConfig.selected_castle`, which drives task behavior and artifact directory naming,
- `PncAccountCastleRosterConfig.castles`, which already stores the same castle identity concept in a separate place,
- `SelectCastleTask`, which can switch castles,
- `LoginTask`, which already uses the roster cache to verify an already-in-game account,
- `ObservationService`, which already syncs visible castle-roster windows back into `castles.yaml`.

The result is that the runtime currently stores castle information in two different ownership domains:

- `accounts.yaml` stores one configured selected castle,
- `castles.yaml` stores the account's discovered castle list.

That split is the source of the current usability and design problem.

## 3. Problem statement

The current model incorrectly treats "which castle should this run use" as stable account configuration.

That is the wrong ownership boundary because:

- `instance_id` and `pnc_account_id` identify the runtime session and login identity,
- castle choice is not part of account identity,
- the same P&C login can legitimately operate on different castles on different runs,
- `castles.yaml` already expresses the per-account castle universe,
- forcing castle choice into `accounts.yaml` makes normal operation require config edits instead of runtime inputs.

This creates concrete problems:

- changing the active castle requires editing authored config,
- one account id cannot cleanly run different scripts against different castles without config churn,
- `selected_castle` duplicates information already represented by the roster cache,
- artifact directory naming is incorrectly coupled to one configured castle,
- validation and runtime behavior are forced to pretend an account target is "account plus one castle" instead of just "one P&C login on one emulator instance".

## 4. Goals

The refactor must achieve all of the following:

1. Keep one canonical implementation per concept.
2. Remove `selected_castle` from `accounts.yaml`.
3. Make castle targeting a runtime step concern, not an account-definition concern.
4. Keep one canonical castle roster per `pnc_account_id` in `config/castles.yaml`.
5. Use the current castle when a task does not request a target.
6. Switch to a requested target castle before the task when a target is explicitly provided.
7. Reuse the existing castle-selection flow and task logic instead of duplicating switching behavior across tasks.
8. Fail fast when a requested target cannot be resolved safely from the known roster state.
9. Keep the solution lean, DRY, extensible, and aligned with the existing task/runner architecture.

## 5. Non-goals

This change should not:

- keep parallel support for the old `selected_castle` account schema,
- hide expensive full-roster discovery inside every login,
- let individual tasks implement their own castle-switch logic,
- guess castle identities from partial or ambiguous data,
- create a second roster file or a second castle-definition format,
- introduce a second runtime parameter path that duplicates the script-step contract.

## 6. Core architectural decision

Castle choice must become an optional per-step runtime contract.

The canonical rule set should be:

1. `AccountConfig` represents only emulator binding and P&C login identity.
2. `config/castles.yaml` is the single canonical castle-roster store for each `pnc_account_id`.
3. Each script step may declare an optional `castle` field.
4. If `castle` is absent, the step uses the currently selected in-game castle and must not switch.
5. If `castle` is present, the runner must ensure that castle is selected before executing the task.
6. The runner must achieve that by reusing the canonical `SelectCastleTask` implementation rather than duplicating switching behavior.

This preserves one canonical implementation:

- one roster model,
- one castle identity model,
- one task-level switch implementation,
- one runner-level pre-step targeting policy.

An optional Python API may be added for ergonomics, but it must compile down into this same runtime contract instead of defining different semantics.

## 7. Canonical domain model

### 7.1 Rename the castle identity type

`SelectedCastleConfig` is no longer the correct name once a castle can be:

- the current active castle,
- a roster member,
- a requested runtime target,
- a verified current castle from observation.

The canonical shared type should be renamed to `CastleIdentity`.

Recommended fields:

- `kingdom: str`
- `castle_name: str`
- `castle_level: int | None = None`

This type should be reused everywhere castle identity appears:

- roster entries,
- runtime step targets,
- current-castle observations,
- live smoke expectations,
- logs and result metadata.

No alias should be kept for `SelectedCastleConfig`. The old name should be removed in the same refactor.

### 7.2 AccountConfig responsibility

`AccountConfig` should represent only the stable runtime target:

- `id`
- `instance_id`
- `pnc_account_id`
- `credentials`

It must no longer own:

- selected castle,
- castle artifact naming,
- any castle-specific execution policy.

### 7.3 Castle roster responsibility

`PncAccountCastleRosterConfig` remains the canonical roster model for one P&C login.

It should continue to own:

- `pnc_account_id`
- `castles: tuple[CastleIdentity, ...]`
- `ordering`

It should remain keyed by `pnc_account_id`, not by `instance_id`, because the roster belongs to the P&C account itself.

### 7.4 Runtime castle target responsibility

The script model should gain one optional runtime field:

- `castle: CastleIdentity | None`

That field is the only canonical task-facing input for explicit castle targeting.

If later a CLI convenience flag is desired, it should compile down into this same script-step contract rather than create a second parallel castle-target pathway.

### 7.5 Task-level castle target support policy

Castle targeting support should be declared once per task through a canonical task metadata property.

Recommended enum:

- `DISALLOWED`
- `OPTIONAL`
- `REQUIRED`

Recommended ownership:

- `ensure_game_running`, `popup_recovery`, `login`: `DISALLOWED`
- `select_castle`: `REQUIRED`
- post-login feature tasks such as chat, building, research, gathering, campaign: `OPTIONAL`

This prevents task-local castle-target validation from being duplicated across implementations.

## 8. YAML contracts

### 8.1 `config/accounts.yaml`

The authored account configuration should stop storing castle choice.

Target shape:

```yaml
artifacts:
  root: artifacts

defaults:
  adb_path: C:\Program Files\BlueStacks_nxt\HD-Adb.exe
  screenshot_format: png
  stable_click_delay_ms: 300
  post_action_observe_delay_ms: 800

instances:
  - id: bs-main
    device_id: 127.0.0.1:5556
    app_package: com.global.tmslg

accounts:
  - id: serious_stuff
    instance_id: bs-main
    pnc_account_id: lewiboo66@gmail.com
    username: lewiboo66@gmail.com
    password: B00PunPlsg
```

### 8.2 `config/castles.yaml`

`config/castles.yaml` becomes the single canonical castle list per `pnc_account_id`.

Target shape:

```yaml
pnc_accounts:
  - pnc_account_id: lewiboo66@gmail.com
    ordering: full_scan
    castles:
      - kingdom: K230
        castle_name: Lv. 6 hellhound
        castle_level: 6
      - kingdom: K157
        castle_name: Tiny NPC
        castle_level: 4
```

This file should remain:

- runtime-loadable,
- runtime-writable,
- schema-validated,
- keyed only by `pnc_account_id`.

### 8.3 Script step schema

Every script step should support one optional `castle` mapping alongside `task` and `params`.

Target shape:

```yaml
name: daily_maintenance

steps:
  - task: ensure_game_running
  - task: login
  - task: building_upgrade
    castle:
      kingdom: K230
      castle_name: Lv. 6 hellhound
    params:
      priority: [castle, wall, academy]
  - task: research
    params:
      priority: [economy, development]
  - task: gathering
    castle:
      kingdom: K157
      castle_name: Tiny NPC
    params:
      preferred_resources: [food, wood]
```

Semantics:

- `building_upgrade` first switches to `K230 / Lv. 6 hellhound`, then executes,
- `research` does not switch and uses whatever castle is currently selected after the previous step,
- `gathering` first switches to `K157 / Tiny NPC`, then executes.

### 8.4 Explicit castle-selection step

The existing `select_castle` task should remain available, but it must now require an explicit `castle`.

Example:

```yaml
steps:
  - task: ensure_game_running
  - task: login
  - task: select_castle
    castle:
      kingdom: K230
      castle_name: Lv. 6 hellhound
  - task: building_upgrade
  - task: research
```

This pattern is useful when several following steps should inherit the same current castle without repeating the target on every step.

## 9. Runtime behavior

### 9.1 Central script preparation

Script loading must parse the optional step-level `castle` field centrally.

The parsing of one castle mapping must be shared between:

- `config/loader.py`
- `automation/scripts/loader.py`

The castle YAML parser must exist once. The code should not duplicate the same mapping-to-`CastleIdentity` logic in two different loaders.

### 9.2 Central castle-target validation

Task-specific castle-target support must be validated during script preparation.

Required rules:

- `DISALLOWED` tasks must reject steps that provide `castle`,
- `REQUIRED` tasks must reject steps that omit `castle`,
- `OPTIONAL` tasks may accept or omit `castle`.

This validation belongs in the task registry or shared script-preparation layer, not inside each task's `parse_params`.

### 9.3 Pre-step castle alignment

When a prepared step has an explicit `castle`, the runner must ensure that castle is selected before the actual step executes.

That precondition must reuse the canonical castle-switch implementation.

Recommended implementation:

1. The runner inspects the prepared step's `castle`.
2. If the task policy is `OPTIONAL` and `castle` is present, the runner executes one synthetic `select_castle` pre-step using the same typed target.
3. If the actual step is already `select_castle`, the runner executes it directly and does not wrap it again.
4. The actual task then runs with the same observation loop as today.

This keeps castle switching implemented in one place.

### 9.4 No-target semantics

If a step omits `castle`, the runner must not:

- open Manage Char,
- open Lord Info,
- try to discover the current castle,
- perform a silent switch,
- guess which castle the user probably intended.

The rule is simple:

- no explicit target means use the current castle exactly as the session is already positioned.

That is the least surprising behavior and the cleanest ownership boundary.

### 9.5 Current-castle evidence

The runtime may still observe and carry current-castle evidence exactly as it does today:

- Lord Info parsing,
- roster-entry selection state,
- observation carry-forward through home-adjacent screens.

That evidence remains useful for:

- switch verification,
- logs,
- smoke validation,
- diagnostics.

It must not be upgraded into an implicit target request.

### 9.6 Python API ergonomics

A Python API is a good usability layer, but it must remain a thin facade over the canonical runner behavior.

Recommended rule:

- the script/task runner contract remains canonical,
- the Python API lowers into that contract,
- there must not be separate castle-target semantics for Python callers.

Recommended public shape:

```python
with automation.use_account("serious_stuff", castle=CastleIdentity(kingdom="K230", castle_name="Lv. 6 hellhound")):
    automation.building_upgrade(priority=["castle", "wall", "academy"])
    automation.research(priority=["economy", "development"])
```

Or, with no explicit castle:

```python
with automation.use_account("serious_stuff"):
    automation.research(priority=["economy", "development"])
```

Semantics:

- entering the context ensures game running, login if needed, and correct account selection,
- if `castle` is provided, it also ensures that target castle is selected,
- if `castle` is omitted, it uses the current castle and performs no switch,
- operations inside the block reuse that prepared session state.

The name should not be `login(...)` because the context is doing more than login:

- ensure emulator/game readiness,
- verify account,
- optionally align the castle,
- then run work.

Better names are:

- `use_account(...)`
- `use_session(...)`
- `account_scope(...)`

The Python context manager should not own the preparation logic itself. It should delegate to one shared session-preparation service that other entry points can reuse.

### 9.7 Exit behavior

The context manager should default to no cleanup action on exit.

Default exit behavior:

- do not log out,
- do not switch back to the previous castle,
- do not mutate the session unless the block itself requested it.

Reasons:

- logout is not required for correctness,
- switch-back is a second hidden castle-transition policy,
- implicit cleanup adds time, risk, and failure modes,
- the least surprising behavior is that the block guarantees entry state, not symmetrical teardown.

If later a restore-style behavior is proven necessary, it should be opt-in and explicit, for example:

- `restore_previous_castle=True`
- `logout_on_exit=True`

Those should be later additions, not the default contract.

### 9.8 Direct function calls outside a context

Direct Python task calls without a session context should use the current selected castle and should not switch.

Recommended rule:

- direct call with no surrounding account context means "operate on the live current session state",
- if the account or game state is not ready for that call, fail fast instead of silently logging in or switching.

That preserves a clean separation:

- context manager: establish runtime state,
- direct function call: operate on current state.

### 9.9 Standalone login-style command

A standalone command-line entry point is also desirable, but it must reuse the same preparation path as the Python context manager.

Recommended rule:

- command-line "login" behavior and Python `use_account(...)` entry behavior must be backed by one shared implementation,
- the CLI command must not reimplement account verification, login, or optional castle alignment separately.

Recommended semantics for a standalone command:

```powershell
python -m pnc_automation.cli login --account serious_stuff
python -m pnc_automation.cli login --account serious_stuff --kingdom K230 --castle-name "Lv. 6 hellhound"
```

Semantics:

- ensure game running,
- login if needed,
- verify the requested account,
- if a castle is supplied, ensure that castle is selected,
- otherwise leave the current selected castle unchanged,
- then exit without logout or cleanup.

This command is useful for:

- manual operator preparation before an interactive session,
- shell scripts,
- debugging,
- separating "prepare session" from later task execution.

The command name may still be `login` for operator convenience, but the implementation contract should be defined as session preparation rather than credential entry only.

## 10. Castle roster ownership and refresh strategy

### 10.1 Canonical rule

`config/castles.yaml` is the only canonical roster store.

The runtime should never require users to define the same castle list again somewhere else.

### 10.2 Passive roster sync

The existing passive sync behavior is correct and should remain:

- when the runtime safely observes Manage Char,
- and the active account is verified,
- the visible roster window is merged back into `castles.yaml`.

This is cheap, useful, and already well integrated.

### 10.3 Full roster refresh must be a separate workflow

A deterministic full-scan roster refresh should be owned by a dedicated workflow, not hidden inside login.

Recommended new task/workflow:

- `refresh_castle_roster`

Recommended script:

```yaml
name: refresh_castle_roster

steps:
  - task: ensure_game_running
  - task: login
  - task: refresh_castle_roster
```

This task should:

1. open Manage Char from a verified in-game state,
2. scan the complete roster,
3. persist the ordered roster with `ordering: full_scan`,
4. return safely to home city.

### 10.4 Why full refresh should not happen before or inside login

A full roster scan does not belong in login because:

- roster scanning is not required for every successful login,
- it adds latency and UI churn to the bootstrap path,
- login should stay focused on proving the correct account is active,
- full-scan ordering is a separate concern from account bootstrap,
- hiding the scan inside login creates a second implicit ownership path for roster refresh.

Also, "before login" is the wrong boundary entirely because the roster is only available after the game is in a verified in-game state.

### 10.5 Failure policy when the roster is insufficient

Explicit target execution must fail fast when the roster does not support safe switching.

Required rules:

- if the target castle is visible in the current roster window, switching may proceed even if ordering is unknown,
- if the target is off-screen and `ordering != full_scan`, fail fast with an error that tells the user to run `refresh_castle_roster`,
- if the explicit target is absent from the cached roster and not currently visible, fail fast,
- the runner must not guess scroll direction from partial ordering.

This keeps castle switching deterministic and safe.

## 11. Artifact and diagnostic ownership

The current artifact path is wrongly tied to `account.selected_castle`.

After this refactor, artifact ownership should become account-scoped, not castle-config-scoped.

Recommended direction:

- `AccountConfig.artifact_directory_name` should be replaced by an account-scoped directory name derived from `account.id`,
- step results and logs should record the requested explicit castle when present,
- observations and smoke validation may still record the observed current castle when known.

This avoids the current design bug where artifact storage depends on a field that should no longer exist.

Optional later enhancement:

- add requested/effective castle metadata to `StepRunResult` or structured logs.

That is useful, but the primary fix is removing the castle dependency from artifact root ownership.

## 12. Detailed implementation plan

### 12.1 Config model refactor

Update:

- `pnc_automation/config/models.py`
- `pnc_automation/config/loader.py`
- `pnc_automation/config/validation.py`
- `pnc_automation/artifact_naming.py`

Required changes:

- rename `SelectedCastleConfig` to `CastleIdentity`,
- remove `selected_castle` from `AccountConfig`,
- remove account-level castle validation from `validate_app_config`,
- keep `(instance_id, pnc_account_id)` uniqueness validation because runtime account identity still depends on that pair,
- replace castle-based artifact naming with account-based artifact naming,
- keep roster validation in `castles.yaml`,
- move shared castle YAML parsing into one canonical helper used by both config and script loading.

### 12.2 Script model refactor

Update:

- `pnc_automation/automation/scripts/models.py`
- `pnc_automation/automation/scripts/loader.py`
- `pnc_automation/automation/scripts/registry.py`

Required changes:

- add `castle: CastleIdentity | None` to `ScriptStep`,
- add the same field to `PreparedScriptStep`,
- parse the step-level `castle` mapping centrally,
- add task-level castle-target policy metadata,
- validate `DISALLOWED` / `OPTIONAL` / `REQUIRED` at prepare-script time.

### 12.3 Task context refactor

Update:

- `pnc_automation/automation/task_context.py`

Required changes:

- expose the prepared step's explicit `castle` target through the context,
- remove all remaining dependence on `context.account.selected_castle`,
- keep task-specific `params` separate from castle targeting so the concepts stay orthogonal.

### 12.4 Runner refactor

Update:

- `pnc_automation/automation/runner.py`
- `pnc_automation/automation/script_runner.py`

Required changes:

- run a centralized castle-alignment pre-step when the prepared step contains an explicit target and the task policy allows it,
- reuse the canonical `SelectCastleTask` implementation rather than introducing a second switch path,
- keep the roster provider unchanged because it is already keyed correctly by `pnc_account_id`,
- create `ObservationService` with account-scoped artifact directories.

### 12.5 Castle-selection task refactor

Update:

- `pnc_automation/automation/tasks/select_castle_task.py`
- `pnc_automation/pnc/screen_flows.py`

Required changes:

- `SelectCastleTask` must read the explicit requested castle from context instead of `account.selected_castle`,
- the task must fail fast if it is executed without a requested target,
- screen-flow helpers should rename their parameters from `selected_castle` to `target_castle` or equivalent,
- all switching and verification logic remains centralized there.

### 12.6 Observation and vision model rename

Update:

- `pnc_automation/pnc/observation.py`
- `pnc_automation/vision/observation_builder.py`
- `pnc_automation/vision/pnc_observation_enricher.py`

Required changes:

- replace `SelectedCastleConfig` references with `CastleIdentity`,
- keep the current-castle observation semantics unchanged,
- keep roster sync behavior unchanged except for the type rename.

### 12.7 New roster-refresh task

Add:

- `pnc_automation/automation/tasks/refresh_castle_roster_task.py`
- task registration in `automation/scripts/registry.py`
- one example script under `scripts/`

Required behavior:

- open Manage Char,
- scan and merge every visible roster page,
- persist `ordering: full_scan`,
- fail fast on inconsistent page progression,
- return to home city when complete.

This is the correct place to own full ordering refresh.

### 12.8 Documentation and example migration

Update:

- `config/accounts.yaml`
- `config/castles.example.yaml`
- any script examples that currently rely on implicit configured castle selection,
- planning documents that still describe the account as owning one selected castle.

Required rule:

- remove obsolete text in the same change,
- do not keep documentation for both the old and new castle-target contracts.

### 12.9 Python API facade

Add:

- a small public Python API module, for example `pnc_automation/api.py`,
- one context-manager entry point for account/session preparation,
- thin function wrappers for supported tasks only when they can forward into the canonical runner/task system without duplicating business logic.

Required behavior:

- `use_account(account_id, castle=None)` prepares the same runtime state as the script model,
- direct function wrappers with no explicit castle operate on the current selected castle,
- the API must not introduce a second implementation of login, selection, or task execution,
- the API must default to no logout and no castle restore on context exit.

### 12.10 Shared session-preparation service and CLI command

Add:

- one internal shared service, for example `prepare_account_session(account_id, castle=None)`,
- one CLI command entry point that calls that service,
- reuse of the same service from the Python context manager.

Required behavior:

- the shared service owns emulator readiness, login if needed, account verification, and optional castle alignment,
- the Python context manager wraps that service,
- the standalone CLI `login` command wraps that service,
- no second login/bootstrap implementation may exist in the CLI layer,
- CLI invocation with no castle preserves the current selected castle,
- CLI invocation with a castle aligns to that target and then exits without cleanup.

## 13. Validation plan

### 13.1 Automated tests

Add or update tests for:

- config loading without `selected_castle`,
- config rejection if old `selected_castle` is still authored,
- shared castle YAML parsing from both config and script loaders,
- task-policy validation for `DISALLOWED`, `OPTIONAL`, and `REQUIRED`,
- `select_castle` failure when no explicit target is provided,
- runner pre-step auto-switch when a non-`select_castle` task declares `castle`,
- no-switch behavior when `castle` is absent,
- failure when an off-screen target requires a missing `full_scan` ordering,
- passive roster sync still merging visible windows,
- full roster refresh persisting `ordering: full_scan`,
- account-scoped artifact directory naming,
- Python context entry performing login/account verification and optional castle alignment through the canonical path,
- Python context exit performing no implicit logout or castle restore by default,
- direct Python task calls using current-castle semantics without hidden switching,
- standalone CLI `login` command reusing the shared session-preparation service,
- standalone CLI `login` command preserving current-castle state when no castle is provided,
- standalone CLI `login` command aligning the explicit target castle when one is provided.

### 13.2 Live smoke validation

Required smoke coverage:

1. `ensure_game_running -> login -> building_upgrade` with no explicit target while already on the desired castle.
2. `ensure_game_running -> login -> building_upgrade` with an explicit `castle` target different from the current castle.
3. `ensure_game_running -> login -> refresh_castle_roster` to prove ordered roster refresh works live.
4. A failure-path smoke or controlled integration test proving that an off-screen target without `full_scan` ordering fails fast instead of guessing.

### 13.3 Validation artifacts

On mismatch or failure, capture:

- before and after screenshots,
- current screen type,
- requested target castle,
- observed current castle when known,
- cached roster ordering state,
- target `pnc_account_id`.

## 14. Migration sequence

The migration should happen in one coherent refactor, not as a temporary dual-schema bridge.

Recommended order:

1. Rename `SelectedCastleConfig` to `CastleIdentity`.
2. Remove `selected_castle` from `AccountConfig`, config loading, validation, and authored config.
3. Add script-step `castle` parsing and task-policy validation.
4. Refactor `SelectCastleTask` to consume the explicit runtime target.
5. Add runner-level pre-step castle alignment for explicit target steps.
6. Convert artifact naming from castle-based to account-based.
7. Add `refresh_castle_roster` and the dedicated refresh script.
8. Update configs, examples, smoke scripts, tests, and documentation in the same change.
9. Delete all obsolete selected-castle references immediately.

## 15. Alternatives rejected

### 15.1 Keep `selected_castle` in account config and add step overrides

Rejected because it creates two sources of truth:

- account default castle,
- step override castle.

That would preserve the original ownership bug instead of fixing it.

### 15.2 Put the castle target inside each task's `params`

Rejected because it duplicates the same castle parsing and validation across many task parameter models.

The castle target is orthogonal to task business parameters and should remain its own shared step field.

### 15.3 Refresh the full roster during every login

Rejected because it couples two different responsibilities:

- account bootstrap,
- full ordered roster discovery.

That would add cost, complexity, and hidden side effects to login.

### 15.4 Key rosters by `(instance_id, pnc_account_id)`

Rejected because the roster belongs to the P&C login, not to the BlueStacks instance.

Keying by instance would duplicate the same roster concept across emulators.

### 15.5 Make the Python API the canonical execution model

Rejected because it would either:

- duplicate the script/task runner semantics in a second API surface, or
- force the internal runtime architecture to depend on a convenience layer.

The correct design is:

- runner/task/script contract is canonical,
- Python API is thin sugar over that contract.

### 15.6 Log out or restore castle automatically on context exit

Rejected as the default because it adds hidden side effects and a second transition policy.

Context entry is the useful guarantee. Symmetric teardown is optional behavior, not the default contract.

### 15.7 Implement CLI login separately from the Python context manager

Rejected because it would create two bootstrap ownership paths:

- Python session preparation,
- CLI login preparation.

The correct design is one shared session-preparation service with multiple thin entry points.

## 16. Definition of done

This refactor is done only when all of the following are true:

- `accounts.yaml` no longer supports or documents `selected_castle`,
- `castles.yaml` is the only canonical castle list store,
- there is one shared `CastleIdentity` model used across config, scripts, observation, and runtime,
- script steps can optionally declare an explicit `castle`,
- omitted `castle` means "use current castle without switching",
- explicit `castle` means "switch before the task through the canonical `SelectCastleTask` path",
- any Python context API is only a thin facade over the same contract,
- any standalone CLI `login` command is only a thin facade over the same session-preparation contract,
- Python direct task calls default to current-castle semantics,
- full ordered roster refresh is owned by a dedicated workflow and not hidden inside login,
- artifact ownership no longer depends on a removed castle config field,
- obsolete code and documentation paths have been deleted,
- no duplicate castle-target parsing, validation, or switching logic remains.

## 17. Recommended next implementation slice

The smallest coherent implementation slice is:

1. remove `selected_castle` from account config and rename the shared castle type,
2. add step-level `castle` parsing plus task-policy validation,
3. refactor `SelectCastleTask` to use the runtime target,
4. add runner-level pre-step castle alignment,
5. switch artifact roots to account-scoped naming,
6. migrate the existing smoke script to use an explicit `select_castle` step target,
7. then add `refresh_castle_roster` as the next follow-up slice.

That sequence fixes the ownership problem first, keeps the runtime usable immediately, and adds full ordered roster refresh as the next bounded increment instead of blocking the whole refactor on it.
