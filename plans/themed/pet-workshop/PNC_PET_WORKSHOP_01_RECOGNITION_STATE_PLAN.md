# Pet Workshop 01 — Shared contract, catalog and recognition

Date: 2026-09-16. Design plan; [current packet status and next assignment](PNC_PET_WORKSHOP_ROADMAP.md).

## 1. Outcome and plan-set ownership

Build the canonical Pet Workshop data model, versioned game catalog and screenshot recognizer. The first useful result is a saved screenshot with reviewed labels and, once Plan 02 is connected, a correct proposed action. This package does not play the game.

The design remains divided among three canonical plans; the [roadmap](PNC_PET_WORKSHOP_ROADMAP.md) owns separate worker packets, dependencies and progress:

1. **This plan:** shared types/catalog, Workshop visual facts and controls, publication through both existing observers, saved-image analysis.
2. [Solver and policy](PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md): pure planning, effort estimates, ingredient reservations and legal-action policy.
3. [Execution and integration](PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md): observed gestures, mutation authority/receipts, independent CLI/API/authored runs, and Daily Maintenance.

This plan owns the shared interface definition below. Plan 02 owns gameplay decisions; Plan 03 owns execution and run lifecycle. Do not copy a recipe, policy rule, parser, executor or journal into another package. Changes to the shared interface are made once by its owner and migrate all affected callers.

### Common baseline and architecture requirements

Planning source baseline: `71272665667baf787538ca8377ed29746d440e22`. The task-owned planning checkout is at `ec76ff86c678eade9c942953a911423ab87d33b7`, which adds the Feature 06 identity-regression documentation. These are evidence checkpoints, not instructions to discard subsequently landed work. Before implementation, identify the accepted current base and reconcile changed owners by symbol.

- One canonical implementation and owner per concept; use existing observation, OCR, template, navigation, session, lease and storage owners.
- Follow the Open-Closed extension model through existing feature registration, typed interfaces and catalog owners. Keep feature-specific rules in their owner so callers reuse them. Do not introduce a generic screen-plugin framework, second vision backend, runtime Lua interpreter or special Workshop ADB client.
- Add strong types and abstractions only where they provide concrete safety, clarity or reuse worth their complexity. Avoid a wrapper class for every integer, configuration switches for hypothetical policies, or a parallel compatibility path. Packet independence must not require duplicate logic, speculative services or artificial validation constraints.
- Fail fast on invalid authored/catalog data. Incomplete or ambiguous screenshots are ordinary recognition results, not malformed configuration exceptions.
- Document every new or materially changed function, including helpers: explain its intent, relevant preconditions, units, return meaning and side effects. Keep docstrings useful rather than repeating the signature. Update the canonical design/behavior documentation as the implementation becomes concrete.
- Fully migrate affected callers and remove superseded task-owned prototypes. Do not retain a second production implementation or fallback. Preserve unrelated legacy work until its own owner migrates it.

## 2. Agreed behavior shared by the three plans

This table records the user's interview decisions. Implement these defaults in the single Plan 02 policy owner; recognizers report facts even when policy excludes them.

