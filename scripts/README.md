# Run Scripts

This folder contains authored automation runbooks grouped by intent.

## Folders

- `routines/`: repeatable operational scripts intended for recurring execution, including scheduler-driven runs.
- `manual/`: one-off or operator-invoked scripts for maintenance, recovery, or ad hoc actions.
- `smoke/`: narrow validation scripts used to confirm core automation paths still work end-to-end.

## Guidance

- Keep scripts high level and task-oriented.
- Prefer composing existing canonical tasks instead of inventing low-level tap sequences in YAML.
- Add new scripts to the bucket that matches how they are meant to be used, not the feature area they touch.
- When a task needs an explicit castle target, use `castle_ref` and define the alias in `config/castle_targets.yaml`.
- For ad hoc building upgrades, prefer the direct `build` CLI entry point with `--priority` or `--priority-file` instead of creating one YAML wrapper per building target or upgrade batch.
- Reusable building-upgrade batches belong under `scripts/manual/build_batches/` as ordered building-id files, not as duplicated multi-step run scripts.
