# Manual Build Batches

These files define ordered building-upgrade batches for the direct `build` CLI command.

Use one building id per line. Blank lines and `#` comments are ignored.

Example:

```text
institute
warehouse
```

Recommended usage from the repo root:

```powershell
py -3 -m pnc_automation.cli build `
  --account account_a `
  --config config/accounts.yaml `
  --kingdom K230 `
  --castle-name Main `
  --priority-file scripts/manual/build_batches/institute_then_warehouse.txt
```

This is the canonical manual building-upgrade path. Do not add one YAML run script per building target or per upgrade batch.
