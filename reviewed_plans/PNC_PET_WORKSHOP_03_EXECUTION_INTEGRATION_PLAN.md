# Pet Workshop 03 — Observed execution, independent runs and Daily Maintenance

Date: 2026-09-16. Design plan; [current packet status and next assignment](PNC_PET_WORKSHOP_ROADMAP.md).

## 1. Outcome and entry points

Implement one canonical Workshop workflow that operates selected eligible castles until observed zero energy or a specific permitted stopping condition. Make it available both as an **independent Workshop run** and as the final Workshop phase of **Daily Maintenance**. Both entry paths must use the same state, solver, legal-action validation, executor, mutation authority and journal.

Dependencies: [Plan 01 shared contract/recognition](PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md), [Plan 02 solver/policy](PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md), and the current canonical runtime. The [Feature 06 native-RGBA identity regression](PNC_CORE_REMAINING_06_CASTLE_NAVIGATION_PLAN.md#september-16-regression-native-screenshot-drops-the-selected-hopium-row) must be closed before unattended target selection is accepted. Do not duplicate its fix here or replace failed preflight with a configured expected name or agent visual assertion.

The exact interview decisions are owned by [Plan 01 section 2](PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#2-agreed-behavior-shared-by-the-three-plans). In particular: exactly two order pieces, reserved higher-priority progress, current bar only with the limited Fruit 5/Statue 5 recycling exception, immediate zero stop, all four ordinary mechanics, and at most 60 seconds of cooldown-only waiting.

Read [the canonical workflow porting contract](../instructions/CORE_WORKFLOW_PORTING.md) before implementation. This plan adds the Workshop behavior to those owners; it does not introduce a parallel game runner.

### Required public behavior

- Add `TaskId.PET_WORKSHOP` with one validated parameter type and a replacement-core authored binding.
- Add `pet-workshop` CLI and corresponding direct Python API/application method, accepting explicit selected account/castle aliases through the existing configuration/target resolution. Reusable authored routines may include the same task and existing castle-repeat blocks.
- Add an optional typed Workshop setting to each existing Daily Maintenance target. It is separate from `DailyQuestId` and Daily quest capabilities. When enabled, call the same Workshop workflow after that castle's existing work, on every maintenance invocation, with a fresh state read.
- Keep normal Daily scheduling/configuration ownership unchanged. No new scheduler, Codex heartbeat, background daemon or automatic modification of local account configuration is part of this work.
- Independent Workshop runs do not claim Daily quests, require a fictitious Daily row, or run the other maintenance phases. Daily calls do not nest a second ScriptRunner or independently acquire a competing connection/lease.

## 2. Canonical owners and necessary extension

| Concern | Existing owner and scoped change |
| --- | --- |
| Workflow lifecycle | `CoreWorkflowRunner`, `WorkflowSpec`, `WorkflowContext`: add the typed Workshop workflow/context seam with known Home entry/exit and resource-changing effect. |
| Capture/content | `CoreRuntime` with the shared Plan 01 parser through current observers; one fresh persisted frame and frame-owned controls. |
| Navigation | `NavigationCore` / `reviewed_navigation_edges`: Home → Illusory Beast Manor → Pet Workshop, information panels and observed returns. Add actual Manor identity to the Home catalog if absent; do not use Trap Workshop. |
| Gestures and guards | Existing `ObservedActionExecutor` and typed action requests: measured tap/drag targets, popup/freshness checks and post-action observation. Add the smallest typed two-cell drag operation if no current operation expresses it. |
| Feature execution | A focused Workshop session/executor in the application automation layer; translates typed intents into the existing guarded operations and interprets receipts. No raw actuator on the solver/workflow context. |
| Authority | `CoreMutationBoundary`, `DailyMutationAuthorizer`, acknowledgement parser/model: extend exact feature-action support already used by building actions. |
| Durable state | `JournaledMutationDispatcher` and `DailyRunJournalStore`: preserve pending intents/receipts and store scoped Workshop invocation progress through this same owner. |
| Entry points | `ApplicationRunner`, direct API/CLI, authored registry and `CoreScriptDispatcher`: thin adapters to the same workflow. |
| Daily composition | Existing Daily connected runner and `DailyMaintenanceApplicationService`: add Workshop after current castle work, using the same connected graph and instance grouping. |

PW06 owns the feature identity/budget extension in `WorkflowSpec`, scope/invocation factory, authorizer, durable dispatcher and journal migration/query lifecycle. It accepts the typed target/policy explicitly and does not depend on optional Daily configuration or CLI/TaskId registration. PW07 owns the connected Workshop action session, UI-result interpretation, `WorkflowContext` methods and the connected action methods of `CoreMutationBoundary`. PW07 supplies the dispatcher callbacks and calls the actual shared policy validator. This keeps authority/persistence independent of recognition while retaining one canonical observed execution path.

### Exact feature identity, authority and budgets

At the planning baseline, `WorkflowSpec.mutation_action_kind` and acknowledgement/journal decoding accept `BuildingMutationKind`; `require_building` is the non-Daily authorization seam. Extend this to typed known feature action kinds, including Workshop, through one canonical parser/validator. Migrate the existing building callers to the generalized exact-feature method and remove the superseded method. Preserve building identities and receipt meanings; never accept arbitrary unvalidated strings or add Workshop to `DailyQuestId`.

Separate **authorization of one Workshop invocation** from the count of its individual game operations. Existing one-Start or `max_claims` limits must not be reused as an accidental five-action/200-action cap on a full Workshop run. The existing generic `TaskExecutor` retry/replan defaults are also not its lifecycle owner.

Extend the current authority model with a small explicitly tagged **observed Workshop bar budget**, alongside the existing counted-operation budget. It authorizes one exact selected castle invocation, the agreed permitted action set, zero premium spend, and only these energy sources: the observed bar, observed natural/automatic gains, and the restricted observed recycling result. It stops at observed zero and cannot refill from inventory or consume energy pieces. This is a closed resource policy, not an arbitrary `unlimited=true` flag. Existing counted budgets retain their semantics; bounded live canaries can continue using an exact counted action budget through the same authority.

Keep this representation and validation in the existing authority/acknowledgement owner; do not build another Workshop approval service. Validate target, role, supported budget form and policy before connection, then validate observed identity/resource facts before each action. The active scope must distinguish a new authorized invocation from continuation/reconciliation of a pending one.

Use this concrete normalized authority contract:

| Field | Contract |
| --- | --- |
| `account_id`, `castle_ref`, resolved castle | Existing configured identifiers and exact resolved identity; aliases resolve before connection and identity is later proved live. |
| `action_kind` | Typed `pet_workshop.run` scope; individual journal intents carry typed Workshop sub-actions such as produce/feed/recycle/submit. The scope covers only the implemented allowed intent set, not arbitrary feature strings. |
| `budget.kind` | `observed_workshop_bar` for a normal run, or the existing counted-operation budget for a bounded named canary. The observed-bar tag has the closed energy-source and zero-stop meaning defined above; do not repeat independently editable energy allowlists in each adapter. |
| `budget.max_diamond_spend` | Exactly zero for Workshop. |
| `maintenance_date`, `game_reset_id` | One shared run-boundary factory supplies the existing America/Toronto local date and midnight-UTC reset identity. Extract the existing calculation from `_run_daily_maintenance` into that owner and migrate its caller; standalone Workshop uses it without loading Daily quest policies. |
| `invocation_id` | Generated once by the canonical application composition after scope validation and unresolved-intent lookup, persisted before mutation. All connected adapters reuse it. It is not a user-entered daily completion flag. |

CLI acknowledgement input uses the existing `--acknowledgement` mechanism with `account_id`, `castle_ref`, `maintenance_date`, `action_kind: "pet_workshop.run"` and `budget: {"kind": "observed_workshop_bar", "max_diamond_spend": 0}`. The factory supplies/validates reset and invocation identity; direct API and Daily composition construct the same typed representation. Existing counted Daily/building acknowledgement forms normalize to their existing counted-budget meaning in this same parser. An authored step receives its scope from the outer invocation, never a secret approval flag inside the script.

Direct invocation and enabled Daily target configuration are composed into the same exact Workshop scope using the existing invocation-authority boundary. Scheduled use must not require a question before every piece or every day; an explicitly enabled target/policy supplies that recurring behavior within the existing automatic-run controls. Do not silently enable global automatic runs or unrelated capabilities. Local account YAML/roles are not changed by implementation unless separately requested.

Track confirmed production dispatches and observed gains separately for reporting. Starting energy minus ending energy is not a spend counter. Do not optimistically credit an expected recycling reward, assume capacity 200 is a lifetime run budget, or use an unseen remaining-use count to authorize more production.

### Persistence and migration

- Reuse the existing reset/account/castle checkpoint and mutation-intent lifecycle. Add only the typed Workshop progress needed to retain invocation ID, operation sequence, pending operation reference, latest stop/result and energy/reward evidence. Reconstruct board/goal/reservations from fresh observations, not a durable shadow board or queued gestures.
- Assign operation IDs once per planned operation from the persisted invocation/sequence. A resumed operation retains its ID. A new healthy invocation has a new ID even on the same day; frame fingerprints are evidence, not a substitute for operation identity.
- Persist intent before the first consumptive gesture, record dispatch through the canonical dispatcher, then commit the observed result. Multi-step recycle confirmation is one operation: journal before the earliest control that can immediately delete, and never restart it blindly after an ambiguous response.
- An unresolved dispatched operation stops further mutations on that physical instance for the current run. Persist the pending operation against its resolved account/castle identity, not a permanent instance-wide quarantine. A separate later authorized invocation may use another explicitly selected castle after fresh identity and safe-screen validation; it may not replay or clear the original castle's pending operation. For the affected castle, allow one bounded read-only reconciliation and retain the pending outcome if current evidence cannot settle it. A new operation ID, entry point or maintenance/game-reset date does not clear that block. PW06 must add/use the same `DailyRunJournalStore` query for unresolved Workshop intents for the exact resolved account/castle across reset partitions before creating its new invocation, returning original checkpoint/operation references. Do not restrict lookup to today's file, evade identity through a different alias, or add a parallel journal or persistent instance-block service.
- Extend the checkpoint schema with an explicit version transition. Read existing supported checkpoint data into the new canonical representation and write only the new representation on the next atomic save. Preserve historical Daily/building intents and receipts. This is a required persisted-data migration, not a parallel legacy executor/fallback.
- Do not add Workshop to `completed_quest_ids`. A successful zero-energy visit is a run result, never a once-per-day lockout. A later Daily invocation may use newly regenerated energy after fresh validation.

## 3. Workflow, gestures and receipts

### Invocation lifecycle

1. Validate explicit aliases, duplicates, available role/capability, policy and mutation scope before connection. Reuse existing multi-account reservation and physical-instance grouping; preserve configured cleanup and pre-existing emulator instances.
2. Use canonical account/castle preparation and exact active identity preflight. Each invocation requires fresh identity and safe-screen evidence, including a later invocation that selects a different castle after a prior instance stop. Check pending operations for the resolved target through PW06. Skip only a castle **confirmed** below C24. Unknown identity/level is not an applicability skip. Read each eligible castle's actual Workshop level/board.
3. Enter through reviewed Home → Manor → Workshop edges and qualified controls. Construction of the connected runtime must not navigate. No saved coordinate tap harness is promoted into the product.
4. Capture state, survey reachable orders, call the pure planner and revalidate its intent against the fresh state and scope. Resolve geometry only through that frame's measured view. A stale proposal returns to observation/planning before any gesture.
5. Perform at most one logical action, obtain its settled result, persist any receipt and replan. Selection-only is a separate action when needed. Do not batch a double tap, repeated production, merges or submissions from a predicted board.
6. Observe energy and any level/modal transition after each action. Observed zero ends gameplay immediately, before a ready submission, recycle or cooldown wait. Normal return navigation may still complete the declared Home exit.
7. For a continuous cooldown-only episode, use a monotonic deadline of 60 seconds. Passive observations do not restart it. A genuinely useful completed action ends the episode. At the deadline, record cooldown-blocked and move to the next safe target; no new delayed revisit/scheduler is introduced.
8. Confirm the declared Home exit for normal completion/applicability/known blockage. Unknown UI or uncertain mutation stops the affected instance with its evidence; no speculative `finally` navigation or automatic replay. Existing explicit safe popup recovery remains with its current owner.

The Workshop workflow owns its repeated observe/plan/execute lifecycle through the core binding. Bypass the obsolete generic short task retry loop for this task, as other replacement-core bindings do. Do not globally raise retry counts. Use semantic no-progress detection: a settled no-effect result or repeated inspection without new facts cannot lead to the same mutation being issued indefinitely. Legitimate production is allowed to exceed five replans and to produce the same item type on successive distinct actions.

### Order survey and freshness

Use a bounded horizontal strip scan with the existing navigation/observation policy and stable end/repeated-viewport detection. Include partially clipped edge cards only after full reacquisition. Survey the currently reachable UI, without claiming that hidden future server orders were discovered.

Invalidate requirement/availability coverage after Produce, Merge, Activate, Feed, SubmitOrder, Recycle, or observed board changes during waits/automatic processing. Before the next order-dependent decision, perform one bounded resurvey. Selection alone does not invalidate requirement facts; scrolling and closing information panels invalidate clickable card geometry. Cache immutable catalog/template work, not stale card positions. This rule covers the observed reorder/reset and the client display of newly ready hidden orders without inventing permanent order IDs.

If two cards have the same requirements/rewards, use fresh measured instance geometry for the intended card. A repeated signature is not proof that a prior submission failed. Submission receipt ambiguity must not trigger a second tap.

### Operation-specific validation

For all resource-changing operations, require exact target identity, fresh unblocked source, canonical `validate_intent`, matching authority and a durable intent. Source evidence must permit a meaningful result check; otherwise inspect before acting.

| Intent | Dispatch and required result |
| --- | --- |
| Select | Tap a known selectable, known-unselected cell once. Confirm selection without attributable production/consumption. Passive regeneration does not invalidate selection. |
| Produce | One tap on a known selected, Normal, available producer with energy and space. Observe a new item in a previously empty usable square and consistent producer/energy state. Ordinary generator, finite disappearance or configured transform are separate qualified result forms. Never assume spawn adjacency or the next random item. |
| Merge / generator upgrade | Drag two known equal Normal pieces with a successor. Observe source empty and destination successor; do not call a swap successful. Refresh selection and any new producer/level state. |
| Activate | Drag a matching Normal piece onto the known inactive piece. Client merge code predicts the catalog successor; require the settled successor and activated usable state. Bubble/level-lock interactions are excluded. |
| Feed | Drag the exact Normal feed ingredient onto its feed-locked generator. Recovered `OnDragEnd` calls `MergeGridUnLock(..., false)` for this direction: food source clears, generator remains at the destination and becomes Normal. Qualify that settled result before promotion. |
| Recycle | Revalidate full-board blockage and allowed unreserved item, select safely, then use the measured recycle control and any observed confirmation. The client can act immediately when its confirmation preference is disabled, so journal before the first recycle control. Observe exactly that piece removed and the current recovery/energy result. Do not change the confirmation preference. |
| SubmitOrder | Reacquire the exact fully identified ready two-piece card and submit once. Verify required ingredient multiset consumption and settled completion/removal/replacement of the target. The game chooses duplicate cells; card movement alone is not a receipt. |
| Inspect / Wait | Use only reviewed information/navigation controls or passive capture. Unknown selection must not turn an inspection tap into reward-piece use. No mutation retries or recovery purchases. |

`MergeAdventureGridOperation:MergeGrid` and `MergeGridUnLock` update client-side grid animation before their request finishes; `command.Compose` later reconciles server DTOs. The first changed frame is therefore insufficient. Use the canonical settled observation policy and retain before/after evidence; if a server correction reverses or obscures the transition, record no-effect/uncertain rather than dispatching again. Do not claim network-level exactly-once delivery from screenshots.

Exact remaining finite uses are not required for one otherwise visibly valid, qualified production action. Never populate that hidden count from the configured maximum or historical tap count. After observed depletion, remove/transform the producer in the current state and let the same planner choose the next recipe. Unknown **availability/status** blocks a production attempt; unknown **remaining count** alone does not make all finite generators permanently unusable.

Advertised rewards and verified receipts are distinct. Report completed orders and their advertised rewards, labeling expected versus observed quantities. Capture an available reward/result surface as part of the same action; do not add whole-account inventory tours solely to prove every reward balance. A recycling value encoded in the packaged catalog is not a verified current bar credit. If it produces an unexpected inventory-only reward or a contradictory transition, retain the evidence and stop that action path rather than consuming inventory to compensate.

## 4. Independent runs, Daily integration and failure results

### Independent API, CLI and authored task

The independent CLI accepts the existing `--config` and repeated `--target ACCOUNT_ID CASTLE_REF` pairs, preserving their order within each physical instance. The direct API accepts the corresponding typed target sequence and mutation scopes. Resolve these through the existing account/castle alias owner; the new flag is only an input adapter, not another alias database. Compose one authorized Workshop invocation per selected castle and return structured results. Authored `PET_WORKSHOP` steps use the existing `castle_ref`/repeat-block syntax, prepared target and same workflow factory. Do not create one YAML wrapper per target.

The planner's fixed user defaults belong to one typed Workshop policy. Expose only invocation inputs with current value: targets and supported execution/validation budget. Do not expose a large optimizer-weight/retry/fallback configuration surface. The cooldown policy and allowed resource actions are represented canonically, not copied as CLI/Daily constants.

Direct runs require no Daily quest scan or claim acknowledgement. They still use the shared authority/checkpoint infrastructure with a feature identity and the applicable configured time/reset context.

### Daily Maintenance

Add an optional `pet_workshop` policy/enablement to the existing target model/loader and a sanitized example. The existing `capabilities` mapping retains its Daily quest meaning. Enabling Workshop applies only to the explicit eligible target; targets without it retain current behavior.

Refactor the connected claim-only runner into one accurately named connected Daily runner as it now composes more than claims. Migrate factory/callers and remove the obsolete class/name; retain the existing canonical claim workflow. Run the claim/current maintenance work first, then invoke the same Workshop workflow using the same connected core and outer reservation. Do not call the public connection-opening API from inside the connected phase.

A normal earlier task result, including a known applicability skip or exhausted daily claims, does not suppress an enabled Workshop phase. A pre-existing unsafe/unknown UI, failed identity or uncertain mutation prevents further actions on that instance. An explicitly disabled/unpromoted capability remains disabled; adding Workshop must not broadly promote all older Daily capabilities.

PW09 maps earlier Daily results through PW07's [canonical continuation decision](#continuation-and-later-invocations). Workshop starts only when that decision is `CONTINUE` and the required fresh Home evidence exists. A claim result containing unresolved unknown UI rows does not become safe merely because a broad exception handler returned a summary. `_run_instance` respects `STOP_INSTANCE` instead of catching it and blindly continuing.

Run Workshop on every maintenance invocation, including twice on the same day after an earlier zero-energy completion. It starts from current energy/board and checks unresolved receipts first. Do not use a Daily completion flag, cached zero value or cached goal to skip it.

### Results and isolation

Use a typed Workshop run result inside the existing application summaries, rather than inventing DailyQuest rows/outcomes. Distinguish:

- Completed with observed zero energy.
- Applicability skip: confirmed C24 prerequisite not met or explicit policy disabled.
- Known stop: board blocked, cooldown timeout, or no eligible useful goal, with actual remaining energy.
- Recognition/unknown-surface failure or uncertain action: affected instance stopped with evidence/pending operation.
- Explicit bounded-validation limit reached: a canary result, not a claim that the full run reached zero.

Include target, initial/final observed energy, confirmed production count, completed order counts/advertised rewards, recycling observations, stop reason and artifact/receipt references. Avoid inventing exact total spend from bar subtraction or exact rewards from previews.

### Continuation and later invocations

PW07 owns one canonical classifier returning only `CONTINUE` or `STOP_INSTANCE`, reused by direct batches and Daily composition. Success/applicability skip and a known stop with its required freshly confirmed Home exit permit continuation. Failed identity, unknown/unresolved surface, uncertain dispatched action, failed exit or an exception without proven safe state stops the instance. Keep the detailed outcome/stop reason in the typed run result; do not duplicate it in multiple continue variants or maintain independently mutable continuation flags that can disagree with the outcome/evidence.

At the baseline, `DailyMaintenanceApplicationService._run_instance` catches a castle exception and tries the next castle. Replace that behavior for unsafe results with the shared classification: stop the remaining targets on that physical instance for this invocation, preserve the first reason, and let independent instance workers continue. A known blockage with a verified normal exit may continue to the next selected castle. No caller invents its own failure policy.

For a separate later authorized invocation, resolve its explicitly selected targets and validate current identity and screen safety again. Another castle may run on the same instance if those checks pass. The original castle remains blocked by its own unresolved journal operation across aliases, entry points and dates until reconciliation settles it. Do not automatically restart a failed invocation or reorder/switch targets merely to bypass its stop. No persistent instance quarantine or new recovery/scheduling service is needed; the existing target journal and current-run sequencing own the two lifetimes.

Prove this with an offline A/B invocation scenario: an uncertain action on castle A stops later castles on that instance during the first invocation; a later invocation explicitly targeting B succeeds after fresh validation while A's record remains pending; a later A invocation attempts only the permitted reconciliation and cannot dispatch again while it remains unresolved. Failure to establish fresh identity/screen safety still stops B's invocation.

## 5. Separate implementation and qualification packets

| Packet | Deliverable |
| --- | --- |
| [PW06](pet_workshop_packets/PW06_AUTHORITY_JOURNAL.md) | Canonical feature authority/budget, invocation factory and journal migration/reconciliation lifecycle. |
| [PW07](pet_workshop_packets/PW07_WORKFLOW_EXECUTION.md) | Observed action session/receipts, Workshop lifecycle, routes/survey and common continuation/results. |
| [PW08](pet_workshop_packets/PW08_INDEPENDENT_RUNS.md) | Independent CLI/API and authored-task binding. |
| [PW09](pet_workshop_packets/PW09_DAILY_MAINTENANCE.md) | Daily Maintenance adapter and invocation/isolation behavior. |
| [PW10](pet_workshop_packets/PW10_LIVE_QUALIFICATION_INTEGRATION.md) | Lead combined review, bounded live qualification and final integration. |

The [roadmap](PNC_PET_WORKSHOP_ROADMAP.md) owns dependencies, statuses and dispatch. PW06 can finish after PW01, independently of recognition/solver work. PW07 consumes PW02/PW04/PW06; PW05 does not block its offline implementation. PW08/PW09 start independently from the same accepted PW07 implementation. PW10 owns the live acceptance ledger, including the available target/window, exact action budgets and pending transitions; it cannot be replaced by worker offline handoffs.

## 6. Tests and completion

Required offline checks:

- Shared policy and fresh geometry gate every mutation; zero blocks Submit/Recycle as well as Produce; selected reward pieces cannot be consumed through Inspect.
- Settled success, optimistic intermediate state, no-effect and ambiguous receipts for each changed action kind; duplicate consumption checked as a multiset; forbidden replay after failure/crash/exit failure.
- Finite producer disappearance/transform and exact food-to-generator result without inventing remaining uses; partial/unknown relevant status never authorizes a trial tap.
- Recycle allowed IDs/full-board/reservation guard; confirmation-on and confirmation-disabled flows; no optimistic energy credit or inventory compensation.
- Existing checkpoint migration preserves Daily/building receipts; the affected castle's pending Workshop work remains blocking across aliases, independent/Daily calls and reset boundaries. A separate later invocation of another selected castle requires fresh validation and preserves that pending record. A completed prior run does not block a healthy later invocation.
- Direct CLI/API/authored and Daily route to one workflow; no legacy TaskExecutor replay/five-replan limit; one core/lease per connected phase; construction does not navigate.
- Daily ordering after earlier work, repeated same-day invocation, target policy omission/enablement, C24 skip versus unknown identity, per-castle progress, and current-invocation physical-instance failure isolation. Verify the same two-way continuation decision in both callers, with detailed reasons retained separately.
- Cooldown monotonic 60-second ceiling, no reset from passive polls, known full-board/cooldown continuation to next safe castle and no automatic scheduled revisit.
- CLI/result serialization separates observed completion, expected rewards, known stops and failures; invalid target/budget/policy fails before connection.

Run focused groups through `tools/run_tests.py`, then `py tools/run_tests.py affected --base <accepted-base> --explain`. Shared authorization/schema integration and final combined integration justify `py tools/run_tests.py full`. Check `git diff --check` and relevant authored config/document links. Do not repeat full suites or live actions after passing checks without a new change or material unresolved concern.

Dependency sequencing and worker instructions are maintained once in the [roadmap](PNC_PET_WORKSHOP_ROADMAP.md). The live proof obligations are maintained in [PW10](pet_workshop_packets/PW10_LIVE_QUALIFICATION_INTEGRATION.md).

**Definition of done:** all three packages are implemented through their canonical owners; required offline and material live checks pass; independent and Daily runs both work with the exact selected policy; documentation explains extension and limits; superseded task-owned implementations/callers are removed; and the final source-control state and any remaining scope limitation are reported accurately. The present task writes plans only.
