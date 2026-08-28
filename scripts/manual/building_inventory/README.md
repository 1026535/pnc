# Home City Building Inventory

`home_city_buildings.txt` is the readable classification report. It separates
upgradeable buildings, non-upgradeable catalog buildings, and live-observed
landmarks that are not automation targets.

`upgradeable_buildings.txt` is a valid ordered input for the direct upgrade task:

```powershell
py -m pnc_automation.app.entrypoints.cli build `
  --account testing `
  --priority-file scripts/manual/building_inventory/upgradeable_buildings.txt
```

One invocation upgrades the first eligible target. It does not upgrade every
line. A complete mutation sweep must invoke one exact id at a time and retain the
normal resource, builder, prerequisite, and no-premium-action guards.

`constructable_buildings.txt` is the safe target set for construction testing.
The construction command accepts one exact id:

```powershell
py -m pnc_automation.app.entrypoints.cli construct `
  --account testing `
  --building farm
```

The files are checked against the canonical catalog by offline tests so catalog
changes cannot silently leave the live-test lists stale.

`phase1_upgrade_entry_results.txt` records the latest safe live inspection.
Rerun a bounded inspection without pressing Upgrade with:

```powershell
py tools/inspect_building_upgrade_entries.py `
  --account testing `
  --targets castle,wall,institute,warehouse
```

`progression_unlock_candidates.txt` preserves the additional Phase 2 targets
that are level- or tutorial-gated but are not normal construction-task targets.
It uses canonical ids (`watchtower` and plural `*_barracks`) and must not be
passed to `construct` until their distinct unlock flows are implemented.