| Concern | Decision |
| --- | --- |
| Eligibility | Explicit account/castle selection. Skip a castle confirmed below C24. Workshop level/progress is read separately for each castle. |
| Orders | Submit only orders requiring **exactly two total pieces**, including repeated quantities. One-piece and three-piece orders remain recognizable but ineligible. |
| Reward order | Beast Lasso > feed > green Workshop EXP > bottles > chests. |
| Within one reward tier | Prefer reward quantity per estimated additional production energy, accounting for existing board progress. |
| Lower-priority ready orders | Allowed only when they preserve quantities and merge progress reserved for the selected higher-priority goal. |
| Energy | Use the current bar, allowing natural regeneration and automatic level-up gains. Stop immediately when zero is reliably observed. No inventory refills, board energy-piece consumption or purchases. |
| Recycling exception | Only unreserved **Fruit 5 / item 20105** or **Statue 5 / item 10205**, only to unblock a full board after useful permitted merges/submissions are unavailable. Recover energy through the garbage-bin control. Never recycle at observed zero. No other deletion or storage use. |
| Supported mechanics | Ordinary and finite generators, feeding generators with matching board pieces, generator upgrades through merging, and activation of matching grey/inactive pieces. |
| Cooldown | Perform other useful permitted work first. If cooldown is the only obstacle, wait at most 60 seconds in that continuous blocked episode, then stop that castle and continue where safe. |
| Excluded mechanics | Premium Auto Fusion, paid acceleration, purchases, special cards, opening/consuming reward pieces, and unrequested inventory/storage operations. |
| Entry points | Independent Workshop CLI/API and authored PNC task **plus** Daily Maintenance. Both use the same workflow and policy. |
| Daily behavior | Run after the existing work for that castle, on every maintenance invocation, with fresh state. No once-per-day suppression after an earlier zero-energy run. |
| Failure isolation | Unknown screen or uncertain mutation stops the affected physical instance for the current run; retain evidence and continue independently usable selected instances. A known ordinary blockage may end only that castle. |
| Later authorized runs | A separate later invocation may use another explicitly selected castle on that instance after fresh identity and safe-screen validation. The castle with the unresolved action remains blocked until that action is reconciled; a new date, entry point or operation ID does not clear it. |
| Level-dependent progression | Treat orders and producer acquisition as linked to Workshop progression, with the evidence limits below. No special lower-priority production strategy is added for an unproven locked-chain order; existing supported progress/inspection/stop behavior applies. |

Target identifiers are supplied at execution time through existing account/castle aliases. This plan does not select a production account, change local account YAML or launch a recurring schedule.

## 3. Evidence and existing owners

### Evidence that can be used without live access

The originating host's ignored evidence root is `C:/Users/lebel/pnc/.local-data/`. Resolve that explicitly when working in an isolated checkout; do not assume its `.local-data` contains the original artifacts.

| Evidence | Location under the evidence root | Limits |
| --- | --- | --- |
| Reviewed client findings | `reports/pet-workshop/reviewed-findings-2026-09-16.md` | Historical read-only access blocker is superseded by the later live report. |
| Completed prior exploration | `reports/pet-workshop/live-findings-2026-09-16.md` | One production and one ordinary merge; no order submission, recycling, feeding, depletion or zero-energy test. |
| Reviewed contract research | `reports/pet-workshop/recognizer-solver-contract-2026-09-16.md` | Predates the interview. The decisions in section 2 supersede its narrower mechanics and missing Daily scope. |
| Decoded tables and hashes | `reports/pet-workshop/client-tables-5.0.203/` | Packaged 5.0.203/233; sparse rows inherit defaults and rewards can reference shared tables. |
| Recovered client | `apk-exploration/gameplay-lua/` | Static evidence, not access to current hidden game state or a replacement network client. |
| Saved BlueStacks frames | `artifacts/2026-09-16/pet_workshop_exploration_20260916/` | 900 x 1600, native opaque RGBA, live build `5.2.80_5.0.204.235`. |
| User screenshots | `C:/Users/lebel/Pictures/pnc/petworkshop/` | 16 phone JPEGs at 1116 x 2480; useful item/detail references, not proof of emulator controls. |

Decisive saved frames in the BlueStacks directory:

- `20260916T051117Z_explore_009_after_tap.png`: Workshop board, energy 166.
- `20260916T051131Z_explore_011_after_swipe.png`: order strip including the ready three-coconut order and lasso goal.
- `20260916T051148Z_explore_013_after_tap.png`: lasso order details, Wood 10 + coconut, 2 lassos and 4,380 feed.
- `20260916T051206Z_explore_015_after_tap.png`: Wood chain/source details.
- `20260916T051242Z_explore_019_after_tap.png`: black transition frame.
- `20260916T051309Z_explore_022_after_tap.png`: selected Tree 4 at r9c7, unchanged energy.
- `20260916T051324Z_explore_024_after_tap.png`: generated apple at r8c7, energy 165.
- `20260916T051343Z_explore_026_after_swipe.png`: Fruit 3 at r7c3 after merging the apples; r8c7 empty.
- `20260916T051417Z_explore_028_after_tap.png`: Workshop help.

