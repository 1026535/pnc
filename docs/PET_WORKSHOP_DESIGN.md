# Pet Workshop design

Canonical implementation reference for the Pet Workshop (merge-board) feature.
Status is tracked per section; the reviewed plans under `reviewed_plans/` own
requirements and sequencing.

## Owner map

| Concern | Owner | Status |
|---|---|---|
| Catalog data + typed loader | `pnc_automation/app/pnc/pet_workshop_catalog.py` + `pnc_automation/app/pnc/data/pet_workshop/catalog.json` | Implemented (PW01 catalog slice, 2026-09-16) |
| Shared state/view/intent models, policy + interface contracts | `pnc_automation/app/pnc/domain/pet_workshop.py` | Implemented (PW01 shared-state slice, 2026-09-16) |
| Observation integration (`ObservationAdditions.workshop`, both publishers) | `Observation`, `observation_builder.py`, `navigation_perception.py`, `observation_provenance.py` | Implemented (PW01 shared-state slice, 2026-09-16) |
| Feature parser + measured controls | `pnc_automation/app/pnc/vision/` (planned) | Pending PW02 |
| Solver, policy, `plan_next`, `validate_intent` | `pnc_automation/app/automation/pet_workshop/` | Implemented (PW03/PW04 solver slice, 2026-09-16) |
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

## Shared models and interfaces

`pnc_automation/app/pnc/domain/pet_workshop.py` owns the canonical immutable
types every later packet exchanges. All of them are frozen/slotted dataclasses
or `StrEnum`s, are constructed without runtime I/O, and fail fast on malformed
authored data while keeping unread facts representable.

### State, view, and observation

- `WorkshopState` is the coordinate-free logical reading of one frame:
  `board` (the catalog's `WorkshopBoardLayout`, which also owns the
  `cell_id = (row - 1) * columns + column` formula), `surface`
  (`WorkshopSurfaceKind`: board/item detail/order detail/help, plus
  `EXCLUDED_MODAL` and `UNKNOWN` so excluded surfaces stay representable),
  `cells`, `energy`, `production_mode`, `workshop_level`/`workshop_exp`,
  `selection`, and `order_survey`. `cells` holds one entry per observed
  cell; `observed_cell_ids`/`unobserved_cell_ids` report coverage, and a
  partial frame is never resized into a fictitious complete board. State
  construction rejects duplicate or out-of-board cells, cell ids that
  disagree with their row/column, and selections outside the board.
- `WorkshopCell` keeps `access` (`USABLE`/`LOCKED`/`UNKNOWN`) independent
  from `occupancy` (`EMPTY`/`OCCUPIED`/`UNKNOWN`). `item_id` may be `None`
  on an occupied cell (piece seen, identity unread); `item_status` covers
  `NORMAL`, `INACTIVE` (grey activation target), `BUBBLE`, `FEED_LOCKED`
  (producer awaiting its catalog feed ingredient), and `UNKNOWN`.
  An unread addressed cell defaults to unknown access and occupancy with no
  item facts; only confirmed occupied cells require an explicit item status.
  `cooldown` is the tri-state visible marker only — no deadline is inferred.
- `WorkshopSelection` distinguishes `SELECTED` + cell id, `NONE`, and
  `UNKNOWN`; a repeated tap on a selected producer produces, so the planner
  must not conflate unknown with known-none.
- `WorkshopEnergy` holds `current`/`capacity` readings; `None` is unknown,
  `0` is the reliable stop signal (`is_zero`), and over-cap readings stay
  valid (the 200 cap is current authored data, not a schema limit).
- `WorkshopView` carries measured geometry: `cell_bounds` per observed cell,
  per-order `WorkshopOrderView` (portrait bounds open the detail, submit
  bounds is the ready control), the safe detail/close/recycle/confirmation
  control bounds, `image_size`, and the publication provenance
  (`frame_ref`, `source_screen`, `source_layout_id`) stamped by
  `observation_provenance.bind_workshop_observation`. No offscreen click
  point is inferred.
- `WorkshopObservation` composes state + view and rejects view geometry that
  names cells or order refs the state never surveyed.

### Orders

