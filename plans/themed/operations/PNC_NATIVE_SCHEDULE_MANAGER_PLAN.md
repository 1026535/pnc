# PNC External Orchestrator And Instance Runner Plan

## 1. Purpose

This plan replaces the earlier native C++ schedule-manager idea.

The current goal is not to homebrew a scheduler. The goal is to manage multiple BlueStacks instances, accounts, castles, and eventually multiple games by combining:

- an external scheduler/orchestrator for due-time calculation, dashboards, logs, retries, and concurrency,
- a Python instance-aware runner for all emulator/game-specific work,
- the existing PNC automation runtime for PNC tasks,
- BlueStacks Multi-instance Manager as the owner of emulator instances.

The central operating model is:

```text
external scheduler
  runs one job per BlueStacks instance

Python instance runner
  owns one emulator lane
  iterates the configured castles/games inside that lane
  calls existing game-specific automation
```

## 2. Superseded Decision

The old plan proposed a small C++ executable that would:

- parse YAML schedules,
- compute due jobs,
- supervise Python commands,
- record state,
- eventually become a local always-running manager.

That is no longer the preferred direction.

Reasons:

- scheduling, retries, logs, and dashboards are already solved by external orchestrators,
- a C++ daemon would become another platform to maintain,
- the real complexity is not timing; it is mapping emulator instances to games/accounts/castles safely,
- BlueStacks UI automation should run in the logged-in interactive session, not as a Windows service,
- cross-game scaling needs a generic instance runner more than a custom scheduler.

C++ may still be useful later for small native helpers, but it should not own v1 scheduling.

## 3. Product Decisions From Discussion

- BlueStacks instance names are runtime/emulator lanes, not game account names.
- The visible BlueStacks lanes are currently:
  - `serious_stuff`
  - `testing`
  - `157_farm`
  - `mega_old_acc`
  - `3xx_spies`
  - `main`
- Work should run in parallel across different BlueStacks instances.
- Work must stay sequential within one BlueStacks instance.
- The runner should iterate each instance's configured castles/accounts.
- The YAML examples in this repo are development examples, not the full operational model.
- The existing `rotation:` schedule shape is still useful, but scheduling should be owned by an external tool where possible.
- The repo should provide stable CLI commands that an external scheduler can run.
- PNC should be one game module, not the whole orchestration system.
- The design should leave room for bots for other games later.

## 4. Recommended External Tool

Use an external scheduler/orchestrator for v1, with Cronicle as the leading candidate.

Cronicle is attractive because it provides:

- web UI,
- scheduled/repeating/on-demand jobs,
- job history,
- live logs,
- retries/failure visibility,
- concurrency controls,
- shell-command execution,
- room to run multiple workers later.

Alternative tools can be evaluated, but the repo plan should assume an external scheduler with the following minimum capabilities:

- launch a command with arguments,
- run several jobs concurrently,
- limit concurrency by category/resource,
- capture stdout/stderr,
- record exit status,
- schedule interval and calendar jobs,
- run under the logged-in Windows user or otherwise preserve interactive BlueStacks access.

Windows Task Scheduler remains acceptable for simple local heartbeat jobs, but it is less convenient for dashboards, fleet visibility, and multi-instance coordination.

## 5. Target Architecture

```text
External Scheduler
  - job schedules
  - dashboard
  - logs
  - retries
  - max concurrency
  - one job per emulator lane

Python Bot Runner
  - loads bot target config
  - resolves BlueStacks instance lane
  - enforces per-instance lock
  - iterates configured games/castles
  - calls game-specific routines

PNC Automation Runtime
  - existing ApplicationRunner / ScriptRunner
  - account/castle config
  - selectors/OCR/navigation/tasks
  - PNC YAML run scripts

BlueStacks
  - owns emulator instances
  - provides ADB/runtime display names
```

The external scheduler should not know PNC internals. It should run stable CLI commands such as:

```powershell
py -3.13 -m pnc_automation.app.entrypoints.cli run-instance --instance testing --routine pnc_daily
```

or, during transition:

```powershell
py -3.13 -m pnc_automation.app.entrypoints.cli run --account testing --script scripts/routines/daily_castle_maintenance.yaml
```

