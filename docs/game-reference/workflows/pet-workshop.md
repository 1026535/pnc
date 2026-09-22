# Pet Workshop catalog tables and progression

## Evidence and limits

The table facts below come from the decoded client tables of packaged PNC
**5.0.203 / version code 233** (the `H-合成活动` sheet family), recovered
offline 2026-09-16. Each table's packed/decoded SHA-256 and decode method
(bytewise XOR `0x2c`, strict UTF-8, no code executed) is recorded in the
packaged catalog's `provenance` section and in
`reports/pet-workshop/client-tables-5.0.203/manifest.json` under the ignored
evidence root. Progression findings cite Lua paths under the recovered
gameplay root (`apk-exploration/gameplay-lua/`); see
[provenance](../PROVENANCE.md).

The prior live exploration ran build `5.2.80_5.0.204.235`, so packaged tables
are static evidence, not a guarantee of current server-delivered data. Active
orders and hidden/random order selection are server-driven and are observed
at runtime, not from these tables.

## Table structure and inheritance

**Client source verified:** every `ComposeAct*` table is a Lua literal whose
rows are sparse: missing fields resolve through `__default_values` via
`setmetatable` `__index`, and repeated subtables are shared `__rt_N` locals
referenced by name. `basedata` records `len`, `key`, and `excelName`. Catalog
authoring resolves both mechanisms into plain data; nothing executes Lua.

## Items, merges, and recycling — `ComposeActItemLevel` (+ `.en` names)

**Client source verified:** 114 item rows keyed by `id`; the English
localization supplies `itemName`/`itemTips` for all 114. Facts preserved per
item: `composeItemId` merge successor (0 = max level), `level` tier, `type`/
`subType`/`sort`/`getType`/`exp` raw fields, `itemIcon` sprite, `recovery`
flag, `recoveryReward`, and `unlockCost` (present on many mergeable pieces;
its consumer is unverified).

- `recoveryReward` shared tables `__rt_2`–`__rt_9` are counts 2–256 of
  energy-related item `44009010`, `type=9`. Fruit 5 (20105) and Statue 5
  (10205) map to `__rt_4` = count 8; **user-confirmed 2026-09-27** that the
  recycling receipt is +8 energy each, settling the earlier live-receipt
  caveat.
- Every producer item has `type=1`; ordinary mergeable pieces are `type=2`;
  the Omni Card (100001) is `type=0`. Producer-ness is defined by the worker
  table, not inferred from `type` — keep the raw field.
- Merge chains are acyclic in the seed and include generator families
  (Map/Tree/Clay/Bag), product families (Treasure/Statue/Fruit/Wood/Bowl/
  Food/Lighting/Fishing Tool/Sea Creature/Ocean Drifter/Animal), and usable
  pieces (Item Chest, AP, Diamond).

## Producers and drops — `ComposeActWorker`, `ComposeActWorkerItemGroup`

**Client source verified:** 20 worker records keyed by generator item id with
`itemGroupId`, `num`, `maxNum`, `cdTime` (ms), `changeItemId`,
`unlockItemId`, `type`, `assist`. 123 group rows form 20 drop groups keyed by
`groupId` with `itemId` + `rate` weights.

- Finite producers carry `maxNum`/`changeItemId`: Fishing Tool 9 (40209)
  transforms to 40206; Bowl 5 (30105) and Item Chest (60001) have `maxNum`
  with no transform (per tips, they disappear). Trap (50004) has
  `unlockItemId=31103`, consistent with `IsProductionNeedUnLock` reading that
  field as the feed/activation ingredient.
- Group weights are authored rates, not guaranteed percentages: most groups
  sum to 1000, but group 66 (Item Chest) sums to 500, and many groups contain
  `rate=0` entries. Consumers must normalize by the actual positive sum.
- No minimum Workshop-level field exists on worker records; do not invent a
  per-generator level gate.

## Board, levels, and energy — `ComposeActAreaGrid`, `ComposeActLevel`, `ComposeAct`

**Client source verified:** 63 area-grid rows (`pos`, `level`, `unlockType`,
`randomItems`) covering the observed 7 x 9 board (cell id `(row-1)*7+col`);
`unlockType` values 0/1/2 are raw codes and `level=0` marks no level gate.
21 level rows carry `exp`, `productivity`, and `composeActItemReward`
(`itemId_count|...`): level 2 grants Map 1, level 3 grants Tree 1 + Map 2,
level 10 grants Bag 1 + Clay 3 + Item Chest x3. The single `ComposeAct` row
carries energy facts: `itemId=44009010`, `maxProductivity=200`,
`productivityCost=1` per production, `productivityTime=300000` ms regen,
shared `cdTime=20000`/`cdCost=50`.