`WorkshopOrder` is an observation-local object: `order_ref` identifies the
card within one survey only (never a server id), `requirements` maps item id
to required pieces and preserves duplicate quantities (`{item: 2}` is
meaningful), and orders of any size stay representable — the exact-two-piece
rule is Plan 02 policy, not a model invariant. `completeness` reuses
`RowRecognitionStatus` so clipped/partial cards keep their data; `ready`
(`True`/`False`/`None`) records the observed ready control; `rewards` carry
`WorkshopOrderReward` entries whose `category` covers the agreed reward
families plus `OTHER`/`UNKNOWN` with a raw `label`. `WorkshopOrderSurvey`
groups the surveyed cards with `coverage` (complete/partial/unknown) and
`freshness` (current/stale/unknown) so a stale survey is never treated as
confirmed.

### Intents, decision, and validation contract

Ten tagged intent dataclasses share the `WorkshopIntent` base and carry only
logical targets (cell ids, order refs, expected item ids) — never gestures or
coordinates:

- `WorkshopSelectIntent(cell_id)` — select a cell, typically a producer
  before production.
- `WorkshopProduceIntent(cell_id, producer_item_id)` — finite and ordinary
  generators alike produce through this intent.
- `WorkshopMergeIntent(source_cell_id, target_cell_id, item_id)` — ordinary
  merges and ordinary producer upgrades; the successor comes from the
  catalog.
- `WorkshopActivateIntent(source_cell_id, target_cell_id, item_id)` — a
  matching normal piece onto an inactive one; distinct from Merge because
  consumption and preconditions differ.
- `WorkshopFeedIntent(food_cell_id, producer_cell_id, food_item_id)` — the
  exact catalog ingredient onto a feed-locked producer.
- `WorkshopRecycleIntent(cell_id, item_id)` — one piece through the
  garbage-bin control.
- `WorkshopSubmitOrderIntent(order_ref)` — the surveyed card by local ref.
- `WorkshopInspectIntent(need, cell_id?, order_ref?)` — a logical
  information need (`ORDER_CONTENTS`, `CELL_STATE`, `ORDER_SURVEY`,
  `BOARD`); Plan 03 owns the navigation that satisfies it.
- `WorkshopWaitIntent(max_wait_ms)` — a bounded wait; never open-ended.
- `WorkshopStopIntent(reason)` — `WorkshopStopReason` covers
  `ZERO_ENERGY`, `BOARD_BLOCKED`, `NO_ELIGIBLE_GOAL`, `COOLDOWN_TIMEOUT`,
  `EXCLUDED_SURFACE`, `UNRESOLVED_STATE`.

`WorkshopDecision` pairs the intent with a human-readable `reason`,
`goal_order_ref`, and the `missing_quantities`/`protected_quantities`
reservation diagnostics; together with the intent's typed targets these are
the facts a fresh-state `validate_intent` re-checks. `WorkshopPolicy` fixes
the typed policy knobs (`order_piece_total`, `reward_priority`,
`recyclable_item_ids`, `max_cooldown_wait_ms`) whose defaults and evaluation
belong to Plan 02. `WorkshopIntentValidation` is the result contract:
`LEGAL`, `ILLEGAL`, or `UNCERTAIN` when a required fact was never observed.

The pure interface signatures are fixed as callable `Protocol`s so both free
functions and classes satisfy them, with no implementation shipped in PW01:

- `WorkshopPlanNext`: `plan_next(state, catalog, policy) -> WorkshopDecision`
  (PW04 one-step planner).
- `WorkshopValidateIntent`:
  `validate_intent(state, intent, catalog, policy) -> WorkshopIntentValidation`
  (PW03 legal-action check, reused verbatim for pre-execution revalidation).

### Data flow

```
screenshot -> ObservationBuilder/NavigationPerception
  -> (PW02 feature parser produces ObservationAdditions.workshop)
  -> bind_workshop_observation stamps view frame_ref/screen/layout
  -> Observation.workshop
  -> plan_next(state, catalog, policy) -> WorkshopDecision
  -> validate_intent(state, intent, catalog, policy) on a fresh state
  -> Plan 03 resolves intent targets against the paired WorkshopView
```

`Observation.workshop` is optional. `ObservationBuilder._publish` and
`NavigationPerception.build` bind it through the same provenance owner as the
existing typed facts; `_merge_observation_additions` preserves it across the
guard/content merge; an unresolved or unknown screen decision drops it along
with all other content (fail-closed). Recognition uncertainty stays inside
the models — malformed frames never raise as catalog errors.

### Extension method

New logical facts extend `pet_workshop.py` in place; new measured geometry
extends `WorkshopView` and is bound by the same provenance owner. New intent
families add a `WorkshopIntentKind` member and a dataclass carrying logical
targets only. Never add server order ids, spawn predictions, exact cooldown
deadlines, or remaining-use counts to the shared contract; never duplicate
catalog knowledge (successor graphs, drop weights, feed ingredients) inside
the state model — read it through `PetWorkshopCatalog`.