Route-evidence pairs in that same directory are `20260916T051058Z_explore_006_before_tap.png` → `20260916T051101Z_explore_007_after_tap.png` for Home → Manor; `20260916T051115Z_explore_008_before_tap.png` → `20260916T051117Z_explore_009_after_tap.png` for Manor → Workshop; `20260916T050642Z_explore_002_before_tap.png` → `20260916T050645Z_explore_003_after_tap.png` for Workshop → Manor; and `20260916T050709Z_explore_004_before_tap.png` → `20260916T050712Z_explore_005_after_tap.png` for Manor → Home. Their commands/results are recorded in `reports/pet-workshop/explore_main_20260916.jsonl`. These are supervised route observations; PW02 must qualify measured source controls and destination identities before handing them to Plan 03 for core edges. The old coordinate commands are evidence, not production selectors.

Lead source checks: `MergeGridItem:OnClickHandler`, merge-drop handling, `CheckProduceCd`, `ShowHelpTag`; `MergeDetailsBottom:CalculateItemCd` and `OnBtnHelpHandle`; `MergeAdventureData:GetDeliveryPos` and `IsGridFull`; `MergeOrderItem:SetTargetItems` and order click handlers; `ComposeactSend.RequireProduce`. The item table maps Fruit 5 and Statue 5 to recovery reward `__rt_4`, encoded as count 8 of energy-related item 44009010/type 9. Treat the current bar/receipt effect as a later action qualification, not proof of a live +8 delta.

### Workshop progression and order selection

Reviewed 2026-09-16 from packaged build `5.0.203/233`; the prior live observation used `5.2.80_5.0.204.235`. The user expects active orders and generator acquisition to follow Workshop progression. The lead verified the source excerpts below, then Devin reviewed those excerpts in a read-only consultation. This supports the expectation without proving a guarantee about all current server-assigned orders.

| Finding | Evidence and confidence | Automation implication |
| --- | --- | --- |
| Normal order display checks completed prerequisites, minimum Workshop level and, when configured, item-family presence. | Repository-proven, high: `uis/composeact/item/mergeadventureorderoperation.lua:161-224`, `VerifyDisplayOrder`; `datas/mergeadventuredata.lua:947-958`, `VerifyHasSubType`. Paths are under the recovered-client evidence root above. | These explain progression. They are not extra UI recognizer fields: server order IDs, completed `preIds` and hidden order types are not required observations. |
| Hidden orders appear when their target requirements are satisfied; random orders arrive as a server-selected ID list. The Normal-order checks are not the random-order selector. | Repository-proven, high: `VerifyDisplayOrder` and `VerifyNewOrder:104-123`; `GetRandomOrders:922-924`, `SetRandomOrders:929-942`; `commands/composeact/composeactcommand.lua` passes `serverData.randomOrderForm` to that setter. | The server's random-order level/feasibility algorithm is unknown. Survey actual visible orders; do not synthesize them from the packaged forms or reproduce a hidden server eligibility check. |
| Workshop levels award producer items and unlock board areas; this does not guarantee a usable producer on the current board. | Repository-proven, high: `ComposeActLevel.lua` gives 10001 at level 2, 20001/10002 at level 3 and 40001/30003 at level 10; `ComposeActAreaGrid.lua` has `level`/`unlockType`. `ComposeActWorker.lua` has no minimum Workshop-level field. | Keep item tier, Workshop level, board access and current generator state distinct. Do not invent a per-generator minimum-level constructor invariant. |
| Feeding and finite exhaustion are separate from a never-unlocked chain. | Repository-proven, high: `IsProductionNeedUnLock:465-470` reads `unlockItemId`; worker records carry `maxNum`/`changeItemId`. | Apply supported feeding, merging/activation or producer reconstruction when useful and permitted. A recoverable generator state is not an immediate stop. |

The consultation memo is saved at `C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-castle-identity-plan/.local-data/devin-game-knowledge/20260916-170720-finish-a-focused-pet-workshop-consultation-using-fa1f406fa7/response.txt`. Its proposed mirroring of hidden prerequisite state is not adopted, and its blocked-state advice is subordinate to the already-supported mechanics above. PW01 carries these reviewed findings and their confidence/provenance into the canonical game-workflow note; the memo is research evidence, not another runtime rule owner.