## 6. Concurrency Model

Concurrency is based on BlueStacks instance lanes.

Rules:

- one active job per BlueStacks instance,
- different BlueStacks instances may run simultaneously,
- account/castle iteration inside one instance is sequential,
- the runner should fail fast if another process already holds the same instance lock,
- global concurrency may still be capped to protect CPU/RAM.

Example:

```text
serious_stuff -> castle A -> castle B -> castle C
testing       -> castle A -> castle B
157_farm      -> castle A -> castle B -> castle C
mega_old_acc  -> castle A
3xx_spies     -> castle A -> castle B
main          -> castle A -> castle B -> castle C
```

These six lanes can run in parallel if the host can handle it, but each lane has only one active automation flow.

## 7. Current Config Reality

The current local `config/accounts.yaml` should distinguish:

- BlueStacks instance display names,
- configured automation account targets,
- PNC login identities,
- castle aliases.

The runtime resolver uses BlueStacks `display_name` values from `C:\ProgramData\BlueStacks_nxt\bluestacks.conf`.

The observed BlueStacks display names are:

```text
serious_stuff
testing
157_farm
mega_old_acc
3xx_spies
main
```

Current important caveat:

- `main` may be a current-session lane with no stored login credentials.
- The runner should support current-session operation for such lanes when credential login is not configured.
- The runner should not assume a BlueStacks instance name has semantic game meaning.

## 8. New Bot Target Config

Add a new config layer for orchestration targets, separate from existing PNC account config.

Candidate file:

```text
config/bot_targets.yaml
```

Example:

```yaml
instances:
  - id: testing
    bluestacks_display_name: testing
    max_parallel_jobs: 1
    games:
      - id: pnc
        account: testing
        castles:
          - castle_ref: hopeful_npc_k323
            routines: [pnc_daily]
          - castle_ref: cute_zenpc
            routines: [pnc_farm]

  - id: main
    bluestacks_display_name: main
    max_parallel_jobs: 1
    games:
      - id: pnc
        account: main
        login_mode: current_session
        castles:
          - castle_ref: main
            routines: [pnc_daily]
          - castle_ref: lazy_intern
            routines: [pnc_farm]
```

This file should not duplicate game workflow YAML. It only maps:

- instance lane,
- game,
- game account target,
- castle refs,
- routine ids.

## 9. Routine Registry

Add a small routine registry that maps routine ids to existing game-specific commands.

Candidate file:

```text
config/bot_routines.yaml
```

Example:

```yaml
routines:
  - id: pnc_daily
    game: pnc
    script: scripts/routines/daily_castle_maintenance.yaml

  - id: pnc_build_wall
    game: pnc
    command: build
    params:
      priority_file: scripts/manual/build_batches/wall.txt
      allow_speedups: false

  - id: pnc_mail_hourly
    game: pnc
    command: run-mail-schedules
```

The registry must compile into existing Python task/script calls. It must not define low-level click sequences.

## 10. CLI Surface

Add CLI commands designed for external schedulers.

### 10.1 Run one instance lane

```powershell
py -3.13 -m pnc_automation.app.entrypoints.cli run-instance --instance testing
```

Behavior:

- load `config/bot_targets.yaml`,
- acquire lock for `testing`,
- start or require the BlueStacks lane according to policy,
- iterate configured games/castles/routines for that lane,
- emit one machine-readable summary,
- return non-zero if any required routine fails.

### 10.2 Run one explicit target

```powershell
py -3.13 -m pnc_automation.app.entrypoints.cli run-target --target testing:hopeful_npc_k323 --routine pnc_daily
```

Behavior:

- resolves one configured target,
- runs one routine for one castle/account,
- useful for manual runs and scheduler smoke tests.

### 10.3 List configured lanes

```powershell
py -3.13 -m pnc_automation.app.entrypoints.cli list-bot-targets
```

Behavior:

- validates target config,
- prints instances/games/castles/routines,
- reports missing BlueStacks display names or missing castle refs.

## 11. External Scheduler Job Shape

The external scheduler should create one job per BlueStacks lane, for example:

```text
pnc_instance_serious_stuff
pnc_instance_testing
pnc_instance_157_farm
pnc_instance_mega_old_acc
pnc_instance_3xx_spies
pnc_instance_main
```

Each job runs:

```powershell
py -3.13 -m pnc_automation.app.entrypoints.cli run-instance --instance <instance_id>
```

Recommended scheduler categories/resources:

- category: `pnc`
- resource key: one per BlueStacks instance,
- max concurrency per resource: 1,
- optional global max concurrency: start with 2 or 3 before trying all 6.

This lets the external tool schedule six lanes simultaneously while still preventing same-instance collisions.

## 12. Rotation Schedules

Keep the `rotation:` format as the canonical calendar-cycle model when the repo needs to express cycle-aware intent.

The external scheduler may own simple periodic timing, but the bot runner can still use rotation-aware filtering inside a lane if a routine needs "day index X of a 14-day game cycle."

Canonical shape:

```yaml
rotation:
  cycle_days: 14
  start_utc: 2026-03-30T00:00:00Z
```

Job-level rotation filter:

```yaml
schedule:
  day_indices: [0, 7]
  hour_utc: 5
```

Rules:

- use UTC for rotation math,
- `day_indices` are zero-based within `cycle_days`,
- `hour_utc` is an hour bucket,
- rotation filters should skip non-due work inside the runner instead of requiring the external scheduler to understand game cycles.

This preserves the existing scheduled-mail concept while avoiding a custom scheduler.

## 13. Locks And State

The Python runner should own lightweight local locks, not the external scheduler alone.

Recommended lock files:

```text
.runtime/locks/instance-testing.lock
.runtime/locks/instance-main.lock
```

Lock contents:

```json
{
  "instance": "testing",
  "pid": 12345,
  "started_at": "2026-07-17T14:00:00Z",
  "command": "run-instance testing"
}
```

Rules:

- acquire before touching an emulator lane,
- release on normal exit,
- detect stale locks by missing process id or age threshold,
- fail fast by default when a live lock exists.

This is the in-repo safety net if the external scheduler is misconfigured.

## 14. State And Logs

Let the external scheduler own job history and stdout/stderr logs.

The Python runner should still produce a concise JSON summary for automation consumption:

```json
{
  "instance": "testing",
  "started_at": "2026-07-17T14:00:00Z",
  "finished_at": "2026-07-17T14:23:00Z",
  "targets": [
    {
      "game": "pnc",
      "account": "testing",
      "castle_ref": "hopeful_npc_k323",
      "routine": "pnc_daily",
      "status": "success"
    }
  ]
}
```

Persistent state should stay minimal in v1:

- last successful routine timestamp per instance/account/castle/routine,
- last failure timestamp,
- consecutive failure count if useful for local skip/backoff.

Do not rebuild an external scheduler database inside the repo.

## 15. BlueStacks Lifecycle Policy

V1 should support these modes per instance:

```yaml
bluestacks:
  start_policy: require_running
```

Possible policies:

- `require_running`: fail if the instance is not already running,
- `start_if_needed`: start the instance through BlueStacks if not running,
- `manual`: do not manage lifecycle; only connect if available.

Recommended v1 default:

- `require_running`

Reason:

- starting multiple BlueStacks instances at once can be slow and resource-heavy,
- the current automation already assumes a stable emulator/session boundary,
- we should prove lane iteration before adding lifecycle complexity.

## 16. Multi-Game Extension Model

The orchestrator model should be game-agnostic.

Game modules should provide a common adapter contract:

```text
GameAdapter
  validate_target(...)
  prepare_target(...)
  run_routine(...)
  summarize_result(...)
```

PNC adapter:

- wraps existing `ApplicationRunner`,
- resolves PNC account and castle refs,
- calls existing `run`, `build`, `send-mail`, `run-mail-schedules`, etc.

Future game adapters:

- may use Airtest/Appium/custom vision,
- should still run under the same instance-lane lock,
- should not require changes to the external scheduler.

## 17. Implementation Phases

### Phase 1: Stabilize Existing Config