`randomItems` is retained as authored seed candidates, including three cells
with more than one candidate. It is not evidence that those pieces currently
occupy a cell. `MergeAdventureData:InitChessboard` copies the current server
`gridMap` entry into each cell; automation must obtain current occupancy from
its screenshot observation, not from the seed catalog.

**Inferred:** `productivity` on level rows is the level's energy value and
`unlockType` gates cells by level/progression; the exact unlock predicates
were not traced.

## Order progression

**Client source verified** (reviewed 2026-09-16; paths under the recovered
Lua root):

- Normal order display checks completed prerequisites, minimum Workshop
  level, and configured item-family presence:
  `uis/composeact/item/mergeadventureorderoperation.lua` `VerifyDisplayOrder`;
  `datas/mergeadventuredata.lua` `VerifyHasSubType`.
- Hidden orders appear when their targets are satisfied; random orders arrive
  as a server-selected id list: `VerifyNewOrder`, `GetRandomOrders`,
  `SetRandomOrders`; `commands/composeact/composeactcommand.lua` passes
  `serverData.randomOrderForm`. The server's random-order selector is
  unknown — survey visible orders, never synthesize them from the packaged
  `ComposeActOrderForm` (1,263 forms, intentionally not imported).

## Automation implications

- `pnc_automation/app/pnc/pet_workshop_catalog.py` is the canonical owner;
  the packaged JSON under `data/pet_workshop/` is the only runtime source.
- `pnc_automation/app/pnc/domain/pet_workshop.py` owns the canonical logical
  models (`WorkshopState`, `WorkshopView`, `WorkshopObservation`, orders,
  intents); `Observation.workshop` is the optional published field bound by
  the shared provenance owner. See the
  [canonical design](../../PET_WORKSHOP_DESIGN.md).
- `pnc_automation/app/automation/pet_workshop/` is the pure offline solver:
  `plan_next` returns one proposed `WorkshopDecision` (typed intent +
  diagnostics) and `validate_intent` checks it; neither performs I/O or
  mutates game state. Executed actions are a later packet's concern —
  execution re-validates the proposal against a fresh observation first.
- Catalog facts are game data, not policy: excluded mechanics (Omni Card,
  consumable AP/Diamond, storage) stay representable for recognition.
- Workshop level awards do not guarantee a usable producer on the current
  board; keep item tier, Workshop level, board access, and generator state
  distinct.
- A recoverable generator state (feedable, mergeable, transformable) is not
  an immediate stop; a visibly present order is not malformed because
  inferred level eligibility disagrees.

## September 17 native capture on another Workshop level

**Artifact-observed / live preflight observed:** the Main pass on selected
K157 / Sword NPC2 / C26 captured Workshop **Lv.6, EXP79/80, energy200/200**,
with a 7×9 board, printed cell gates 7–11 and no empty usable square visible.
Two visible order cards show different chest images and a pomegranate-like
fruit, with displayed Feed rewards 968 and 1634; the first also shows one
green EXP. These visual labels are not a decoded `WorkshopState` or confirmed
catalog item IDs. The current game build was not captured in this pass.

Provenance: corrected manifest
`C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-live-main/.local-data/devin-live-test/runs/main-evidence-20260917/turn-002/evidence.json`;
native board `20260917T045029Z_core_20260917T044156Z_9e838404_0039_tap_pet_workshop.png`
under `C:/Users/lebel/pnc/artifacts/2026-09-17/pet_workshop_evidence_20260917/`.
The lead visually checked this board and the selected-character frame.
Use this capture alongside the earlier level as recognition evidence.

Manor/Workshop routes remain unqualified: the baseline classified their
screens as UNKNOWN and the worker used coordinates from fresh captures.
Grass texture and an Inactive banner do not by themselves establish cell
status. Cooldown, feed-locked producer and exhaustion transitions remain
unproven. The book/badge-24 probe was outside its no-inventory-claims brief
and returned No slots available; its operation is unconfirmed and must not
be treated as a safe inspection control. No successful resource change was
observed. The capped energy reading alone is not proof of zero spending.

