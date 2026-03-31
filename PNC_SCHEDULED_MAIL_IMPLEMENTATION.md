# PNC Scheduled Mail Implementation Document

## 1. Purpose

This document defines the clean implementation plan for scheduled mail in the current PNC automation platform.

The goal is not to create a second mail-sending system. The goal is to add a new authored schedule source that reuses the existing canonical mail workflow already implemented through:

- [mail.py](/c:/Users/lebel/pnc/pnc_automation/app/pnc/domain/mail.py)
- [send_mail_task.py](/c:/Users/lebel/pnc/pnc_automation/app/automation/tasks/send_mail_task.py)
- [api.py](/c:/Users/lebel/pnc/pnc_automation/app/entrypoints/api.py)

This document also covers the direct command/API surface for ad hoc mail sends, because the user-facing feature is one coherent mail-dispatch capability with multiple entry sources:

- direct single-mail execution,
- script-authored `send_mail` steps,
- scheduler-driven execution from authored mail catalogs.

The scheduler contract in this document is an hourly heartbeat, not one giant two-week scheduled task. Windows Task Scheduler should trigger the automation hourly, and the application should determine whether the current UTC hour is due for any authored mail schedule relative to the configured rotation start time.

## 2. Current Repository Context

The repository already has the right runtime primitives for mail:

- one canonical task id model in [task.py](/c:/Users/lebel/pnc/pnc_automation/app/automation/engine/task.py),
- one canonical task registry in [registry.py](/c:/Users/lebel/pnc/pnc_automation/app/authoring/scripts/registry.py),
- one script model and loader in [models.py](/c:/Users/lebel/pnc/pnc_automation/app/authoring/scripts/models.py) and [loader.py](/c:/Users/lebel/pnc/pnc_automation/app/authoring/scripts/loader.py),
- one script runner in [script_runner.py](/c:/Users/lebel/pnc/pnc_automation/app/automation/engine/script_runner.py),
- one application wiring layer in [app.py](/c:/Users/lebel/pnc/pnc_automation/app/entrypoints/app.py),
- one CLI entry point in [cli.py](/c:/Users/lebel/pnc/pnc_automation/app/entrypoints/cli.py),
- one Python convenience API in [api.py](/c:/Users/lebel/pnc/pnc_automation/app/entrypoints/api.py),
- one canonical `send_mail` task implementation in [send_mail_task.py](/c:/Users/lebel/pnc/pnc_automation/app/automation/tasks/send_mail_task.py).

The repository also already distinguishes:

- authored runtime/account config in `config/accounts.yaml`,
- authored castle aliases in `config/castle_targets.yaml`,
- authored run scripts in `scripts/`,
- scheduler-oriented routines under `scripts/routines/`.

That architecture is already strong. Scheduled mail should extend it, not bypass it.

## 3. Confirmed Product Decisions From Discovery

The design decisions established during discussion are:

- We must reuse the existing mailing functionality. Scheduled mail is a new source of `send_mail` requests, not a second mail implementation.
- We should not integrate Google Calendar for v1. The added auth, sync, and external-dependency surface is not justified for a deterministic internal scheduler contract.
- We should use YAML, not plain text, because this repository already uses validated authored YAML and expects fail-fast schema validation.
- The new mail-authored YAML must not duplicate account ownership. `accounts.yaml` already owns account configuration.
- Mail definitions and mail schedules should be stored separately so schedules can reference reusable mail ids.
- One schedule must support many mails.
- Schedule files should remain global/shared authored intent. Account and instance selection remain external runtime context supplied by the existing account config and command/routine invocation.
- The schedule shape should be a day-plus-hour composite, not a flattened 336-slot integer.

## 4. Goals

The feature must provide all of the following cleanly:

- keep direct `send_mail` available as the canonical single-mail task,
- support ad hoc direct execution from CLI and Python API using string parameters,
- support reusable authored mail definitions,
- support reusable authored schedules that reference mail ids,
- support multiple mail ids in the same schedule,
- support Windows Task Scheduler as the external hourly trigger,
- keep castle targeting account-scoped through existing `castle_ref` resolution,
- preserve one canonical implementation per concept.

## 5. Non-Goals

This slice should not add:

- Google Calendar integration,
- a second mail-send task with its own UI workflow,
- account ids inside the new mail-authored YAML files,
- free-form plain-text schedule parsing,
- duplicated inline mail bodies repeated inside schedule entries,
- a task-within-task execution model that reimplements runner behavior.

## 6. Canonical Target Architecture

## 6.1 High-level design

The clean design has three layers:

1. Authored mail definition layer
   - reusable mail definitions keyed by `mail_id`.
2. Authored schedule layer
   - reusable schedule definitions keyed by `schedule_id`, each referencing one or more `mail_id`s.
3. Runtime expansion layer
   - resolve which schedules are due for the current hourly heartbeat,
   - expand them into generated canonical `send_mail` script steps,
   - execute those steps through the existing runner.

This means scheduled mail remains a producer of normal `SEND_MAIL` work, not a second mail workflow.

The runtime decision point is:

- Windows Task Scheduler runs once per hour,
- the application compares the current UTC timestamp to the configured rotation start time,
- the application computes the current 14-day day index plus current UTC hour,
- the application loads `mail_schedules.yaml`,
- the application determines whether any schedules are due in this hourly execution window.

## 6.2 Public runtime surface

There should be exactly two public mail execution surfaces:

- existing single-mail `send_mail`,
- new application-level `run_mail_schedules`.

Important ownership rule:

- `send_mail` remains the only public single-mail automation task.
- `run_mail_schedules` should be an application/CLI/API entry point that expands due schedule definitions into generated `send_mail` script steps.

This is cleaner than introducing a second automation task such as `send_scheduled_mail`, because generated steps automatically preserve:

- existing `send_mail` param parsing,
- existing send verification,
- existing step-level castle alignment through `castle_ref`,
- existing runner retry/replan behavior.

## 6.3 Why scheduled mail should not be a second automation task

If scheduled mail becomes a new UI-driving task, it would need to own:

- per-mail queue state,
- per-mail castle switching,
- repeated mail-send workflow reuse,
- its own nested execution semantics.

That would either duplicate `send_mail` behavior or force awkward task-within-task execution.

The correct design is:

- schedule resolution above the runner,
- generated `RunScript` below that,
- existing `SEND_MAIL` steps inside the generated script.

That preserves the runner as the single orchestration engine.

## 7. Authored File Ownership

Add two new optional authored sibling files under `config/`:

- `config/mail_definitions.yaml`
- `config/mail_schedules.yaml`

Also add examples:

- `config/mail_definitions.example.yaml`
- `config/mail_schedules.example.yaml`

Ownership split:

- `accounts.yaml` owns configured accounts, instances, and login/runtime config.
- `castle_targets.yaml` owns account-scoped `castle_ref` aliases.
- `mail_definitions.yaml` owns reusable mail definitions.
- `mail_schedules.yaml` owns reusable schedule definitions.
- CLI/API/routine invocation owns which account is being run and optionally which schedule ids to consider.

This keeps account ownership out of the new mail-authored YAML, exactly as desired.

## 8. Canonical Authored YAML Contracts

## 8.1 `config/mail_definitions.yaml`

This file stores reusable mail payloads by id.

Recommended shape:

```yaml
mails:
  - id: alliance_reset
    castle_ref: main
    recipient_kind: alliance
    subject: Alliance Reset Reminder
    body: |
      Reset is today.
      Please finish donations and rallies.

  - id: player_followup_alpha
    castle_ref: main
    recipient_kind: player
    player_name: SomePlayer
    subject: Follow-up
    body: |
      Hi,
      Checking in on today's plan.
```

Rules:

- `id` is required and unique.
- `castle_ref` is optional, but when present it must resolve through the selected account's `castle_targets.yaml`.
- The remaining keys intentionally mirror canonical `send_mail` params.
- The loader should reuse existing `parse_send_mail_params(...)` for the mail payload instead of inventing a second parser.
- `body: |` is normal YAML multiline-string syntax and should be supported naturally.

## 8.2 `config/mail_schedules.yaml`

This file stores reusable schedule groups by id.

Recommended shape:

```yaml
rotation:
  cycle_days: 14
  start_utc: 2026-03-30T00:00:00Z

mail_schedules:
  - id: mailschedule_1
    enabled: true
    day_indices: [0, 7]
    hour_utc: 5
    mail_ids:
      - alliance_reset
      - player_followup_alpha

  - id: mailschedule_2
    enabled: true
    day_indices: [9]
    hour_utc: 19
    mail_ids:
      - player_followup_alpha
```

Rules:

- `rotation.cycle_days` is fixed to `14` in v1 and must fail fast for any other value.
- `rotation.start_utc` is required and must be a UTC timestamp aligned with day-index zero.
- `mail_schedules[].id` is required and unique.
- `enabled` defaults to `true` when omitted.
- `day_indices` is required and non-empty.
- `hour_utc` is required and must be an actual UTC hour `0..23`.
- `mail_ids` is required, non-empty, and ordered.
- Unknown `mail_id` references must fail fast during load/validation.
- Duplicate `mail_id`s inside one schedule should fail fast instead of being silently deduplicated.

## 8.3 Why the schedule uses `hour_utc`

The discussion converged on a day-plus-hour composite rather than a flattened slot integer. That is correct and should be preserved.

The implementation should intentionally store the hour as actual `hour_utc`, not a shifted pseudo-index such as `4 => 05:00`, because:

- actual hours are easier to read,
- they avoid midnight wraparound ambiguity,
- they map directly to current UTC time,
- they keep authored YAML leaner and less surprising.

So the final authored contract should be:

- `day_indices`: scheduler-cycle day positions,
- `hour_utc`: real UTC hour.

## 9. Day-Index Contract

The framework should define one canonical 14-day rotation:

- `0 = Monday, week 1`
- `1 = Tuesday, week 1`
- `2 = Wednesday, week 1`
- `3 = Thursday, week 1`
- `4 = Friday, week 1`
- `5 = Saturday, week 1`
- `6 = Sunday, week 1`
- `7 = Monday, week 2`
- `8 = Tuesday, week 2`
- `9 = Wednesday, week 2`
- `10 = Thursday, week 2`
- `11 = Friday, week 2`
- `12 = Saturday, week 2`
- `13 = Sunday, week 2`

`rotation.start_utc` must therefore point to a Monday 00:00:00 UTC that represents day index `0`.

Operational contract:

- Windows Task Scheduler remains the external hourly trigger.
- The authored `start_utc` is the explicit cycle-start source of truth that makes due-resolution deterministic inside the app.
- The scheduler does not need to understand the 2-week rotation. It only needs to run the command once per hour.
- The application owns the comparison between the current UTC time and the authored rotation start.

## 10. Runtime Resolution Rules

Given current time `now_utc`, the schedule resolver should:

1. truncate to the current UTC hour bucket,
2. compute `elapsed_days = floor((now_utc - start_utc) / 1 day)`,
3. compute `current_day_index = elapsed_days % 14`,
4. compute `current_hour_utc = now_utc.hour`,
5. select schedules where:
   - `enabled == true`,
   - `current_day_index in day_indices`,
   - `current_hour_utc == hour_utc`.

The hourly heartbeat must therefore be the only scheduler requirement. The application, not Windows Task Scheduler, owns the 2-week rotation arithmetic.

Order rules:

- if the caller provided explicit `schedule_ids`, preserve that outer schedule order,
- otherwise preserve authored schedule order from `mail_schedules.yaml`,
- inside each schedule, preserve authored `mail_ids` order.

Collision rule:

- if the selected due schedules would send the same `mail_id` more than once in one execution window, fail fast instead of silently double-sending.

## 11. Runtime Model

Add dedicated typed models, for example under a new authoring package such as:

- `pnc_automation/app/authoring/mail/models.py`
- `pnc_automation/app/authoring/mail/loader.py`

Recommended models:

```python
@dataclass(frozen=True, slots=True)
class AuthoredMailDefinition:
    id: str
    castle_ref: str | None
    params: SendMailParams

@dataclass(frozen=True, slots=True)
class AuthoredMailSchedule:
    id: str
    enabled: bool
    day_indices: tuple[int, ...]
    hour_utc: int
    mail_ids: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class MailScheduleCatalog:
    start_utc: datetime
    definitions: tuple[AuthoredMailDefinition, ...]
    schedules: tuple[AuthoredMailSchedule, ...]
```

Recommended service behavior:

- load both YAML files once,
- validate cross-file references once,
- expose one canonical `resolve_due_mail_definitions(...)` method for the current hourly heartbeat,
- expose one canonical `build_generated_send_mail_script(...)` method or equivalent helper.

## 12. Config Loading Integration

The clean integration path is:

- extend [models.py](/c:/Users/lebel/pnc/pnc_automation/app/authoring/config/models.py) so `AppConfig` can carry the resolved mail-definition and mail-schedule paths and loaded authoring catalog,
- extend [loader.py](/c:/Users/lebel/pnc/pnc_automation/app/authoring/config/loader.py) so sibling defaults resolve to:
  - `config/mail_definitions.yaml`
  - `config/mail_schedules.yaml`
- keep these files optional when absent, but fail fast when the user invokes scheduled-mail entry points without valid loaded schedule data.

This mirrors the current loading pattern already used for:

- `castles.yaml`
- `castle_targets.yaml`

## 13. Execution Surface

## 13.1 Keep direct `send_mail`

No change in concept:

- existing `TaskId.SEND_MAIL` remains the canonical single-mail task,
- existing script-authored `task: send_mail` remains supported,
- existing Python API `send_mail(...)` remains supported.

## 13.2 Add application-level `run_mail_schedules(...)`

Add new application and script-runner methods:

- `ApplicationRunner.run_mail_schedules(...)`
- `ScriptRunner.run_mail_schedules(...)`
- `AutomationApi.run_mail_schedules(...)`

These methods should:

1. resolve due mail definitions from the loaded catalog,
2. build a generated `RunScript`,
3. execute that generated script through existing `run_script(...)`.

No new automation task id is required for v1.

## 13.3 Generated script shape

The generated script should look conceptually like:

```yaml
name: generated_mail_schedule_20260331T050000Z

steps:
  - task: ensure_game_running
  - task: login
  - task: send_mail
    castle_ref: main
    params:
      recipient_kind: alliance
      subject: Alliance Reset Reminder
      body: |
        Reset is today.
        Please finish donations and rallies.
  - task: send_mail
    castle_ref: main
    params:
      recipient_kind: player
      player_name: SomePlayer
      subject: Follow-up
      body: |
        Hi,
        Checking in on today's plan.
```

Key benefit:

- the existing runner will automatically perform per-step castle alignment before each generated `send_mail` step.

That is exactly why schedule expansion belongs above the runner instead of inside a second mail task.

## 14. CLI Design

Extend [cli.py](/c:/Users/lebel/pnc/pnc_automation/app/entrypoints/cli.py) with two direct commands:

- `send-mail`
- `run-mail-schedules`

### 14.1 `send-mail`

This is the string-parameter direct command requested by the user.

Example:

```powershell
python main.py send-mail --account primary-account --recipient-kind alliance --subject "Reset" --body "Please donate"
```

Player example:

```powershell
python main.py send-mail --account primary-account --recipient-kind player --player-name "SomePlayer" --subject "Hi" --body "Checking in"
```

Profile-route example:

```powershell
python main.py send-mail --account primary-account --recipient-kind player --profile-route-kind alliance_member --profile-route-player-name "SomePlayer" --subject "Hi" --body "Checking in"
```

CLI rule:

- CLI stays flat and string-based,
- the CLI adapter builds the nested canonical `profile_route` mapping internally before calling the existing `send_mail` task.

### 14.2 `run-mail-schedules`

Example:

```powershell
python main.py run-mail-schedules --account primary-account
```

Optional narrowing:

```powershell
python main.py run-mail-schedules --account primary-account --schedule-id mailschedule_1 --schedule-id mailschedule_2
```

Optional deterministic replay/debug input may be added later:

- `--scheduled-for-utc 2026-03-31T05:00:00Z`

but it should remain optional and primarily test/debug oriented.

Operational usage:

- configure Windows Task Scheduler to run `run-mail-schedules` every hour,
- let the application decide whether zero, one, or many scheduled mails are due in that hour,
- treat "no schedules due this hour" as a normal successful no-op.

## 15. Python API Design

[api.py](/c:/Users/lebel/pnc/pnc_automation/app/entrypoints/api.py) already exposes canonical direct mail helpers. That surface should be preserved and expanded.

Keep:

- `send_mail(...)`
- `send_alliance_mail(...)`
- `send_personal_mail(...)`

Add:

- `run_mail_schedules(account_id: str | None = None, schedule_ids: list[str] | None = None, scheduled_for_utc: datetime | None = None)`

The API should remain thin and forward into the canonical application runner.

## 16. Validation Rules

## 16.1 Mail definition validation

Reject:

- duplicate mail ids,
- empty ids,
- unsupported `recipient_kind`,
- invalid `player_name` / `profile_route` combinations,
- empty `subject`,
- empty `body`,
- unsupported extra keys,
- invalid `castle_ref` resolution at execution time.

## 16.2 Mail schedule validation

Reject:

- duplicate schedule ids,
- disabled schedules with invalid structure,
- empty `day_indices`,
- any `day_index` outside `0..13`,
- duplicate `day_indices`,
- `hour_utc` outside `0..23`,
- empty `mail_ids`,
- duplicate `mail_ids` inside one schedule,
- unknown `mail_id` references,
- `rotation.cycle_days` other than `14`,
- invalid or non-UTC `rotation.start_utc`.

## 16.3 Runtime validation

Reject:

- invoking `run_mail_schedules` when no schedule catalog is loaded,
- invoking `run_mail_schedules` with unknown requested `schedule_id`,
- one execution window that would send the same `mail_id` twice,
- generated steps whose `castle_ref` cannot be resolved for the chosen account.

## 17. Implementation Surface

Likely files to add or modify:

- [loader.py](/c:/Users/lebel/pnc/pnc_automation/app/authoring/config/loader.py)
- [models.py](/c:/Users/lebel/pnc/pnc_automation/app/authoring/config/models.py)
- [script_runner.py](/c:/Users/lebel/pnc/pnc_automation/app/automation/engine/script_runner.py)
- [app.py](/c:/Users/lebel/pnc/pnc_automation/app/entrypoints/app.py)
- [api.py](/c:/Users/lebel/pnc/pnc_automation/app/entrypoints/api.py)
- [cli.py](/c:/Users/lebel/pnc/pnc_automation/app/entrypoints/cli.py)
- [mail.py](/c:/Users/lebel/pnc/pnc_automation/app/pnc/domain/mail.py)
- new `pnc_automation/app/authoring/mail/models.py`
- new `pnc_automation/app/authoring/mail/loader.py`
- new `config/mail_definitions.example.yaml`
- new `config/mail_schedules.example.yaml`

## 18. Implementation Order

### Phase 1: Authoring models and loaders