- Align `config/accounts.yaml` with actual BlueStacks display names.
- Keep `config/castle_targets.yaml` account ids valid against configured accounts.
- Keep `config/castles.yaml` as local roster cache.
- Fix stale `pnc_automation.cli` references or add a compatibility alias.
- Validate `load_app_config("config/accounts.yaml")` after each config change.

### Phase 2: Add Bot Target Models

- Add typed models for `bot_targets.yaml`.
- Validate:
  - unique instance ids,
  - known BlueStacks display names,
  - known PNC account ids,
  - known castle refs,
  - known routine ids,
  - no duplicate target identity inside one instance.
- Keep validation fail-fast and DRY with existing config helpers.

### Phase 3: Add Routine Registry

- Add typed models for `bot_routines.yaml`.
- Support initial PNC routine kinds:
  - `script`,
  - `build`,
  - `run-mail-schedules`.
- Compile routines to existing `ApplicationRunner` calls.
- Do not add a second task language.

### Phase 4: Add Instance Locking

- Add a small lock-store abstraction.
- Lock per BlueStacks instance display name or stable instance id.
- Include stale lock detection.
- Add offline tests for lock acquire/release/fail-stale behavior.

### Phase 5: Add `run-target`

- Resolve one game/account/castle/routine.
- Run one PNC routine through existing runtime.
- Return a JSON summary.
- Add tests using fake runners and fake adapters.

### Phase 6: Add `run-instance`

- Resolve one instance lane.
- Iterate configured targets in authored order.
- Respect optional due filters.
- Stop or continue on failure according to explicit policy.
- Return a JSON summary.

### Phase 7: External Scheduler Prototype

- Install/configure the selected external scheduler.
- Add one job for one safe lane, such as `testing`.
- Run `list-bot-targets`.
- Run one dry-run target.
- Run one low-risk real routine.
- Add the remaining lanes gradually.

### Phase 8: Parallel Lane Validation

- Start with global concurrency 2.
- Run two known independent BlueStacks lanes.
- Inspect artifacts and logs.
- Increase to 3, then 6 only if CPU/RAM/ADB behavior remains stable.

## 18. Testing Strategy

Offline tests:

- bot target config loader,
- routine registry loader,
- instance/routine validation,
- run-target command argument parsing,
- run-instance iteration order,
- lock-store behavior,
- adapter dispatch into fake PNC runner.

Existing tests:

- keep running `python -m unittest discover -s tests` for Python changes,
- use `py -3.13` if the Windows `python` shim is still active.

Live validation:

- one lane with one castle,
- one lane with multiple castles,
- two lanes in parallel,
- all configured lanes after resource tuning.

## 19. Non-Goals

V1 should not add:

- a C++ scheduler daemon,
- a Windows service for interactive BlueStacks automation,
- a custom dashboard,
- arbitrary shell-command jobs inside repo config,
- duplicated scheduling state that competes with the external scheduler,
- C++ ADB or BlueStacks control,
- cross-machine worker orchestration before local six-lane operation is stable,
- new game adapters before PNC lane orchestration works.

## 20. Open Questions

1. Which external scheduler should be used for v1: Cronicle, Windows Task Scheduler, or another tool?
2. Should the repo include example Cronicle job definitions, or only document commands?
3. Should `run-instance` continue after one castle routine fails, or stop the lane immediately?
4. Should `main` remain current-session only, or should it get real login credentials in `accounts.yaml`?
5. Should BlueStacks lifecycle start/stop be part of v1, or require instances to already be running?
6. How many lanes can this machine run reliably before BlueStacks/ADB/OCR timing becomes unstable?

## 21. Recommended Defaults

- External scheduler owns timing, logs, retries, and dashboard.
- Python owns all emulator/game-specific orchestration.
- One scheduler job per BlueStacks instance.
- One runner lock per BlueStacks instance.
- Start with `require_running` lifecycle policy.
- Start with global concurrency 2.
- Run castle routines sequentially inside each instance.
- Preserve `rotation:` as a cycle filter model, not as a replacement for the external scheduler.
- Keep PNC run scripts as the canonical one-shot workflow format.
- Delay multi-game abstractions until the PNC instance runner shape is proven.

