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

The canonical daily routine is castle-agnostic. Bind it to ordered account-scoped aliases at invocation time:

```powershell
py -m pnc_automation.app.entrypoints.cli run --account testing --script scripts/routines/daily_castle_maintenance.yaml --castle-ref main --castle-ref hopeful_npc_k323
py -m pnc_automation.app.entrypoints.cli run --account serious_stuff --script scripts/routines/daily_castle_maintenance.yaml --castle-ref main
```

`tools/run_daily_maintenance.ps1` runs this initial three-castle selection and is the command intended for a 2:00 AM Windows Task Scheduler trigger. Configure the scheduled task so it does not start a second copy while the previous run remains active.

The unattended routine currently contains only building upgrade with speedups disabled. Research, purchases, Gem, Saurgem, Gear, gathering, Campaign, Arena, and troop training remain excluded until each feature passes the promotion gate.

For every new daily feature:

1. Add deterministic offline task and runner coverage.
2. Add a single-feature script under `scripts/smoke/`.
3. Run that feature alone on the currently active `testing` castle:

   ```powershell
   $env:PNC_RUN_LIVE_DAILY_TASK_SMOKE="1"
   py -m unittest tests.test_live_daily_task_smoke
   ```

4. Inspect the generated screenshots and logs under `artifacts/`.
5. Convert live failures into offline regressions when practical.
6. Add the task to `daily_castle_maintenance.yaml` only after the live smoke proves a safe success or intentional no-op.