## Recognition — pending

Owned by PW02: one feature parser under `app/pnc/vision/` producing
`ObservationAdditions.workshop`, measured controls bound to
`observation_provenance`, publication through `ObservationBuilder`
and `NavigationPerception`.

## Solver and policy

Owned by Plan 02 (PW03/PW04): `pnc_automation/app/automation/pet_workshop/`
implements the pure offline solver. No module in this package performs
emulator, image, filesystem, clock or network I/O; authored state
transitions exist only in `tests/support/pnc/pet_workshop_solver.py`.

- `board.py` — `BoardFacts` partitions observed cells (normal, inactive,
  feed-locked and bubble pieces, usable-empty cells, unread pieces) and
  derives `board_full` as a tri-state; `MergeChains` indexes the catalog
  successor graph (successor, ancestors, closure, binary unit values).
- `policy.py` — `default_policy()` and `assess_order`: the two-total-piece
  admission rule, reward-category ranking from `policy.reward_priority`,
  ranking-blocked marking for unread reward quantities, and the restricted
  recycling allowlist.
- `effort.py` — `allocate_goal` owns multiset reservations and advisory effort
  together (exact stock, feed-unlockable pieces, lower-tier intermediates,
  activation pairs; higher tiers are never split backwards).
  `useful_units_per_draw` provides the catalog-weighted production proxy.
  The allocation flags `conservative` when one producer serves two demands
  and reports unknown finite capacity as uncertainty only.
  Exact requirements are reserved together before recipes consume stock.
  The free recipe traversal can build a Normal partner before activating an
  inactive piece; it records original consumed quantities and restores an
  unsuccessful branch without borrowing the same piece twice.
  Feed ingredients and producer construction consume the same remaining
  pool as order demands. The selected recipe supplies production and
  auxiliary targets to `rules.py`; no caller independently rediscovers them
  from raw board counts. Thus an order's reserved Food 3 cannot double as
  the Trap's feed, and a lower ready order cannot take the allocated feed.
  Reachable construction expands through catalog producer chains with a
  dependency-cycle guard. New finite copies receive their catalog capacity;
  replacements require fresh stock or separately priced upstream production.
  Existing finite copies retain unknown remaining capacity. If only the
  first construction is reachable, useful progress remains available but
  the total effort is unknown. Expected draws are an additive advisory
  approximation; no stochastic simulator or future inventory is created.
- `goals.py` — `GoalSelection`/`select_goals`: survey gating,
  category-first then zero-cost-before-positive-cost ranking with
  policy-ordered secondary rewards, known estimates ahead of absent or
  uncertain ones (which tie-break on primary reward quantity), and
  `inspect_order_ref` for any contender whose unread facts — a clipped
  card, an UNKNOWN reward category, a missing primary or an undecidable
  secondary count — could still change the applicable ranking.
  When an unfinished primary permits a ready secondary submission, that
  secondary selection uses the same reward inspection and surplus-stock
  predicates rather than treating unread quantities as zero.
- `rules.py` — `goal_context` plus the reservation verdicts for merge,
  activate, feed, finite production and submit: protected exact/intermediate
  pieces may only be consumed when the action advances the serving demand.
  A finite generator reserved as an exact order ingredient cannot produce
  if its exhaustion could remove the required quantity; a reserved unlimited
  generator remains usable.
- `validation.py` — the canonical `validate_intent`, used by the planner
  and reused verbatim for pre-execution revalidation; `UNCERTAIN` whenever a
  required fact was never observed.
- `planner.py` — `plan_next` returns exactly one `WorkshopDecision`:
  terminal evidence first (zero energy, excluded surface, auto-fusion
  production mode), then survey/inspection needs, ready order submissions,
  free progress (merges, activations, feeds), full-board recovery ending in
  one allowlisted recycle, production (select/produce with bounded cooldown
  waits), and finally bounded inspection or a typed stop. Every returned
  intent is canonically legal on the state that produced it — missing
  relevant facts (production mode, cell access/occupancy) yield a targeted
  inspection, not a mutation `validate_intent` would reject.

Every `WorkshopDecision` is a proposal: intents carry logical targets only,
the planner never touches game state, and execution is a separate Plan 03
step that re-validates the intent on a fresh observation through the same
`validate_intent` before any gesture.

## Execution — pending

Owned by Plan 03: gestures, mutation authority, entry points and Daily
Maintenance integration.