- add typed mail-definition and mail-schedule models,
- load the two new sibling config files,
- validate all cross-file references and schedule semantics.

Exit condition:

- the app can load valid `mail_definitions.yaml` and `mail_schedules.yaml` or fail fast with precise errors.

### Phase 2: Application runner integration

- extend `AppConfig`,
- wire loaded mail authoring into `build_application_runner(...)`,
- add `ScriptRunner.run_mail_schedules(...)`,
- add `ApplicationRunner.run_mail_schedules(...)`.

Exit condition:

- the runtime can expand due schedules into a generated `RunScript`.

### Phase 3: CLI and Python API parity

- add CLI `send-mail`,
- add CLI `run-mail-schedules`,
- add Python API `run_mail_schedules(...)`.

Exit condition:

- direct ad hoc mail sends and scheduler-driven runs are both available without authored wrapper scripts.

### Phase 4: Example files and docs

- add example YAML files,
- document the 14-day day-index contract,
- document the scheduler anchor contract.

Exit condition:

- the feature is operable without reading source code.

### Phase 5: Validation and hardening

- add loader tests,
- add generated-script tests,
- add CLI/API tests,
- add end-to-end schedule-expansion tests that verify generated `send_mail` steps are correct.

Exit condition:

- scheduled mail has strong automated coverage without duplicating live UI mail tests.

## 19. Test Plan

Add automated tests for:

- valid mail-definition loading,
- invalid mail-definition rejection,
- valid mail-schedule loading,
- invalid day/hour/reference rejection,
- due-resolution at multiple UTC timestamps,
- hourly-heartbeat no-op behavior when nothing is due,
- schedule ordering,
- duplicate due-mail collision failure,
- generated script construction including `castle_ref`,
- `run_mail_schedules(...)` calling through to existing runner behavior,
- CLI `send-mail` argument translation,
- CLI `run-mail-schedules` argument translation.

Existing `send_mail` task tests should remain the single UI-workflow proof for actual sending behavior.

## 20. Acceptance Criteria

The feature is complete only when all of the following are true:

- scheduled mail does not introduce a second mail-send UI workflow,
- direct `send_mail` remains the only single-mail automation task,
- scheduled mail expands into generated canonical `send_mail` steps,
- the external scheduler only needs to run hourly,
- the application computes due schedules relative to the authored `start_utc`,
- no account ids are duplicated inside the new mail-authored YAML,
- mail definitions and schedules are stored separately,
- schedules can reference multiple mail ids,
- `castle_ref` remains account-scoped through existing castle-target resolution,
- CLI supports direct `send-mail` with string parameters,
- CLI and Python API support schedule execution,
- invalid authored content fails fast with precise errors,
- due schedules execute in deterministic order,
- duplicate due mail dispatches in one execution window are rejected,
- there is exactly one canonical implementation for mail sending behavior.

## 21. Rejected Alternatives

Rejected for v1:

- Google Calendar integration,
- plain-text schedule files,
- storing account ids in mail-definition or mail-schedule YAML,
- embedding full mail bodies directly inside every schedule entry,
- a new `send_scheduled_mail` automation task that reimplements mail execution,
- a flattened 336-slot schedule index.

## 22. Final Design Summary

The clean solution is:

- one canonical existing `send_mail` task,
- one global reusable `mail_definitions.yaml`,
- one global reusable `mail_schedules.yaml`,
- one explicit 14-day day-index schedule contract relative to authored `start_utc`,
- one hourly scheduler heartbeat that lets the application decide what is due,
- one application-level `run_mail_schedules(...)` entry point that expands due schedules into generated `send_mail` script steps,
- one direct CLI/API `send-mail` surface for string-based ad hoc execution.

This preserves the repository's current architecture, stays DRY, avoids duplicated mail logic, keeps account ownership where it already belongs, and provides a clean path for both manual and scheduler-driven mail dispatch.
