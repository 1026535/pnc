# Pet Workshop design

Canonical implementation reference for the Pet Workshop (merge-board) feature.
Status is tracked per section; the reviewed plans under `reviewed_plans/` own
requirements and sequencing.

## Owner map

| Concern | Owner | Status |
|---|---|---|
| Catalog data + typed loader | `pnc_automation/app/pnc/pet_workshop_catalog.py` + `pnc_automation/app/pnc/data/pet_workshop/catalog.json` | Implemented (PW01 catalog slice, 2026-09-16) |
| Shared state/view/intent models | `pnc_automation/app/pnc/domain/pet_workshop.py` (planned) | Pending next PW01 slice |
| Observation integration (`ObservationAdditions.workshop`, both publishers) | existing observation owners | Pending next PW01 slice |
| Feature parser + measured controls | `pnc_automation/app/pnc/vision/` (planned) | Pending PW02 |
| Solver, policy, `plan_next`, `validate_intent` | `pnc_automation/app/automation/pet_workshop/` (planned) | Pending Plan 02 |
| Execution, mutation receipts, entry points, Daily Maintenance | existing task/engine owners | Pending Plan 03 |

Do not copy catalog knowledge, recipe logic, or recognition rules into a
second owner. Later packets extend this document in place.

## Catalog and provenance

The catalog is the single source of Pet Workshop game data. It is authored
from the decoded PNC **5.0.203 / version code 233** client tables
(`H-合成活动` sheet family) and packaged as tracked JSON at
`pnc_automation/app/pnc/data/pet_workshop/catalog.json`. Each source table's
SHA-256 (packed `.bin` and decoded Lua), decode method, build, and row count
is recorded in the document's `provenance` section; the upstream manifest
lives under the ignored evidence root `reports/pet-workshop/client-tables-5.0.203/`.

Authoring rules applied once, offline:

- Sparse rows inherit `__default_values` via the client's `setmetatable`
  `__index` mechanism; inherited values are resolved into plain data.
- Shared `__rt_N` subtables (recycle rewards) are resolved as data.
- `0` id sentinels (`composeItemId`, `changeItemId`, `unlockItemId`) become
  `null`; `a_b|...` reward lists become `{item_id, count}` entries.
- `ComposeActOrderForm` (1,263 server/hidden order forms) is intentionally
  excluded; active orders are observed at runtime.
- `ComposeActWarehouse` is decoded but not modeled (storage expansion is
  outside this release).

### Schema and invariants

`load_pet_workshop_catalog()` validates on construction:

- Unique ids across items, producers, drop groups, grid cells, and levels.
  Duplicate JSON object keys fail before parsing can silently discard a value.
- Required references resolve: merge successors, producer item/feed/transform
  ids, drop entries, cell seeds, and level rewards must be catalog items;
  producer `group_id` must be a defined drop group. Recycle-reward and
  activity energy item ids reference the client's global item table and stay
  external.
- Positive required quantities (tiers, reward counts, energy capacity/cost/
  regen interval); non-negative authored counts, costs, cooldowns, and drop
  weights. Zero-weight drop entries are real authored data and are preserved;
  each group's total must be positive.
- Grid positions must be unique and inside the declared 7 x 9 board
  (`cell id = (row - 1) * columns + column`).
  Authored `randomItems` candidates are not current occupancy; only observations
  populate the live logical board.
- The merge-successor graph must be acyclic.

Explicitly **not** enforced: fixed catalog length (114 is the current seed,
not a schema limit), drop groups summing to 1000 (group 66 legitimately sums
to 500; probabilities normalize by the actual sum), per-generator minimum
Workshop levels (none exists in the client table), hidden server order state,
and user-policy exclusions — valid items such as the Omni Card or AP/Diamond
pieces remain representable.

### API summary

- `load_pet_workshop_catalog(path=None) -> PetWorkshopCatalog` — loads the
  packaged JSON (default path inside the installed package; `path` override
  for tests) and returns the validated immutable catalog. Raises
  `PetWorkshopCatalogError` (a `ValueError`) on malformed data.
- `PetWorkshopCatalog`: `items`, `producers`, `drop_groups`, `cells`,
  `levels` tuples; `item`/`require_item`, `producer_for`, `drop_group`,
  `cell`, `level` lookups; `board` (`WorkshopBoardLayout`), `activity`
  (`WorkshopActivityConfig`), `provenance` (`CatalogProvenance`).
- `DropGroup.probability_of(item_id)` — weight normalized by the group's
  actual total.
- `WorkshopBoardLayout.cell_id(row, column)` / `contains_position` /
  `contains_cell_id` — coordinate validation shared with the board models.

### Extension method

New client builds or newly needed fields extend the same owner: update the
authored JSON from the matching decoded tables (resolving defaults the same
way), extend the typed model/loader in `pet_workshop_catalog.py`, and keep
provenance honest (build, hashes, observation date). Do not add a runtime Lua
interpreter, a second catalog, or reads of the ignored extraction root.

## Shared models and observation — pending

Owned by the next PW01 slice per the Plan 01 interface contract
(`WorkshopState`, `WorkshopView`, `WorkshopObservation`, selection and order
models, shared intent variants). This section intentionally stays empty until
those types exist; do not document non-existent APIs.

## Recognition — pending

Owned by PW02: one feature parser under `app/pnc/vision/`, measured controls
bound to `observation_provenance`, publication through `ObservationBuilder`
and `NavigationPerception`.

## Solver and execution — pending

Owned by Plan 02 (`plan_next`, `validate_intent`, `WorkshopPolicy`,
`WorkshopDecision`) and Plan 03 (gestures, mutation authority, entry points,
Daily Maintenance).