No special locked-chain strategy or extra live visit is required. If the observed board still permits no useful action after the existing rules are applied, retain evidence and use the existing known-blocked/unknown outcome. Do not reject a visibly present order as malformed merely because inferred level eligibility disagrees. If this situation is later observed, a capture of the Workshop level, readable order requirements and relevant board/producer state is sufficient evidence to investigate; a hidden server order ID is not required. Scripted prerequisite chains do not override the exact-two-piece submission policy.

### Canonical integration points

Follow the accepted [V01 extension contract](../vision/modules/V01_EXISTING_OPENCV_FOUNDATION.md#where-later-packets-extend-the-path):

- `VisualScreenRecognizer` and `data/screen_anchors.json` prove screen/layout and measure controls; identity anchors are not automatically action targets.
- `ObservationRequest`, `pnc_ocr_capabilities.py`, `ocr_region_plan.py` and the frame-owned `ObservationOcrContext` own requested OCR and its cost.
- One Workshop feature parser is called by `PncObservationEnricher.enrich` and returns `ObservationAdditions`.
- `ObservationBuilder` and `NavigationPerception` publish that same content and provenance. Neither acquires a second parser.
- `observation_provenance.py` binds measured controls and content to the current frame.

Pet Workshop is not the existing **Trap Workshop** building family. Add the actual Beast Manor/Workshop identities without borrowing Trap Workshop enums/selectors. Plan 03 owns navigation edges; Plan 01 supplies their observed screen/control facts. The existing [Feature 06 selected-castle regression](../account-runtime/PNC_CORE_REMAINING_06_CASTLE_NAVIGATION_PLAN.md#september-16-regression-native-screenshot-drops-the-selected-hopium-row) remains with its current owner.

## 4. Shared interface contract

### Shape and ownership

Use a focused `app/pnc/domain/pet_workshop.py` module for shared immutable domain types and a focused packaged catalog owner under `app/pnc/`. Split only when responsibilities warrant it. The feature parser belongs under `app/pnc/vision/`; the pure planner belongs under `app/automation/pet_workshop/` in Plan 02. These names are new proposed owners, not claims that modules already exist.

Represent the observation as **one logical `WorkshopState` plus a `WorkshopView`** containing measured geometry/provenance. The published `WorkshopObservation` composes them. Do not repeat item/energy/order fields in a second solver model. A solver consumes the logical state without coordinates; the executor resolves its targets against the corresponding view and a fresh frame.

| Model/fact | Minimum meaningful contents |
| --- | --- |
| WorkshopState | Surface kind, grid dimensions/coverage, energy current/capacity and supported production mode, Workshop level and EXP, selection, cells, surveyed orders and order-survey freshness. Unknown readings remain explicit. |
| Cell | Logical row/column/ID; access separately from occupancy; item ID when known; normal/inactive/bubble/feed-locked/unknown item state; visible cooldown active/clear/unknown. Generator kind comes from the catalog. |
| Selection | Distinguish a known selected cell, known no-selection, and unknown selection. This is necessary because a repeated tap can consume or produce. |
| Order | Observation-local reference, requirement quantities by item ID, completeness/visibility, observed availability/ready control, reward quantities by recognized category, and source evidence. Unknown/other rewards are representable. |
| WorkshopView | Current FrameRef and source image size; measured board cell bounds; order portrait versus submit bounds; safe detail/close/recycle/confirmation controls. No inferred offscreen click coordinates. |
| Catalog | Item IDs/names/sprites, merge successors, producer type/drop weights, feed ingredient, configured capacity/exhaustion transform, unlock facts, energy mode/cost and recycling reward provenance. |
| WorkshopPolicy | A small typed policy for the agreed behavior; default values and evaluation belong to Plan 02. Scope/target configuration remains with the existing application owners. |
| WorkshopDecision | One typed logical intent plus a human-readable reason and the state facts needed for revalidation. No raw gesture or screenshot coordinates. |

Use tagged dataclasses/enums or equally clear existing conventions. `None` may mean unknown for a numeric reading, but cannot conflate unknown with a known empty cell or no selected cell. Do not add generic per-field wrapper/provenance hierarchies where the containing frame and a scoped diagnostic are sufficient.

Shared intent variants: **Select, Produce, Merge, Activate, Feed, Recycle, SubmitOrder, Inspect, Wait, Stop**. Ordinary generator upgrades use Merge with a catalog successor; finite generators use Produce. Activate and Feed remain distinct because their consumption/preconditions differ. Inspect names a logical information need or target; Plan 03 owns the reviewed navigation needed to satisfy it. Generic move/swap, refill, purchase and special-card intents are outside this release.

Agree these pure interfaces in PW01 before downstream workers start:

- `plan_next(state, catalog, policy) -> WorkshopDecision`, implemented by Plan 02.
- `validate_intent(state, intent, catalog, policy) -> validation result`, implemented by Plan 02 and reused before execution; it is the same legal-action/reservation logic, not a second executor policy.
- One `workshop` content field on `ObservationAdditions` and the canonical `Observation`, bound consistently in both publishers.

PW01 defines the models and signature contract, not placeholder production implementations of the solver or executor. Downstream tests may use typed fixtures/test doubles. Do not ship runtime stubs or duplicate the future owner to make a parallel branch import successfully.

### Important data rules

- Current observed board is 7 columns x 9 rows; ID is `(row-1)*7+column`. Keep dimensions in the layout/catalog model and validate coordinates against them. Recognition of another layout requires evidence; a malformed or partial frame is not resized into a fictitious complete board.
- Order eligibility is **not** a model invariant. Preserve three-piece orders accurately for Plan 02 to reject.
- Catalog coverage counts such as 114 items describe the packaged seed, not a fixed-length schema; valid future entries must not fail merely because the count changes.
- Capacity 200 and ordinary cost 1 are current evidence, not universal constructor limits. Do not reject possible over-cap energy simply because regeneration normally caps at 200.
- Reject duplicate catalog keys, nonpositive quantities where quantities are required, dangling recipe/drop references, impossible grid addresses, nonpositive total drop weight and cycles in a merge-successor graph. Normalize weights by their actual positive sum; do not require every group to total exactly 1000.
- Distinguish recoverable OCR uncertainty from invalid catalog/authored values. Unknown fields block only decisions depending on those fields.
- Do not invent server order IDs, remaining generator uses, exact cooldown deadlines, spawn positions or permanent card identity. A catalog maximum is not current stock. The cooldown price label is not a remaining-use count.
- An absent lightning icon is not evidence that an item is not a generator: the client hides it during cooldown.

## 5. Separate implementation packets

| Packet | Deliverable |
| --- | --- |
| [PW01](packets/PW01_SHARED_CONTRACT_CATALOG.md) | Shared models, catalog, seed fixtures and canonical implementation documentation. |
| [PW02](packets/PW02_RECOGNITION_CONTROLS.md) | Workshop parser, measured controls, observer parity and route-evidence handoff. |
| [PW05](packets/PW05_SCREENSHOT_PROPOSAL_MILESTONE.md) | Saved-image analysis using the accepted parser and solver; first screenshot/proposal milestone. |

These files own their work instructions and acceptance handoff. The [roadmap](PNC_PET_WORKSHOP_ROADMAP.md) owns scheduling, dependency status and the worker/lead review cycle.

## 6. Verification and evidence gaps

Use the repository test runner. Run the narrow affected component first, then `py tools/run_tests.py affected --base <accepted-base> --explain`; accept its legitimate full fallback for new/shared modules. Do not write wording-only documentation tests. Catalog/schema invariants and observer parity warrant portable tests; live execution belongs to Plan 03.

Required recognition cases: native RGBA and phone-reference layouts; zero versus unreadable energy; inactive versus normal and bubble/feed-lock overlays; cooldown icon disappearance; selected reward-piece hazard; duplicate ingredient quantities; clipped third ingredient; similar reward icons; order detail versus submit geometry; both-observer content/provenance parity. Use negative crops only for credible confusions represented in the corpus.

Known missing coverage: order completion/result, recycling receipt, generator feeding/depletion, grey activation, newly unlocked cells/level result, another Workshop level and the corrected production identity preflight. [PW10](packets/PW10_LIVE_QUALIFICATION_INTEGRATION.md) owns the bounded live acceptance ledger; recognition corrections feed back through this one parser. Do not label a synthetic fixture as live proof or declare all mechanics accepted from the initial screenshots.

Shared worker instructions and lead review are in the [roadmap](PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Full completion requires the [PW10 qualification and integration packet](packets/PW10_LIVE_QUALIFICATION_INTEGRATION.md).
