# Run Scripts

This folder contains authored automation runbooks grouped by intent.

## Folders

- `routines/`: repeatable operational scripts intended for recurring execution, including scheduler-driven runs.
- `manual/`: one-off or operator-invoked scripts for maintenance, recovery, or ad hoc actions.
- `smoke/`: narrow validation scripts used to confirm core automation paths still work end-to-end.

## Guidance

- Keep scripts high level and task-oriented.
- Promote a feature into an unattended routine only after focused offline tests and one opt-in live task smoke pass.
- Prefer composing existing canonical tasks instead of inventing low-level tap sequences in YAML.
- Add new scripts to the bucket that matches how they are meant to be used, not the feature area they touch.
- When one task needs an explicit castle target, use `castle_ref` and define the alias in `config/castle_targets.yaml`.
- When one shared workflow should run for several account-scoped castle aliases, use one repeat block with `castle_refs` plus nested `steps`. The nested steps must stay ordinary task steps and must not declare their own `castle_ref`.
- For ad hoc building upgrades, prefer the direct `build` CLI entry point with `--priority` or `--priority-file` instead of creating one YAML wrapper per building target or upgrade batch.
- For ad hoc mail sends, prefer the direct `send-mail` CLI entry point instead of creating one-off YAML wrappers.
- For authored recurring mail, define reusable payloads in `config/mail_definitions.yaml`, schedules in `config/mail_schedules.yaml`, and invoke `run-mail-schedules` hourly from the external scheduler.
- Reusable building-upgrade batches belong under `scripts/manual/build_batches/` as ordered building-id files, not as duplicated multi-step run scripts.
- The catalog-synchronized Home City classification and reusable construction/upgrade target lists live under `scripts/manual/building_inventory/`.

Construct one exact missing building with `building_construct` (or the direct `construct --building ...` CLI command):

```yaml
steps:
  - task: building_construct
    params:
      building: farm
```

When resources are sufficient, construction starts directly without a resource popup. An unmet-resource popup is handled only as the insufficient-resources failure branch; this task never spends premium currency or uses speedups.

## Multi-Castle Pattern

Use repeat blocks when you want to finish one full workflow for one castle before moving to the next:

```yaml
name: daily_castle_maintenance

steps:
  - task: ensure_game_running
  - task: login
  - castle_refs: [main, farm]
    steps:
      - task: building_upgrade
        params:
          priority: [castle, wall, institute]
          allow_speedups: false
      - task: research
        params:
          priority: [economy, development]
```

This expands during script preparation into ordinary single-target prepared steps. Runtime tasks still execute against one concrete castle at a time.

## Nightly Daily Maintenance

NPC 2 (`mega_old_acc/npc_2`, K157) and free cookies
(`serious_stuff/free_cookies`, K226) are **canary-only**, never nightly targets.
Local/example Daily configs list all seven screenshot-confirmed `testing` castles
as automatic targets; `3xx_spies` is excluded.

`automatic_runs_enabled: false` blocks even claim-only runs before connection.
Finish **all** canary evaluations first, then enable only validated features.
NPC 2 must pass; cookies may have an explicitly approved, observed applicability
skip. Insufficient funds fails that feature without being a software defect.
Retest successful canaries after relevant changes, not every day.

Game reset is `game_reset_hour_utc: 0`, separate from 02:00 Toronto maintenance.
The screenshot aliases do not prove login ownership: resolve the testing/3xx
login-cache mismatch before live preparation. K303's obscured name remains unverified.

Use TDD: failing offline feature tests first, incremental implementation, then bounded
live proof. Live proof is iterative: a selector/OCR/navigation/reconciliation failure
is inspected, fixed, covered by a regression test when reproducible, and rerun through
the smallest bounded probe. It is not a completed feature until the expected
postcondition is observed, an approved applicability skip is recorded, or a precise
external/user-input blocker is documented. `tests/test_daily_canaries.py` covers the
paired contracts and release decision, not game-action completion. The implementation
plan records remaining gates.

Daily maintenance is an application-level coordinator, not an authored task YAML. Copy
`config/daily_maintenance.example.yaml` to the ignored local
`config/daily_maintenance.yaml` only after its castle aliases have been reviewed against
the canonical roster cache.

```powershell
tools/run_daily_maintenance.ps1 -AcknowledgementPath C:\secure\daily-acknowledgements.json
```

