# Remaining A11/A12/A13 building workflows — bounded implementation plan

## Status, owner, and checkpoint gate

This is an A-owned remaining-work plan for the finite A11/A12/A13 building slice.
It covers the 19 remaining original building routes and the legacy construction
and upgrade callers. Preserve the six already supported endpoints. It does not reopen the A11
catalog inventory, add a generic mutation abstraction, or take ownership of B's
recognition, OCR, assets, or observation publication.

Read the [six-package coordination contract](PNC_CORE_WORKFLOW_PORTING_PLAN.md#six-remaining-agent-packages) before implementation. It defines the shared snapshot, exclusive-file ownership, and permission ledger that govern this plan.

The implementation worker must begin by recording:

```text
git rev-parse HEAD
git status --short --ignored
```

The expected source checkpoint is `4f332027e924a9f73e3e3740d92980d8950ddae1`
(`HEAD4f33202`). The worktree also contains dirty, completed A changes and
root-owned plan/ledger files. They are part of the starting snapshot. Preserve them,
never reset or clean them, and never overwrite a root-owned hunk. Serialize edits to
shared files with the other remaining plans and with root's current work:

- `pnc_automation/app/automation/engine/core_daily_mutation.py`
- `pnc_automation/app/automation/engine/core_workflow.py`
- `pnc_automation/app/automation/engine/navigation_core.py`
- `pnc_automation/app/entrypoints/task_registry.py`
- `pnc_automation/app/entrypoints/api.py`
- any shared domain/policy or test-runner file

Before touching one of those files, publish the exact intended patch range and wait
for the owner of the concurrent slice to release it. Do not use a second worktree,
merge, reset, or commit in this plan. The final worker report must include the
checkpoint, preserved dirty paths, changed files, focused commands, and results.

## Remaining deliverables and scope

Reconciled September 14 against A `4f33202` plus its preserved dirty changes and
published B `10740ebb9b8d9d43fc24f970b904796ca41bd082`. The six existing endpoints
are modeled routes, not a claim that all six currently acquire a Home object on
the new producer. The saved Institute-source replay through both B production
observers publishes clear Home but zero building objects. That shared source
regression must close before a building route relying on that publication is
accepted; its canonical producer work is described in
[package 01](PNC_CORE_REMAINING_01_RESEARCH_LIVE_PLAN.md#producer-acceptance-on-the-saved-institute-source).

Deliver the following cohesive behavior:

1. Implement the remaining 19 A11 routes once each endpoint has independent replacement visual evidence and a reviewed return edge. The six currently supported endpoints are preserve-only route acceptance in this slice; they are not new route deliverables.
2. Port the existing normal building-construction behavior through typed
   `WorkflowContext`, reviewed `NavigationCore` edges, the existing durable mutation
   journal, and `CoreMutationBoundary`. Construction remains a finite, explicit
   caller. It is not added to automatic Daily maintenance.
3. Port the existing building-upgrade behavior with its current level, queue,
   prerequisite, normal-payment, warning, and optional speedup semantics. The typed
   operation must dispatch once, record the intent before input, and reconcile a
   target-specific receipt without replay.
4. Keep the canonical `OpenBuildingWorkflow` for entering one of the six supported
   endpoints. The A11 artifact counts six current core endpoints: Castle, Institute,
   Warehouse, Goddess Statue, Hero Hall, and Campaign. Their independent fixtures and
   reviewed return edges are listed in
   `.local-data/artifacts/core_resume/a11_endpoint_inventory.json`.
5. Keep the finite endpoint inventory bounded to the original 25 historical smoke targets. Sixteen
   have catalog mappings but still lack independent replacement profile and/or
   reviewed return evidence; Arena lacks a primary mapping/profile and a
   Versus-to-Home edge; Bank and Dragondom Conquest are unmapped. Do not revive the
   old generic `PNC_BUILDING_DETAILS` or build-menu fallback to claim A11 completion.
6. Wire direct and authored callers after the typed path has producer facts and
   offline coverage, then use that actual path for the bounded live proof. Promote
   caller acceptance only after that proof passes. Keep parameter compatibility for
   existing callers where it does not weaken exact identity or mutation authority.

Construction and upgrade actions are separate from read-only endpoint coverage. A
supported `open_building` route is not evidence that a build/upgrade control or its
receipt is publishable.

## Finite A11 endpoint inventory and acceptance

The original inventory contains exactly 25 endpoint requirements. The six
`supported_current_core` rows preserve the existing catalog/profile/return contract;
they do not imply action support. The remaining 19 are finite route deliverables,
implemented only after their producer dependency is present. A11 must add no route
for a row marked blocked or unmapped below.

| Original endpoint | Current replacement identity | A11 disposition and exact acceptance |
| --- | --- | --- |
| `CASTLE` | `PNC_CASTLE` | Preserve `castle_audit.png` and `PNC_CASTLE -- PNC_BACK_BUTTON_TOP_LEFT -> PNC_HOME_CITY`; fresh identity and reviewed return remain green. |
| `WALL` | `PNC_WALL` | Add only after an independent replacement profile and saved open/Back-to-Home transition qualify; exact `WALL` identity and fresh return required. |
| `INSTITUTE` | `PNC_INSTITUTE` | Preserve `institute_audit.png` and reviewed Back-to-Home edge; action facts are separately A12/A13 producer work. |
| `WAREHOUSE` | `PNC_WAREHOUSE` | Preserve `warehouse_audit.png` and reviewed Back-to-Home edge; action facts are separately A12/A13 producer work. |
| `TRAP_WORKSHOP` | `PNC_TRAP_WORKSHOP` | Add after independent profile plus saved open/return evidence; reject generic building-details fallback. |
| `WATCHTOWER` | `PNC_WATCHTOWER` | Add after independent profile plus saved open/return evidence; exact target and reviewed return required. |
| `SAUROI_LAIR` | `PNC_SAUROI_LAIR` | Add after independent profile plus saved open/return evidence; exact target and reviewed return required. |
| `CAMPAIGN` | `PNC_CAMPAIGN_MAP` | Preserve `campaign_map.png` and `PNC_CAMPAIGN_MAP -- PNC_CAMPAIGN_HOME_PORTAL -> PNC_HOME_CITY`; battle preparation remains separate. |
| `ARENA` | required mapping to `PNC_VERSUS_CENTER` | Add catalog primary mapping, independent replacement profile, and reviewed `PNC_VERSUS_CENTER -> PNC_HOME_CITY`; the legacy HeroShowdown-to-Versus proof is not this edge. |
| `ALLIANCE_HALL` | `PNC_ALLIANCE_HALL` | Reuse B's published `alliance_remaining_hall` reference profile and qualified Hall rows. Still prove the exact Home object → Hall route, current control/return edge and independent capture group; reference-profile presence does not complete A11. |
| `BLACKSMITH` | `PNC_BLACKSMITH` | Add after independent profile plus saved open/return evidence; exact target required. |
| `MARKET` | `PNC_MARKET` | Add after independent profile plus saved open/return evidence; the historical build-menu fallback is not acceptance. |
| `GODDESS_STATUE` | `PNC_GODDESS_STATUE` | Preserve `goddess_statue_audit.png` and reviewed Back-to-Home edge; action facts are separately A12/A13 producer work. |
| `TOWER_OF_TRIAL` | `PNC_TOWER_OF_TRIAL` | Add after independent profile plus saved open/return evidence; exact target and reviewed return required. |
| `BANK` | no canonical primary screen | Add only after a canonical producer mapping, independent profile, and reviewed return exist; generic `PNC_BUILDING_DETAILS` is rejected. |
| `SANCTUM` | `PNC_SANCTUM` | Add after independent profile plus saved open/return evidence; legacy parsing alone is not replacement evidence. |
| `RANGED_BARRACKS` | `PNC_RANGED_BARRACKS` | Add after independent profile plus saved open/return evidence; exact target and reviewed return required. |
| `INFANTRY_BARRACKS` | `PNC_INFANTRY_BARRACKS` | Add after independent profile plus saved open/return evidence; exact target and reviewed return required. |
| `CAVALRY_BARRACKS` | `PNC_CAVALRY_BARRACKS` | Add after independent profile plus saved open/return evidence; do not expand cavalry policy. |
| `SIEGE_FACTORY` | `PNC_SIEGE_FACTORY` | Add after independent profile plus saved open/return evidence; exact target and reviewed return required. |
| `HERO_HALL` | `PNC_HERO_HALL` | Preserve `hero_hall.png` and reviewed Back-to-Home edge; Hero summon/result ownership stays with B. |
| `HALL_OF_WAR` | `PNC_HALL_OF_WAR` | Add after independent profile plus saved open/return evidence; exact target and reviewed return required. |
| `SACRED_TREE` | `PNC_SACRED_TREE` | Add after independent profile plus saved open/return evidence; exact target and reviewed return required. |
| `PIT` | `PNC_PIT` | Add after independent profile plus saved open/return evidence; exact target and reviewed return required. |
| `DRAGONDOM_CONQUEST` | no canonical primary screen | Add only after a canonical producer mapping, independent profile, and reviewed return exist; historical smoke inclusion is not replacement support. |

For each of the 19 additions, the saved evidence must contain source identity,
post-open identity, exact actionable control or read-only endpoint, and a reviewed
return edge. A classifier header, enricher definition, generic Back helper, or
historical task fixture is not an independent profile or reviewed route.

Keep all 19 in the execution ledger: Wall, Trap Workshop, Watchtower, Sauroi Lair,
Arena, Alliance Hall, Blacksmith, Market, Tower of Trial, Bank, Sanctum, Ranged
Barracks, Infantry Barracks, Cavalry Barracks, Siege Factory, Hall of War, Sacred
Tree, Pit and Dragondom Conquest. A Farm detail/construction proof is an action
representative; Farm is not a replacement for any of these original endpoints.

For every row apply this concrete route sequence through the existing owners:

1. Resolve `OpenBuildingPolicy` to its exact `HomeCityObjectId`; read
   `building_catalog._PRIMARY_SCREEN_BY_HOME_CITY_OBJECT_ID` and the corresponding
   owning-screen map. For Arena establish the canonical primary Versus mapping;
   for Bank and Dragondom obtain B's actual supported endpoint identity before
   adding a mapping. An enum name or legacy generic-details fixture is insufficient.
2. On fresh independently recognized Home, use
   `NavigationCore.open_building` / `open_visible_building` and the existing
   bounded camera acquisition. Require exactly one current matching object with
   valid bounds, source frame and safe point. Missing Home publication blocks
   input before the route; more camera gestures cannot manufacture its facts.
3. B qualifies the endpoint's screen/layout, current return control and consumed
   content through both observers. A consumes the saved action/destination pair
   in `reviewed_navigation_edges` and `_require_reviewed_building_route`. Reusing
   a Back selector is allowed only with a proved destination for this screen.
4. The consumer contract must exercise the actual captured Home object, one
   fresh object tap, independent destination observation, measured return action
   and fresh Home. Test a wrong destination and lost/changed object before input;
   fixture text alone must not force the expected screen. A already modeled
   endpoint or menu option without these observations stays blocked.
5. Use saved transition evidence if sufficient. Otherwise run one leased
   production `OpenBuildingWorkflow` open/return for that distinct new route.
   Stop on the first unproved predicate, save before/action/after/return frames
   and trace, and continue offline work on other rows. Do not perform a building
   mutation to prove a read-only endpoint.

Once an endpoint's producer gate passes, extend its existing catalog mapping and
reviewed route, add a consumer open/return contract using that real frame, and
exercise the production `OpenBuildingWorkflow` caller. Qualify each distinct new
edge with saved current-build transitions or the smallest necessary leased live
open/return. Do not repeat a live open merely because another API exposes the same
route. A11 completes when all 19 rows are qualified and implemented, or reports
each exact remaining blocked row; an inventory alone is not completion.

## Existing implementation and caller map

The current behavior and its intended replacement seams are:

| Area | Existing path | What it establishes | Porting consequence |
| --- | --- | --- | --- |
| Construction | `pnc_automation/app/automation/tasks/building_construction_task.py:BuildingConstructionTask` | Validates `BuildingConstructionPolicy`, resolves the exact empty home slot and `BuildingConstructionSource`, opens fixed/large/small menu, taps ordinary Build, and checks timer/queue/target evidence | Preserve source-family and target validation, but move navigation and the one mutation to the typed core |
| Upgrade | `pnc_automation/app/automation/tasks/building_upgrade_task.py:BuildingUpgradeTask` | Chooses policy priority, opens the exact target, handles unmet requirements, queue/full states, warning, optional speedup, and timer/level confirmation | Preserve the policy branches as typed decisions; do not translate them into blind button retries |
| Shared UI facts | `pnc_automation/app/automation/tasks/building_workflow_support.py` | Existing timer, queue, requirement, help, and speedup helpers | Reuse the meanings in typed observation models; do not duplicate OCR parsing in a caller |
| Catalog | `pnc_automation/app/pnc/domain/building_catalog.py` | `HomeCityObjectId`, primary screen/owner maps, construction families and source selectors | Extend only exact typed identities needed by this slice |
| Policy | `pnc_automation/app/pnc/domain/policy_models.py` | `BuildingUpgradePolicy` (`allow_speedups`, prerequisite mode, premium-material policy) and `BuildingConstructionPolicy` | Keep defaults fail-closed: no speedup or premium purchase without explicit policy and acknowledgement |
| Typed entry | `pnc_automation/app/automation/open_building.py:OpenBuildingWorkflow`, `NavigationCore.open_building` | Source selection, exact object identity, reviewed route and fresh destination | Reuse for both workflows; no caller-local coordinate fallback |
| Dispatcher | `pnc_automation/app/automation/engine/core_script_dispatcher.py` | Typed lifecycle/castle/chat/mail/Research/open-building steps; no build/gather branches | Add only the two explicit typed workflow steps and their parameter validation |
| Entrypoints | `pnc_automation/app/entrypoints/task_registry.py`, `pnc_automation/app/entrypoints/api.py` | Legacy `BuildingConstructionTask`, `BuildingUpgradeTask`, and `run_task` wrappers | Migrate one authored/direct caller slice after acceptance; retain no second mutation owner |
| Mutation | `CoreMutationBoundary`, `DailyMutationAuthorizer`, `JournaledMutationDispatcher`, `DailyRunJournalStore` | Durable PREPARED/DISPATCHED/RECONCILED/COMMITTED intent and exact account/castle/capability limits | Reuse these interfaces; extend identity/capability explicitly only where construction has no durable quest id |

The existing registry and API are evidence of the migration remainder, not a reason
to broaden this plan to every task. The implementation must leave Research, Resource,
Hero, and Daily changes owned by their current workers intact.

## Producer facts required before implementation can be accepted

The published batch supplies useful subsets. Consume these before requesting
more producer work; do not reconstruct them or count them as complete A workflows:

| Published B fact/reference | Exact remaining qualification or consumer work |
|---|---|
| `building_detail_farm`, `building_construction_farm`, level 0/1 and upgrade 7/8 captured cases | Reuse `tests/integration/vision/test_building_captured_flows.py`, `test_building_level_publication.py` and `tests/data/screen_recognition/building_variants/`. Prove exact empty slot/instance, current normal control, source/menu family and correlated new Start receipt in the consumer. Other fixed/large/small construction families remain open where their UI differs. |
| Castle/Institute/Warehouse/Goddess level publication | Reuse bounded per-field production reads and non-actionable levels; a readable number is not a target identity or a receipt. Preserve Castle's native RGB3x field behavior instead of coercing malformed numbers. |
| `institute_upgrade_detail` unmet prerequisite Go | Preserve the distinct unmet row and measured Go; a satisfied Requirement heading and Builder Set Go must not become this prerequisite action. A still owns `FAIL`/`QUEUE`, actual prerequisite identity, route and receipt. |
| `build_queue_centered` active and idle reference rows | Preserve title/timer/state row association and Close. Active-reference replay is not independent qualification of a new target's started queue. The consumer must compare the exact pre-action baseline with the new target-associated row. |
| Independent idle Build Queue source `20260913T234651Z_build_queue_holdout.png` | The frozen-catalog 3xx replay already proved clear centered Queue, measured Close and no unsafe upgrading rows through both paths. Reuse it; do not demand another idle capture or call it an active queue/level receipt. |
| `alliance_remaining_hall` | Destination reference recognition and Hall row content are present. Home acquisition, reviewed return and independent layout qualification still gate the A11 route. |
| Home source after Research Queue Go | Current B publishes no Home objects on A's saved source. Restore semantically bounded current object publication, including Institute, in the existing B Research follow-up owner; A may not add its own OCR or coordinate fallback. |

The independent-evidence inventory is B's
`.local-data/reports/non_yolo_remaining_evidence_audit.md`. New/changed Farm,
construction, active Queue, Institute-detail and Hall layouts require their own
remaining independent evidence. A replay of a reference or a resized copy does
not satisfy that criterion. A scope is blocked only by the facts it consumes;
it need not wait for every unrelated B layout.

A may implement the consumer and mutation path only after B or another explicitly
assigned producer publishes these facts in both canonical observation paths. These
are producer facts, not fields to infer in a building workflow:

### Endpoint and target facts

For each action representative, the observation must publish one exact
`HomeCityObjectId`, canonical primary screen, instance/building id where available,
current level, and an actionable reviewed return edge. A visible label or a generic
building detail screen does not establish identity. The source frame and the final
fresh frame must agree on target identity; an ambiguous or stale target stops.

### Construction facts

The producer must publish the exact empty position/slot identity and construction
family (fixed, large, or small), the menu screen, the one target option, and distinct
controls for normal Build and premium/instant Build Now. It must distinguish an
unavailable option from a selected option and expose a target-specific start receipt:
active construction timer, queue entry, or an equivalent exact target/position
state. A global queue count or a changed screen alone is insufficient. If the menu
contains a requirement or a cost, publish its state and text/amount as facts; do not
make the consumer parse an image or guess a payable amount.

### Upgrade facts

The producer must publish current level and the intended next level, the strongest observable target correlation (HomeCityObjectId plus instance/slot/geometry when available), precondition status and requirement text, normal upgrade control, castle
warning/confirm controls, premium material or speedup controls, and queue status.
Queue status must distinguish idle/available from full, gift/third-queue, or other
known blocked states. A post-dispatch fresh receipt must correlate to the same target
instance and show a started queue/timer or an explicit target-level increase. An empty
queue by itself is never a completion proof.

B's current follow-up owns Resource/Hero/broader Research producers. Building
profiles, controls, and receipts are a separate producer request and cannot be
silently assumed to arrive with that handoff. A owns the typed consumer, reviewed
navigation, policy, durable intent, and caller migration after those facts exist.
Recognition fields, assets, OCR, and screen-anchor changes remain producer-owned.

## Target design and exact contracts

Create two explicit typed workflow operations, using the existing workflow module
conventions and names selected during implementation:

- `BuildingConstructionWorkflow` for one exact home-city object and one validated
  empty position/source.
- `BuildingUpgradeWorkflow` for one exact home-city object instance and one level
  transition.

Each must expose a `WorkflowSpec` with known entry (`PNC_HOME_CITY`), known action
state(s), known exit (`PNC_HOME_CITY` after the receipt), and a declared
`RESOURCE_CHANGING` effect. Each operation accepts typed policy/target data; it does
not accept an arbitrary screen, coordinate, or unvalidated button name.

`WorkflowContext` should provide focused methods for the typed sequence. Reuse
`open_building` and the existing content/confirmation helpers. Add only the
construction-source selection and upgrade action seams that are needed by these two
workflows. Source acquisition may use `CoreRuntime.observe_ready` through reviewed
navigation when the source is published as `PNC_LOADING`; ordinary post-action and
Chat observations continue using raw `observe`. Every final control and target is
revalidated from a fresh frame immediately before input.

Route and source revalidation must reject wrong, missing, stale, blocked, or unknown
screens before input. A loading frame receives only the existing bounded passive
settle through `NavigationCore`/`CoreRuntime.observe_ready`; there is no generic
UNKNOWN retry and no caller-local sleep loop.

Use the existing `CoreMutationBoundary` and journal dispatcher for both actions. The
operation must be durably PREPARED before an actuator call, transition through the
existing journal states, reconcile from fresh observations, and return the existing
`JournaledMutationResult` semantics. A repeated operation id or an already committed
intent is a reconcile/no-op path and may not press Build or Upgrade again.

The current `DailyQuestId.UPGRADE_BUILDING` is the existing Daily identity for upgrade. Construction has no exact Daily quest identity. Before implementation, the shared mutation owner must select a narrow, honest construction capability and durable operation identity that the existing boundary can authorize without representing construction as a Daily quest. Keep construction excluded from automatic Daily, do not overload `UPGRADE_BUILDING`, and do not add a generic mutation framework. The capability must carry exact account/castle/date, one mutation, the applicable diamond budget, and the existing acknowledgement shape.

Add typed branches to `CoreScriptDispatcher` and its step validator only after the
workflow contract is stable. Migrate `task_registry` and direct API wrappers in one
coherent caller patch; `BuildingConstructionTask` and `BuildingUpgradeTask` must not
remain a second mutation path for callers that have migrated. Preserve their target
and policy parameters, but reject unsupported premium/speedup requests before any
navigation or journal write.

## Required behavior

### Normal construction

1. Validate one catalog object, one exact empty slot, and its family/source mapping.
2. Ensure Home City and acquire a fresh source frame. If the source is loading, use
   the bounded ready callback and retain the initial capture in the total budget.
3. Open the exact fixed/large/small construction menu and revalidate the target
   option, normal Build control, and any known prerequisite/cost state.
4. Write the durable intent, then press the ordinary Build control exactly once.
   Build Now is a distinct premium control and is not a fallback.
5. Re-observe fresh content and accept only a target-specific active timer, queue
   entry, or exact target/position start receipt. If the screen is stale, blocked,
   unknown, or ambiguous after dispatch, stop with the existing pending/ambiguous
   journal result and reconcile later; never replay.
6. Return through a reviewed edge to Home only after the receipt is known. Do not
   wait for completion or infer completion from an empty queue.

### Upgrade

1. Validate the exact catalog object, strongest observable instance correlation, current level, and requested next level. A level label without an owning target correlation is insufficient. The source command may use an internal numeric id, but the producer must not fabricate or expose an invisible id solely for this plan; when multiple instances cannot be disambiguated, record that blocker.
2. Revalidate preconditions. `FAIL` mode stops on an unmet requirement; `QUEUE` mode
   may follow the one observed Go/prerequisite route only when its destination and
   return edge are reviewed. Unknown requirements stop.
3. Revalidate queue status. Idle/available is dispatchable. Queue-full, gift, premium
   third-queue, or unknown states stop with a known result; they do not trigger a
   purchase or a second queue route.
4. Revalidate the normal Upgrade control and any castle-level warning. Normal
   resource payment proceeds only from published facts and the explicit policy.
   Warning confirmation is exact and bounded.
5. If policy explicitly allows speedups or premium material purchases, require the
   corresponding typed control and acknowledgement/cap; otherwise reject before
   navigation. No diamond budget is silently increased.
6. Write the intent, press normal Upgrade once, and reconcile a fresh receipt tied to
   the same building instance or strongest approved HomeCityObjectId/slot/geometry/level correlation. The source client calls
   `BuildingSend.UpgradeBuilding(id, queueId=0)`; its id is internal to the client.
   the consumer uses the strongest approved observed HomeCityObjectId/instance/slot/
   geometry/level correlation and must not fabricate an invisible numeric id.
7. Treat a started timer/queue as a start receipt. Treat completion as proven only by
   a fresh exact target-level increase after refresh. An empty queue, unrelated level,
   or generic success panel is pending clarification.
8. Return Home via a reviewed edge after a known receipt. An ambiguous result is
   reconciled from the durable intent and never replayed.

### Original policy branches that remain part of completion

Normal construction is the entire current `BuildingConstructionPolicy` action
contract: it accepts `building` only. Keep fixed/large/small source families and
their exact legal-slot validation. Premium Build Now is a distinct excluded
control, not a new construction mode to add because the user supplied a budget.

Upgrade also retains its priority order/priority-file loader,
`prerequisite_mode`, `allow_speedups` and
`allow_premium_material_purchases`. Port these existing branches through the same
owners where evidence supports them; a normal-only implementation leaves them
explicitly open. Required branch work and acceptance are:

| Branch | Remaining implementation | Required proof |
|---|---|---|
| `FAIL` / `QUEUE` prerequisites | Preserve the distinction between a satisfied Requirement and an unmet prerequisite. In `QUEUE`, keep the originally requested target separate from the actual prerequisite being upgraded, as `_QueuedBuildingPrerequisite` does today. Follow only the observed bounded Go route; stop after the one prerequisite Start. | The intent/receipt names the actual prerequisite, and the result says prerequisite started for the root target. The root building's upgrade must not be reported as started or complete. Tests cover satisfied Requirement, unsupported Go and changed prerequisite target. |
| Optional speedup | Trace the existing active-upgrade/speedup branch and retain the intended target. Consume only qualified item/quantity/Use controls and observed availability/cost under the explicit policy. | Item consumption and the same target's resulting state are correlated; completion requires actual target-level proof. A disappearing timer or empty queue alone is insufficient. |
| Optional premium materials | Preserve the current material-purchase opt-in separately from normal Upgrade and other premium controls. Revalidate item/quantity/cost and the target after any purchase. | Each purchase has its own exact durable intent and receipt; only then may the subsequent upgrade proceed. Unknown purchase outcome stops without another purchase or Start. |
| Existing post-start Help | Inspect `_complete_started_upgrade_at_home_city` and its pending-help path. Preserve the supported observed Help behavior through one constrained operation after the upgrade receipt is already established. | Missing/blocked Help does not erase a valid upgrade receipt or rerun Upgrade. A confirmed build and a failed follow-up/exit remain distinguishable. |

One Build/Upgrade Start remains the bounded primary operation. A speedup or
material purchase is a distinct resource-changing action, not an unjournaled
navigation step hidden inside that Start. The shared mutation owner must supply
exact action identities and finite per-action counts through the existing
boundary before these optional branches are enabled. Reuse persisted receipts
after interruptions; do not increase a one-action policy internally to fit a
multi-action sequence. The user's unlimited authority permits a concrete
supported proof policy; it does not remove these runtime contracts.

Use saved producer evidence and deterministic branch tests first. The first live
proof can be one normal construction and one normal upgrade. Add one smallest
live proof only for a materially different optional mutation boundary whose
current behavior is not established by existing accepted evidence. Report those
branches separately until qualified; do not repeat every building/flag combination.
No extra resource-budget approval is needed for these in-scope actions.

## Implementation sequence

1. Freeze the checkpoint and inspect the current dirty paths. For each next route
   or action, confirm its exact producer fields and fixtures. Park an unqualified
   row with its precise dependency and continue other qualified rows; a construction
   mutation gap does not prevent a supported read-only endpoint port.
2. Resolve the explicit construction durable-id/capability choice with the mutation
   owner. Add the smallest typed domain value and loader acceptance needed for a
   standalone operation, keeping it excluded from automatic Daily.
3. Add typed construction and upgrade observation requirements and workflow models
   in A-owned modules. Coordinate any observation-model field changes with B; do not
   edit B-owned vision or OCR files.
4. Implement the two workflows and their focused `WorkflowContext`/`NavigationCore`
   seams. Reuse reviewed routes, fresh content observation, loading-only readiness,
   exact source revalidation, and existing receipt/reconcile helpers.
5. Add the two typed dispatcher steps and strict validation. Add direct/API and
   authored caller adapters in one patch, preserving parameter semantics and
   removing the migrated legacy mutation call path.
6. Add focused unit/contract/integration regressions, run the smallest repository
   groups, and inspect journal/artifact output. Before accepting a consumer test,
   replay its saved source, menu/detail and receipt images through both real
   production observers with actual RapidOCR and the ordinary semantic request.
   Check the published frame/layout/guard, target, level, requirement, queue row
   and normal/premium control separately. Then feed those observations to the
   typed consumer, preserving distinct frame provenance and pre-action baseline.
   Synthetic policy tests remain useful, but injected OCR cannot establish that
   the real crop plan supplies a consumed field. Fix only a failing behavior evidenced
   by those checks.
7. Acquire the canonical live lease only after offline acceptance. Run one normal
   construction and one normal upgrade representative, or one of them if the first
   proof establishes a shared producer/mutation blocker. Capture exact identity,
   source, control, receipt, journal, and reviewed return evidence. Stop on the first
   unknown or ambiguous state.
8. Promote the caller only after the receipt is reconciled and the no-replay check is
   recorded. Re-run the focused gate against the preserved checkpoint and report the
   exact dirty-path boundary to root.

## Offline validation and acceptance

Use the repository runner and the installed Python 3.13 launcher:

```text
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group unit.app.automation.tasks
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group integration.workflows
C:\Users\lebel\AppData\Local\Programs\Python\Python313\python.exe tools/run_tests.py group contract.entrypoints
```

Select the narrowest groups accepted by the runner and include the exact selected
names in the report. The existing combined affected gate at this checkpoint passed
2,033 tests, with 2,027 passed and six skipped, run id
`c467de4a5dcb42809cef0545c3aa43e6` at `2026-09-13T23:18:18.415109+00:00`; do not
rerun it merely because this plan was written. Documentation-only edits to this
plan require `git diff --check`, not a broad source test run.

The new tests should be small and contract-focused:

- construction accepts the exact family/menu/option and produces a target-specific
  start receipt; wrong source family, missing option, wrong target, stale source,
  blocked menu, premium-only control, and unknown receipt reject before a second
  actuator call;
- upgrade accepts a normal available queue and exact instance receipt; unmet
  prerequisite in `FAIL`, missing reviewed Go in `QUEUE`, full/gift/third-queue,
  wrong-level, ambiguous target, and normal-control absence stop before input;
- warning confirmation is exact; speedup and premium-material branches require
  explicit policy and acknowledgement and never become fallback behavior;
- a loading source settles once within the total observation budget, with its first
  capture retained; ordinary post-action and Chat observation stay raw;
- stale checkpoint, wrong account/castle/capability/date, missing acknowledgement,
  duplicate operation, PREPARED/DISPATCHED intent, and committed intent all reject or
  reconcile without a second Build/Upgrade input;
- direct API and authored dispatcher callers produce the same typed operation,
  journal states, receipt, and return edge;
- Castle, Institute, Warehouse, Goddess Statue, Hero Hall, and Campaign retain their
  existing modeled open/return contracts, with actual Home acquisition requalified
  after the new producer. Each of the 19 added endpoints needs its distinct
  source/destination/return test; do not multiply those route tests by every
  construction/upgrade flag or call a classifier header an independent profile.

A positive test must show exact input and the corresponding fresh receipt. A negative
must show no actuator input or no replay. Avoid tests that merely assert button names
or implementation wording.

After source changes, run the required affected gate on the actual candidate:

```powershell
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py affected --base origin/main --explain --json .test-impact/buildings-selection.json --results .test-impact/buildings-results.json
git diff --check
```

Follow any required full fallback once. Include the prerequisite result, distinct
optional mutation receipts and post-start Help cases above in the appropriate
existing/new consumer contracts. Broad prior passes are not new branch acceptance.

## Live proof and stop conditions

After the offline gate, use `mega_old_acc` with the configured active castle and
canonical process-scoped lease. Select an eligible exact building/slot from fresh published observation under the granted authority and record the target and requested level/empty slot in the execution trace; do not use arbitrary catalog order. Perform exact identity preflight, then one normal construction and one normal upgrade at most. Normal paths use zero diamonds. The user's unlimited
mega_old_acc authorization covers resource spending, so no new spending permission
is needed. Select and record the eligible building/slot as described above; castle
selection/return remains package 06's separate identity-controlled boundary.

Capture the initial identity, source profile, control coordinates/ids, fresh
pre-dispatch frame, durable intent, post-dispatch frame, receipt, journal transition,
and reviewed return. Store redacted artifacts under
`.local-data/artifacts/core_resume/` with a unique run directory. If a screen is
loading, only bounded ready settlement is permitted. If the result is UNKNOWN,
stale, blocked, wrong-target, or ambiguous, stop, preserve the dispatched intent,
and reconcile from observation. Do not replay the same operation. Start acceptance
does not require waiting for completion. When a supported optional speedup branch
is being qualified, choose its finite action/quantity policy within the existing
user authority and require the fresh exact target-level receipt; do not ask for
the same spending permission again.

Acceptance is one exact target-specific start receipt for each attempted operation,
correct journal state, no duplicate input, and a confirmed Home return. A started
queue is enough for normal Start acceptance. Optional speedup, purchase, queued
prerequisite and Help branches retain the separate acceptance cells above; one
normal happy path must not mark the full legacy policy contract implemented.

## Evidence and version caveats

The finite endpoint inventory is
`.local-data/artifacts/core_resume/a11_endpoint_inventory.json`. Its source
requirements are the historical 25-target smoke in `tests/test_live_home_city_map_smoke.py`
and the canonical catalog/workflow/navigation symbols listed in the artifact. The
six supported endpoints are Castle, Institute, Warehouse, Goddess Statue, Hero Hall,
and Campaign. A11's old validation note saying five is stale relative to the current
Campaign mapping and reviewed Campaign-to-Home edge.

Building source evidence is in
`docs/game-reference/workflows/building-upgrade.md` and the source map. The package
is build 5.0.203/version code 233; the latest live footer is 5.0.204.235. The
inspected client symbols are:

- `uis/building/buildingupgradewin.lua:OnUpgradeHandler` and
  `CheckResIsEnough`: precondition, resource/premium branch, queue status, castle
  warning, and normal upgrade dispatch;
- `commands/building/buildingcommand.lua:BuildingSend.CreateBuilding`,
  `DoneFastCreate`, `BuildingSend.UpgradeBuilding`, and the corresponding
  `command.CreateBuilding`/`command.UpgradeBuilding` handlers;
- `datas/buildingdata.lua:GetIdelCoolStatusType`,
  `CheckBuildPreconditionIsPass`, `GetEmptyPosForBuild`, and
  `GetBuildDataForId`.

These are versioned client evidence, not server or current-live proof. Source
responses update queues/building DTOs but do not by themselves prove completed level
or payment acceptance. Base resource tables do not establish displayed payable
costs after modifiers. The worker must use the current published observation and
live receipt for acceptance.

## Permission, configuration, and unresolved choices

| Item | State and required action |
| --- | --- |
| Account/resources | Granted: `mega_old_acc`, all in-game actions/resources, unlimited budget. Do not re-request spending approval. |
| Workers/network | Keep workers offline during implementation and offline gates; live execution uses the assigned canonical lease only after those gates. No direct service calls, APK changes, or other worktree edits. |
| Castle/identity | Exact active castle, account identity, and target building must be preflighted from configured roles; do not switch them. |
| Construction target | Select an eligible exact `HomeCityObjectId`, empty position, and normal construction source from fresh producer observation during the bounded proof; record the choice and evidence. |
| Upgrade target | Select an eligible exact building correlation, current level, next level, and applicable prerequisite policy (`FAIL` or `QUEUE`) from fresh observation during the bounded proof; record the choice and evidence. |
| Mutation authority | Resolve the narrow construction capability/durable operation identity and local boundary/policy integration with the shared owner; preserve one mutation and the existing policy budget. |
| Premium behavior | The current authority grants in-scope actions and resources. Preserve upgrade's explicit premium-material/speedup policies through exact runtime authority. Construction Build Now remains outside the existing construction policy; do not add it as a new feature. These are contract boundaries, not another resource-permission question. |
| Producer facts | B/other producer must supply independent replacement profiles, controls, typed level/queue/receipt facts, and saved evidence. A consumes these facts. |

Technical decisions and evidence gates before implementation or live dispatch:

1. The shared mutation owner must select the exact typed construction capability and durable operation identity that the existing boundary can authorize without representing construction as a Daily quest. Do not overload `UPGRADE_BUILDING`.
2. At execution, select one currently observed eligible empty slot and one upgrade instance for the bounded proof; record the evidence rather than inventing a building, level, source, or queue state.
3. The producer evidence must distinguish normal Build, prerequisite, and premium-only routes. The consumer stops if it cannot.
4. Qualify the strongest observable target-specific receipt for the current live build. A source response or empty queue is not enough.
5. Preserve the existing speedup/premium and `QUEUE` branches as explicit policy paths; each requires its producer control and receipt facts. The bounded first proof may use the normal path, while unsupported branches remain an evidenced dependency rather than a silent fallback.

## Copyable worker kickoff

```text
Work in C:\Users\lebel\pnc\.local-data\worktrees\workflow-recognition-integration
from the verified current HEAD plus preserved dirty source. Read this whole plan
and the shared ownership register. Retain all 19 remaining original A11 routes
and the full original construction/upgrade policy branches. Reuse B's published
Farm, queue, level, prerequisite and Hall subsets, but require actual current
Home object publication, independent destination identity and a reviewed return.
Park each missing producer predicate and continue independent supported rows;
do not replace it with consumer OCR or coordinates. Resolve the narrow standalone
construction capability through the existing shared authorizer/journal owner,
then port the workflow and direct/authored callers with one dispatch/no replay.
Keep normal Start, queued prerequisite, speedup, material purchase and Help
acceptance distinct. Use real both-observer saved replay plus focused runner
checks before one smallest canonical leased mega_old_acc live proof per new
material boundary. Existing unlimited in-game authority needs no repeat budget
question; use exact finite action/target policies and durable receipts. Preserve
other workers' files, publish shared-file ranges before editing, and report exact
remaining rows/branches, test results, artifacts, journal and Home/cleanup outcome.
```