## September 18 live transition captures (main, Lv.7)

**Live-observed** on `bs-main-android` (exploratory coordinate taps; the
Workshop screen still classifies UNKNOWN). Artifact root:
`C:/Users/lebel/pnc/artifacts/2026-09-18/pet_workshop_sim_20260918/`.

- **Produce (verified):** tapping an already-selected manual producer sends
  `ComposeactSend.RequireProduce(posId)`; the response
  (`MERGE_UPDATE_ITEM_PRODUCE`) carries `originalPos` + `targetPos` — the
  server chooses the spawn cell. Captured: Clay 1 (item 30001, cell 56)
  produced Bowl 1 (30101) onto server-chosen cell 24 — matching drop group
  21's single positive entry — with energy −1 and a circular cooldown badge
  (`cdTime`) shown on the producer afterward.
- **Merge (verified):** dragging one piece onto an identical Normal piece
  produced the catalog successor at the target cell and emptied the source
  (Wood 1 + Wood 1 → Wood 2); no energy spent.
- **Recycle (verified):** with a piece selected, the detail-bar bin button
  opens a "Confirm to delete?" dialog (`ConfirmBoxPanelManager`, can be
  suppressed by a don't-ask-again preference); confirming sends
  `RequireOperate(gid, Recovery=1)` and removes the piece. Wood 1 granted no
  reward — consistent with `recoveryReward` absent on tiers 1–2. Observation
  popup-settling dismissed this dialog once; the confirm button must be
  tapped explicitly.
- **Selection (verified):** first tap selects (border + detail panel);
  tapping the selected piece again is the action path (`Use` when the item
  config carries `rewards`, else `RequireProduce` for non-Auto producers,
  gated by `status == Normal` and `not IsGridFull()`).
- **Cooldown rejection (observed):** produce taps while a producer shows
  the `cdTime` badge — and several later taps outside any visible window —
  produced no board or energy change. Client sends are unconditional; the
  server rejects silently. Whether rejection is a per-produce cooldown or a
  hidden `num` budget is unresolved (`num` is never displayed client-side).
- **Producer tooltips (observed):** Bowl 5 (type 3, LimitCount) reads "Tap
  to generate items upon reaching the highest level. Disappears after
  attempts are depleted" — consistent with `max_num` = lifetime attempts and
  removal when `change_item_id` is absent.
- **Orders (observed):** two order cards showed required item icons plus
  rewards of Feed pieces and Merge EXP; neither was fulfillable from the
  board at capture time, so submission remains unproven.

## September 18 second pass (main, Lv.9 board — input-timing A/B)

**Live-observed** on the same instance, a different castle's board. Probe
captures under the same artifact root plus raw frames in
`.local-data/devin-live-test/runs/sim-transitions-20260918/turn-002/`.

- **Tap-gap timing is not the produce gate (verified):** rapid ~300 ms
  select→produce double-taps and a ~4.4 s slow pair all produced. Pass-1's
  silent rejections were therefore producer server state (`cdTime`/`num`
  budget on that board's items), not input sequencing — and not the ±4 px
  humanization jitter, which was active for every successful tap here.
- **Produce ×4 (verified):** Arbre 4 (palm, max level) → berries at a
  server-chosen cell; Carte 4 (pouch) → stone piece; Argile 3 (clay) →
  broken-pot shard; Arbre 4 again ~5 min later → apple. Each cost −1
  energy; all spawns landed on server-chosen cells.
- **Repeat production (verified):** the same producer produced again
  minutes after its first use — cooldown/budget refreshes, consistent
  with the `num`-cycle reading rather than a permanent per-use budget.
- **Energy regen (observed):** +1 energy ticks were seen across ~40–90 s
  idle windows; the exact authored interval is unconfirmed.
- **Producer identity (observed):** selecting a producer shows its line
  and tier in the detail bar (e.g. "Arbre 4 (Niveau Maximum) — Appuyez
  pour générer des objets"); the ⚡ badge marks manual producers.

## September 18 third pass (main, Lv.9 board — cooldown + submit)

**Live-observed** on the same instance/board later the same day. Raw frames
in `.local-data/devin-live-test/runs/sim-transitions-20260918/turn-004/`.

- **`num`-cycle cooldown verified end-to-end:** Tree 4 (`num=40`,
  `cooldown_ms=10000`) accepted exactly 40 consecutive produces (energy
  −1 each), then rejected the 41st with an **"In Cooldown" toast**, a blue
  clock badge on the producer, and a **"Speedup 50"** gem button — the
  authored `cooldown_skip_cost=50`. ~12 s later the badge cleared and the
  next tap produced again. This pins `num` = uses per `cooldown_ms`
  window and explains pass-1's badge/rejections as mid-cycle state from
  prior play — not per-use cooldown, not input timing.
- **Board-full rejection (verified):** once every usable cell held a
  piece, further taps showed **"No slots available"** and spent no
  energy. The server had reused freshly-merged-free cells for spawns.
- **Order submit ×3 (verified):** a completable order shows a green
  **"Complete"/"Terminer" button** (`btnFinish` → `OnOrderTipClick` →
  `RequireOrderForm`). Tapping it consumed exactly the required pieces
  (one coconut from `posList`; three coconuts on the second), dropped
  the card, dealt a new random order, granted the reward (chest task
  counter +1; the earlier submit granted feed + potion to the knapsack),
  and cost no energy. Green-marked board pieces are the delivery
  candidates (`CheckStatues` Finish state); blue marks are HalfFinish —
  the piece is needed but the order is not fully satisfied.
- **Merge chains (verified):** fruit berries→apple→bananas→pomegranate→
  coconut and wood log→planks→crate follow `merge_successor_id`; ~20
  merges all landed. Merge creates no energy delta.
- **Energy regen (verified):** authored `energy_regen_ms=300000` (5 min)
  matches observed ticks (152→156 over ~23 min idle; several +1 ticks
  during the session's active play).
- **Locked cells:** "10"/"11" overlay cells are level-gated areas; they
  did not unlock on submit (`newAreaMap` requires the matching level).

## Observed recognition surfaces (PW02, 2026-09-17)

**Artifact-observed** on the reviewed 2026-09-16 exploration frames and the
authored `tests/data/screen_recognition/pet_workshop*` fixtures; the runtime
parser is `pnc_automation/app/pnc/vision/pet_workshop.py`:

- The board is a fixed 7x9 grid on the 540x960 reference frame. Level-locked
  cells show a numbered badge medallion on a bare tile (catalog
  `unlock_level`); seeded covered cells show grass tufts (`unlockType=2`)
  with contents hidden. Flat beige tiles are usable-empty.
- A tapped piece selects its cell (corner brackets) and opens a bottom
  selection bar with an inspect `!` medallion; a blue recycle trash button
  appears only for recyclable pieces (Treasure shows it, an inactive Bowl
  does not). Control presence is item-dependent and must be measured, not
  assumed. Palm foliage can chronically occlude a selected cell's brackets:
  on the 2026-09-16 frames 022-025 the selected Tree 4 cell stays
  below-threshold on every frame, so selection correctly publishes unknown;
  a clean merged frame of the same sequence measures its brackets and reads
  `SELECTED`.
- Order cards sit in a three-slot top strip; the right edge can clip the
  third card to a sliver. Scrolling left swaps the clipping: the leading
  card becomes a sliver while the trailing card ends just inside the frame
  and still reads complete. Requirement tiles carry a card-level state
  tint (fulfilled recipes sit on green, unfulfilled on blue); an icon
  observed on both tints keeps one template per reviewed appearance, e.g.
  Fruit 5 ships a green and a blue crop. A card's green Complete button
  appears only when all requirements are satisfiable from the board. The
  order-detail modal (tap a card) shows target items with satisfied checks
  plus a reward row; it has a close X but no submit control.
- The storage bottom sheet (layers icon) is a premium Get-Slots drawer with
  no close control — it dismisses on an outside tap. Its Get Slots/price
  column follows the sheet's slot capacity, not its occupied-item count:
  the reviewed five-slot LV6 sheet (four occupied, one empty) shows the
  anchors in the first column while the six-slot LV7 sheet shows them in
  the second.
- The Illusory Beast Manor hub is a navigation surface, not a Workshop
  surface; its Pet Workshop building and back chevron are measured controls.
- Header reads: `Lv.N` workshop level, `N/M` EXP gauge, `N/M` energy pill
  (verified: LV8 = `8/100`, `166/200`; LV6 = `79/80`, `200/200`). An energy
  read whose denominator is not positive is OCR noise and publishes unknown
  rather than a zero-capacity gauge; zero-current and over-capacity reads
  remain valid.

## September 27 manual-run diagnosis and offline regressions

**Saved-evidence / offline diagnosis:** the reviewed report and
game-knowledge addendum
(`C:/Users/lebel/pnc/.local-data/review/pw-main-manual-diagnosis-20260927/REPORT.md`,
`GAME-KNOWLEDGE-ADDENDUM.md`) plus the simulator findings
(`pet-workshop-pw01` worktree, `.local-data/review/pw-main-manual-20260927/SIMULATOR-FINDINGS.json`)
replayed a manual run against saved captures and offline fakes — no
daytime emulator or account access was used. Accepted facts:

- **Submit consumes by quantity (verified):** the reviewed run delivered a
  ready order requiring three identical Fruit 5/coconut pieces; all three
  were consumed. `RequireOrderForm` gathers the required *quantity* of
  matching Normal pieces — the game does not consume a pre-chosen cell —
  so stock and order readiness must be re-derived after every delivery.
- **Exactly-two-piece policy (policy, not game):** the game accepts orders
  of any piece total, including three-duplicate; the solver policy admits
  only orders whose required units total exactly two, counting duplicates.
  A native green **Complete** on a three-piece order is correct game UI,
  not policy approval — such orders are known-ineligible, never submitted.
- **Recognition boundary (verified):** an unreadable or clipped order card
  is not evidence the order is absent. Proven typed requirements stay
  known-ineligible even when the row's recognition status is UNREADABLE;
  partial/clipped requirement lists are never submittable. In the logical
  simulator, `ready=None` permits a transition with confirmed stock;
  live execution still requires a fresh measured ready control.
  `ready=False` proves no completable control.
- **Distinct producer/board conditions (verified):** selection marks the
  piece (border + detail bar); Use/Produce is the second tap — separate
  typed intents. A refused produce tap is not proof of a `cdTime`
  cooldown: `IsGridFull` (no usable empty cell), feed-locked producers
  (`unlockItemId`), inactive pieces and cooldown windows are independent
  gates. Level-gated locked tiles are not spawn capacity.
- **Grey activation (user-confirmed September 27; client-source supported):**
  merging Normal onto an identical grey/inactive piece produces the
  next-tier item. This uses `MergeGrid(..., true)`; it is distinct from
  reverse feeding through `MergeGridUnLock(..., true)`. User confirmation
  establishes the rule; it does not live-accept an executor implementation.
- **Energy accounting (repository-proven + user-confirmed):** ordinary production spends 1
  energy; merges, activations, feeds and order submission spend none;
  recycling Fruit 5 or Statue 5 returns +8 each (user-confirmed, matching
  `recoveryReward __rt_4`). The reviewed run's unexplained 154→153 delta
  stays recorded as-is. Order delivery costs no energy, user-confirmed
  September 27; the cause of that historical delta remains unknown.
- **Green/blue board marks (verified):** green marks Normal pieces whose
  item ID is needed by a fully satisfiable displayed order; blue marks
  partially satisfied order needs (`VerifyOrderTarget`,
  `ProcessOrderMarkGrid`; Finish takes precedence over HalfFinish). Marks
  are game signals spanning all displayed orders — including
  policy-ineligible three-piece orders — not policy permission, and they
  do not reserve pieces for the solver's selected goal. Reservations are
  recomputed from typed demands on every replan.

**Simulator/planner regressions added** (reduced deterministic scenarios,
not native board replay): the incident-shaped `{Fruit 5: 3}` rejection and
its UNREADABLE-completeness variant; full-board submission of a ready
reservation-safe secondary; recycling restricted to unreserved allowlisted
terminals while goal-protected pieces stay; sequential
submit → inspect → select → produce replanning; select-vs-produce split on
a Clay 4 producer; production refusals for feed-locked/inactive producers
and for boards whose only empty cells are level-locked; zero-energy-cost
merge/activate/feed; +8 recycling on both allowlisted terminals; and
quantity-based submit consumption with readiness re-derivation. Existing
coverage already proved three-distinct-piece rejection, quantity
consumption, unreadable/clipped readiness gating, cooldown waits
preserving readiness, and green-marked three-piece orders earning no
submission — those were cited, not duplicated.

**Outside the simulator boundary — assigned to their existing owners:** green-mark
recognition and raw tap/UI emulation; refill and speedup-modal
interruption; asynchronous server delivery and manual command-file
buffering; native energy and order recognition (one serialized recognition
worker, with no numeric repair/smoothing); and applicable final-candidate
live validation of runtime corrections. These tests change no production
planner behavior and require no new live proof themselves. Existing
manual-helper fixes remain locally implemented and offline-tested.

The readable native energy examples must replay as 162/200 and 163/200.
The final native chest/table two-piece card must be reproduced separately
to identify the failing item, tile-coverage or geometry boundary; narrower
spacing is an unsupported causal explanation until demonstrated. Preserve
the manual fallback while automatic recognition is unqualified. The
September 27 roadmap amendment owns these scoped corrections and the
separate design, offline, live and merge/push milestones.

## Saved-screenshot analysis (PW05, 2026-09-21)

`tools/pet_workshop_analyze.py` replays saved captures through the
production recognizer and accepted planner, writing one
`pet_workshop_analysis/v1` report plus an annotated review image per frame
under an ignored output directory. It reads images and writes reports only —
no emulator, ADB, lease or live state — and non-Workshop frames produce no
gesture proposal.

```powershell
# All labeled fixtures into the default .local-data/pet-workshop-analysis/
py tools/pet_workshop_analyze.py --fixtures --fail-on-mismatch

# Specific frames (fixture names or explicit paths) with a custom output dir
py tools/pet_workshop_analyze.py pet_workshop_merged_native_rgba.png `
    C:\path\to\saved.png --out-dir .local-data\pw05\run1
```

Reviewed expectations live in `tests/data/pet_workshop/analysis_labels.json`
(`pet_workshop_analysis_labels/v1`): each sample names the fixture, its
provenance kind (`real_screenshot`/`synthesized`) and a subset of the report
to match. Add a promoted fixture's entry there to make
`--fail-on-mismatch` and the analysis regression cover it.

Output files are named by each input's stem. Two inputs that share a
basename would overwrite each other, so the run is rejected with an
actionable error before any report is written — rename the inputs or
analyze them in separate `--out-dir` runs.

## September 22 live006 recognition corrections (PW05)

**Artifact-observed** on the four promoted native captures under
`C:/Users/lebel/pnc/.local-data/artifacts/2026-09-22/pet_workshop_pw05_hopium_growth_c920dad`
(board, two survey frames, one order detail; LV8, energy 123→124):

- The green **Complete** order control differs across the captured frames
  and between cards in one frame. Animation is the inferred cause; these
  snapshots do not establish its full cycle or independent timing.
  Recognition retains measured appearances (canonical plus alternates
  authored from these captures) at the unchanged match
  threshold; it does not relax confidence or guess coordinates. Cards
  that render no Complete control still publish `ready=None`/`False`
  with no measured `submit_bounds`.
- The order-detail reward row draws each reward inside its own framed
  box whose bottom edge forms the pedestal run; the Item Chest's art
  pokes through that edge and splits it visually, so runs separated by
  small gaps are merged back into one pedestal. Reward quantity badges
  sit lower than strip badges and can overhang the icon's right edge —
  the count zone reaches deeper/rightward and reads comma-grouped values
  (chest 1, feed "4,380" → 4380, lasso 2).
- The detail requirement band spans the modal's full centered pedestal
  row (three on the chest order); pedestals outside recognized template
  families keep unknown coverage rather than being dropped.
- `portrait_bounds` and `submit_bounds` are measured independently: the
  card portrait region can resize between animation frames while the
  control's measured bounds stay fixed.

## Remaining uncertainty

- `unlockType`/`type`/`getType`/`sort`/`assist`/`num`/`itemLimit` encodings
  are preserved raw; their consumers were not all traced.
- Generator `max_num` exhaustion/transform, feed-unlock, piece activation,
  and the live modal flow around recycling remain unobserved — no eligible
  board state appeared in three passes; see the PW10 live-qualification
  ledger. The +8 Fruit 5/Statue 5 recycle reward is now user-confirmed
  against `recoveryReward`. True server-side drop weights are not
  observable without many controlled samples; the simulator samples
  authored group weights and replays captured `ProduceOutcome`s for
  determined tests.
- The PW02 parser's qualified fixture coverage remains narrower than the
  simulator exploration record above. Those raw transition captures alone
  do not qualify cooldown, feeding, depletion, recycle confirmation or
  level-result recognition for unattended execution.