The acknowledgement file is a JSON array. Every entry binds an account, castle alias,
capability, America/Toronto date, maximum mutation count, and maximum diamond spend.
The wrapper validates `Eastern Standard Time`, holds a process mutex, and propagates the
coordinator exit code. Claim-only operation uses capability `claim_completed` and the
configured `max_claims` value. Stale, missing, broad, or duplicate acknowledgements fail
before ADB connection.

No action capability is promoted yet. Any non-empty production `enabled_capabilities`
list fails before ADB. Canary policies are separate and do not enable production.
The old building-upgrade routine was removed because it contradicted the
Daily plan's exclusions.

The first connected resource-item canary has a read-only inspection command:

```powershell
py tools/run_resource_item_canary.py --role free_cookies
```

It verifies the selected canary and scans existing Resource inventory without using
an item. `--execute --acknowledgement '<JSON>'` requires exact authority for that
castle, current Toronto date, `use_resource_item`, one mutation and zero diamonds.
If a prior authorized dispatch is unresolved, use
`--reconcile-only --game-reset-id <existing-reset-id>`; this mode requires an
existing unresolved journal and cannot create a new mutation intent or press Use.
The mutation journal is shared by UTC game-reset identity across callers; rerunning
a committed action does not produce a new live pass. Inspection alone is not a pass.
Canary evidence is persisted below the configured artifact root under
`canary-evidence/<quest>/<role>/result.json`. The evaluator reuses a stored result
only when its feature revision still matches; a changed feature revision creates a
missing canary cell and requires a new paired evaluation. Persisted evidence never
enables automatic runs by itself.

The Hero Hall canary is now implemented as a five-single, zero-diamond increment:

```powershell
py tools/run_hero_hall_canary.py --role free_cookies
```

The default command is read-only. An acknowledged execution sends at most one fresh
free 1x recruit per invocation, journals it exactly once, and reports the five-minute
cooldown so later invocations can resume without replaying prior singles:
`--execute --acknowledgement '<JSON>'`. The canary remains unpromoted until both NPC 2
and free cookies have complete postcondition evidence. Hero Hall entry is through the
observed Home City Hero Hall building; the Hero Hall canary does not click its Daily
`Go` row. Daily is used only for the final read-only completion check.

The connected runtime recognizes the exact `New version detected. Tap Confirm to
update.` modal from any canonical workflow. It presses that modal's typed Confirm
control once, allows up to ten minutes for installation/restart, relaunches P&C once
if Android Home appears, and resumes only after typed Home is observed. Other
confidently detected transient offers (including generic upper-right-X offers,
VIP daily/login notices, and account-switch/game-open offers) are recovered across
workflow boundaries by the shared observed-action executor. Recovery may use only
`PNC_POPUP_CLOSE_BUTTON` or `PNC_VIP_DAILY_RESET_CLOSE_BUTTON`, requires a fresh
frame fingerprint, taps each fingerprint at most once, and stops after six distinct
popups. Missing or unrecognized popup controls fail with captured diagnostics;
Android Back is never used as a generic-popup fallback. Task-owned confirm, claim,
purchase, and mutation controls remain with their task.

If an exact update interrupts an already-dispatched task action, that task fails as
ambiguous instead of replaying the action; journaled Daily operations reconcile from
a freshly reopened Daily or Resource screen. Transient popup dismissal does not
consume task replan/retry budgets, and closing a transient popup never replays the
action that preceded it.

For every new daily feature:

1. Add deterministic offline task and runner coverage.
2. Add a single-feature script under `scripts/smoke/`.
3. Run that feature alone with an explicit account, castle, script, and acknowledgement:

   ```powershell
   $env:PNC_RUN_LIVE_DAILY_TASK_SMOKE="1"
   $env:PNC_LIVE_SMOKE_ACCOUNT="mega_old_acc"
   $env:PNC_LIVE_DAILY_TASK_SMOKE_CASTLE_REF="reviewed_alias"
   $env:PNC_LIVE_DAILY_TASK_SMOKE_SCRIPT="scripts/smoke/daily/feature.yaml"
   $env:PNC_LIVE_DAILY_TASK_SMOKE_ACKNOWLEDGEMENT='{"account_id":"mega_old_acc","castle_ref":"reviewed_alias","capability":"feature","maintenance_date":"YYYY-MM-DD","max_mutations":1,"max_diamond_spend":0}'
   py -m unittest tests.test_live_daily_task_smoke
   ```

4. Inspect the generated screenshots and logs under `artifacts/`.
5. Convert live failures into offline regressions when practical.
6. Add the capability to the typed local Daily config only after its promotion gate passes.
