# Remaining package 04 — Campaign selection through battle preparation

Planning snapshot: September 14, 2026. This is A16's remaining implementation and
validation contract for one vertical Campaign owner. It includes the
feature-specific producer and consumer work needed by Campaign, and does not
include battle execution. Read the
[independent package contract](PNC_CORE_WORKFLOW_PORTING_PLAN.md#six-remaining-agent-packages)
for shared scope only; this plan's named Campaign partitions govern its feature
files and symbols. The execution base is the immutable merged revision
`6bc27585fbac1244672cf4a653ea6248955a4aca`; do not rely on a dirty predecessor
or wait for a peer release. Status: implementation may proceed; acceptance still
needs qualified mode/eligibility, Hero Formation and safe-return evidence.

### Saved evidence locations

Historical ignored `core_resume/` evidence resolves under
`C:/Users/lebel/pnc/.local-data/worktrees/workflow-recognition-integration/.local-data/artifacts/`.
Historical B `.local-data/reports/` diagnostics resolve under
`C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation/.local-data/reports/`.
Other numbered capture paths use the exact roots in the linked capture-findings
record. Read these saved artifacts in place; they are not copied into a new
feature worktree. Tracked fixtures arrive with the merged base. Put this feature's
new captures, replays and reports under its own ignored `.local-data/` and test
selection under `.test-impact/`. Missing historical evidence is reported with its
exact source path, never replaced by a guessed current screen or invented result.

## Outcome and exact scope

The existing Campaign caller must select an eligible stage according to its
canonical policy, open the distinct battle-preparation surface, return a typed
receipt of reaching it and finish through a reviewed Home exit. This removes the
remaining legacy Campaign dispatch while preserving the original stop before
battle. The result records that preparation was reached; Home is the final
workflow exit, not a substitute for preparation evidence.

Retain `CampaignPolicy.enabled_modes` and `CampaignMode.STANDARD` / `ELITE`,
including caller order and default Standard policy. Preserve the original
selection semantics unless actual evidence establishes that they cannot be
implemented as written; report that conflict before changing user-visible policy.
An unobserved mode is unknown, not Standard. Selecting a stage and starting its
battle must remain separate operations even when both buttons read Challenge.

Completed Campaign map/chapter/stage entry and return routes, existing fixtures,
and the general replacement runner are prerequisites to reuse. Do not rebuild
them. Do not add hero optimization, battle execution, sweep, AP replenishment,
reward claims, automatic Daily or a global Campaign catalog.

The actual endpoint contract still needs one explicit reconciliation. The core
already has `ScreenType.PNC_BATTLE_PREP` and `campaign_flow_screen_types()` treats it
as the Campaign preparation endpoint, while the saved current sequence reaches the
distinct `ScreenType.PNC_HERO_FORMATION` surface. A Hero Formation frame must not be
silently relabeled as `PNC_BATTLE_PREP`, and a generic `Hero Formation` page must not
be accepted as preparation without the stage transition that opened it. The
consumer should accept the independently published `PNC_HERO_FORMATION` only as
the fresh result of its own exact stage-to-preparation transition. Preserve the
stage snapshot and formation snapshot separately in the typed preparation result;
do not invent an intervening `PNC_BATTLE_PREP` screen or publish two primary screen
identities on one frame. Migrate this caller's old BATTLE_PREP-only postcondition.
Do not add all generic Hero Formation pages to the global Campaign-ready family;
other Hero formation flows must remain distinct. This is a technical contract
change owned by the producer/consumer owners, with no additional user permission.

### Current evidence boundary

Use saved captures as evidence inputs and do not replay a completed battle merely to
qualify recognition. The exact captured facts are:

| Saved frame | What it proves | What it does not prove |
| --- | --- | --- |
| `0087_campaign_stage6_5_detail.png` | Human-reviewed stage-detail appearance for `[6-5] Marsh of Tear`; `AP 120/120`; visible Challenge cost `20` and close control. Expected producer identity is `PNC_CAMPAIGN_STAGE`. | A qualified producer identity/control profile for this stage, mode/eligibility metadata beyond what is visible, or a battle-preparation receipt. |
| `0088_campaign_stage6_5_challenge.png` | Distinct `PNC_HERO_FORMATION` surface with `Hero Formation`, five selected hero cards/check marks, and a bottom Challenge label. | Current stage, mode, AP, cost or eligibility. Those facts are absent and must not be carried forward from `0087`; its Hero Formation header/control profile is currently unmatched. |
| `0097_campaign_victory_receipt.png` | A historic Campaign Victory/result frame after a battle. | Preparation acceptance for this package. Victory/result automation is conditional on a separate consumer requirement and remains outside the stage-to-preparation endpoint. |

The current Campaign producer is narrow: `pnc_observation_enricher.py` publishes the reviewed
Chapter 10/stage 3 rows and the stage 10-3 Challenge profile only. It does not prove
the saved 6-5 Marsh of Tear stage, displayed AP/cost, mode/eligibility, or the
Hero Formation layout. Both `0087` and `0088` are currently unmatched producer
coverage. `0097` has no published Victory selector and is not an implementation
target here. Production-safe `UNKNOWN` or an absent profile is an explicit coverage
gap, never completed Campaign support.

## Starting gate and evidence to inspect

1. Work from the immutable merged base
   `6bc27585fbac1244672cf4a653ea6248955a4aca` in the assigned isolated copy.
   Record the revision and clean-start status in the plan evidence; there is no
   dirty A baseline to preserve and no peer release to await.
2. Read `AGENTS.md`, the applicable write-code/live skills,
   [CORE_WORKFLOW_PORTING](../instructions/CORE_WORKFLOW_PORTING.md), the current
   [coordination document](PNC_AB_COORDINATED_CONTINUATION.md), and only the relevant
   [validation ledger](PNC_CORE_PORTING_VALIDATION.md) sections.
3. Inspect `pnc_automation/app/automation/tasks/campaign_task.py`,
   `pnc_automation/app/pnc/domain/policy_models.py`,
   `pnc_automation/app/automation/engine/navigation_core.py`,
   `pnc_automation/app/automation/engine/core_workflow.py` and the current Campaign
   registry/caller bindings. Locate all `TaskId.CAMPAIGN` and public `campaign`
   call sites with `rg`; preserve their validated parameter/result behavior.
4. Read [Campaign navigation source evidence](../docs/game-reference/workflows/campaign-navigation.md)
   and the [capture findings](PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md).
   `campaign_map.png`, `campaign_chapter_10.png` and `campaign_stage_10_3.png`
   have provenance in `tests/data/screen_recognition/replacement_core_provenance.json`.
   They establish the observed chapter/stage geometry, not mode or eligibility.
5. Use the saved sequence 0087 stage 6-5, 0088 Hero Formation, 0090–0096 battle,
   0097 Victory and 0098 chapter receipt only for the facts actually visible.
   Hero Formation lacks stage/mode/AP labels. The saved successful battle is
   already evidence; another battle is unnecessary for this package.

The merged base already includes the reviewed no-claim checkpoint protection and
loading-only `CoreRuntime.observe_ready` path. Preserve those fixes and use them for
the Campaign workflow; do not reopen them as Campaign work or add generic UNKNOWN
retries. A recorded RapidOCR replay of the saved `0026` Home frame at producer
commit `10740eb` also produced a clear `home_city` with zero published spatial
building objects through both `ObservationBuilder.build` and
`NavigationPerception.build`. Although `HomeCityObjectId.CAMPAIGN` and the
`PNC_CAMPAIGN_HOME_PORTAL` return edge exist in the catalog/graph, the Home-to-Campaign
entry control is not thereby proven. Treat the producer's current Home publication
and the entry selector as a prerequisite; do not assume a Campaign portal is usable
from endpoint mapping alone.

The replay result is recorded in
`.local-data/reports/institute_remaining_audit_20260914/results.json` and its
`replay.py`; it is retained as a Home-publication regression, not a reason to add a
Home coordinate guess or a second observer.

The recovered build's `CopyZonesFightWin:openHeroBattlePosWin` opens formation;
its selection callback reaches `sendChanegeCmdFunc` and then
`CopyzonesSend.RequireAttack`. This is strong client-source evidence of separate
operations, not proof of current control geometry or server behavior. Consult
the scoped note before expanding source inspection; never invoke game-service
requests to bypass UI evidence.

## Campaign-owned producer and release acceptance

The Campaign owner owns the Campaign-specific perception models/IDs, assets,
bounded OCR/anchors, fixtures, qualification and publication through both
`ObservationBuilder.build` and `NavigationPerception.build`, together with the
consumer that decides whether those facts prove a workflow. This scope excludes
generic vision engines, global guard changes and the Resource, Hero recruitment,
Gathering march-formation and broader Research families. The existing
Resource-partial/Hero-results/broader-Research work remains outside this plan;
Campaign must not wait for or extend it. DailyGo, if an entry path is relevant,
is only an adapter to this same Campaign workflow and does not create a second
identity, engine or battle path.

| Required fact | Consumer use | Qualification required before enabling the path |
|---|---|---|
| Observed chapter and stage identity with actionable geometry | Select one stage and reacquire it after a transition | Independent known surface, CLEAR guard, fresh frame, exact row identity; no arbitrary unobserved stage synthesized from 10-3 |
| Mode and eligibility/locked state used by the original policy | Choose Standard/Elite in configured order | Positive supported evidence for each mode enabled by the caller; missing mode or eligibility cannot select |
| Current stage AP and displayed Challenge cost when visible | Decide whether the requested stage action is within the existing preparation boundary | Read AP/cost from the current stage-detail frame (`0087` shows `120/120` and `20`); never carry AP, cost or stage facts from a prior frame into Hero Formation; any AP-consuming action needs the existing mutation/authority review |
| Stage-detail Challenge distinct from formation Challenge | Open preparation exactly once | Source-screen-specific actionable control, with competing overlay/premium/label-only negatives |
| Current Hero Formation identity | Prove preparation was reached | Independent `PNC_HERO_FORMATION` identity for the 0088 layout and its current controls; do not equate it to `PNC_BATTLE_PREP` or copy stage/mode/AP from 0087 |
| Formation safe return control and actual destination | Finish Home without attack | Qualified current-frame action and saved transition back to stage/map, then existing Home route |
| Home-to-Campaign entry control | Enter the Campaign map from the shared Home boundary | The recorded both-path Home replay at producer revision `10740eb` published zero spatial building objects; qualify a current Campaign portal/route before relying on `HomeCityObjectId.CAMPAIGN` mapping |

Implement and review the named Campaign producer slice in the same vertical change.
Replay relevant saved frames through both real observation paths and preserve
negative guards. Do not add a consumer parser, alias a mismatched surface, or
fabricate `mode` metadata in production. If one mode lacks evidence, keep that mode
explicitly unsupported and leave its requirement open; do not call the full policy
port complete. A change to a generic OCR, guard or runtime engine is outside this
plan unless a concrete cross-cutting defect is demonstrated and one focused
consultation establishes its smallest safe fix.

## Canonical owners: existing symbols and proposed seams

Use the current task, policy, observation and route owners as the baseline. The
proposed names below identify the smallest missing consumer contracts; they do not
authorize a second parser, route graph or battle runner:

| Concern | Existing verified owner | Remaining typed seam |
| --- | --- | --- |
| Policy/input | `CampaignPolicy.from_params`, `CampaignMode.STANDARD` and `CampaignMode.ELITE` in `pnc_automation/app/pnc/domain/policy_models.py` | Reuse enabled-mode order and default Standard. Reject missing/unknown mode or eligibility; do not coerce an unobserved mode to Standard. |
| Legacy selection | `CampaignTask.plan`, `CampaignTask.verify`, `choose_priority_entry`, and `_tap_entry` in `pnc_automation/app/automation/tasks/campaign_task.py` | `CampaignWorkflow` selects one exact observed row and returns a typed `CampaignPreparationResult`; preserve no-candidate skip/unsupported behavior without legacy fallback. |
| Screen identity | `ScreenType.PNC_CAMPAIGN_MAP`, `PNC_CAMPAIGN_CHAPTER`, `PNC_CAMPAIGN_STAGE`, `PNC_BATTLE_PREP`, and `PNC_HERO_FORMATION` | Campaign owns the named Campaign producer profiles, fields and controls in the shared identifier/observation partitions. `PNC_HERO_FORMATION` is not an alias for `PNC_BATTLE_PREP`; reconcile the endpoint contract explicitly and keep Gathering's formation controls separate. |
| Existing route graph | `campaign_flow_screen_types()`, `NavigationCore.navigate`, `NavigationCore.transition`, and `reviewed_navigation_edges()` (`PNC_CAMPAIGN_MAP -- PNC_CAMPAIGN_HOME_PORTAL -> PNC_HOME_CITY`, chapter Back, stage Close) | Campaign owns only the named Campaign edges and constrained operations: stage selection, stage-detail Challenge, preparation confirmation and qualified formation return. The Home-to-Campaign entry control needs fresh Campaign producer evidence because endpoint mapping alone is insufficient. |
| Existing core context | `WorkflowContext.navigate`, `WorkflowContext.observe_content`, `CoreWorkflowRunner.run`, and `CoreWorkflowRunner.recover_to_home` | Add typed Campaign selection/preparation/return methods using current-frame content, bounded loading settle and exact source/control checks. No raw tap or `TaskContext` leak into the workflow. |
| Callers | `TaskRegistry` registers `CampaignTask`; `AutomationApi.campaign`, `AutomationSession.campaign`, and module helper call `run_task`; typed core dispatcher currently has no Campaign branch | Campaign owns the `TaskId.CAMPAIGN` registry entry, dispatcher branch/factory and direct/authored caller bindings in their named partitions. The typed binding must have no silent legacy fallback and must stop before formation Challenge/attack. Leave other TaskId branches unchanged. |
| Result/receipt | Legacy `TaskResult` accepts `PNC_BATTLE_PREP` or a route transition as success | Add a typed receipt containing selected chapter/stage, proven mode/eligibility, current preparation screen/layout/frame/artifact and final Home evidence. Preparation evidence remains valid after exit; Home alone is not preparation. |

Campaign's producer partitions are its named entries and fields in
`screen_type.py`, `ui_element_id.py`, `screen_contracts.py`, `selector_registry.yaml`,
`screen_anchors.json`, `ocr_region_plan.py`, `observation_request.py`,
`pnc_observation_enricher.py`, `screen_classifier.py` and `observation.py`, plus
the corresponding Campaign fixtures, provenance and qualification tests. Its
consumer partitions are the Campaign methods/edges in `navigation_core.py` and
`core_workflow.py`, the `TaskId.CAMPAIGN` branches in the registry/dispatcher/API
and the typed workflow/result modules. This named partitioning lets Campaign own
the complete vertical in an isolated copy while leaving generic OCR/guard/runtime
engines and other task families unchanged.

`PNC_CAMPAIGN_BATTLE_BUTTON` is an existing selector whose tested production profile
is the narrow `campaign_stage_10_3` layout. It is not evidence that the saved 6-5
Challenge has the same geometry or meaning. `PNC_HERO_FORMATION_HEADER` and
`PNC_HERO_FORMATION_SAVE_BUTTON` exist in the selector catalog for other formation
flows, but the saved 0088 layout currently has no matching producer profile; neither
the existing Save Form selector nor the bottom Challenge label may be borrowed as an
attack or preparation control without independent current-frame qualification.

## Independent qualification scope

The prior evidence audit leaves independent positive holdouts missing for 19 changed
layouts overall. That is a Campaign-owned qualification queue, not a requirement to replay
every historical screen before this Campaign consumer can be reviewed. Campaign
requires separately reviewed positives for the exact Home entry, chapter/stage and
mode/eligibility facts, stage-detail Challenge, distinct Hero Formation identity and
safe return control that the workflow actually consumes, with wrong-screen,
locked/absent, overlay and unowned-control negatives. Preserve the recorded idle
Build Queue and Economy idle-detail proofs without rerunning them or treating
them as Campaign stage or Hero Formation qualification. A correction capture cannot become
an untouched holdout for the same corrected profile. Record each feature's holdout,
both-path result and producer revision independently.

## Remaining implementation sequence

### C1 — Close the selection and result contract

Trace the existing `choose_priority_entry` use and Campaign task applicability.
Specify the finite selection scope the current policy promises. The existing
chapter/stage examples cannot justify a new unbounded map traversal. If progressing
to another chapter is necessary for that scope, identify its actual producer and
bounded route before writing the consumer; otherwise report the precise missing
coverage.

Define a typed result carrying selected chapter/stage, policy mode when proven,
preparation capture time/artifact, and a positive preparation-reached outcome.
Separate selected-stage context from current formation content. Preserve the
original no-eligible-stage disposition as a structured skip/unsupported result
where appropriate; never manufacture a positive preparation result from a map
with no candidate. Follow existing result conventions rather than adding a new
generic outcome framework.

When the current stage-detail frame shows AP and a Challenge cost, both are required
current facts: publish and validate the numeric current AP and cost before the stage
Challenge input, and stop when an expected displayed field is absent, stale or
malformed. Opening preparation is a separate nonspending action; any additional
insufficient-AP eligibility predicate must follow the qualified UI or scoped client
evidence, not an assumed global cost or a new battle policy.
The `0087` values (`120/120`, cost `20`) are saved evidence only. Once `0088`
Hero Formation is reached, its frame does not show stage, mode or AP; the result must
retain the earlier stage snapshot separately and must not reuse those values to
authorize any formation Challenge or attack action.

Acceptance: input validation, no-candidate behavior and success evidence are
specified without relying on undocumented metadata or calling the old task engine.

### C2 — Add only the missing constrained core operations

Extend the existing navigation/context owners with the smallest typed operations
for selecting a Campaign row and opening its preparation surface. Do not expose a
generic tap or raw action executor to workflow code. Reuse current route and
observation requests, freshness checks, source-screen validation, label rejection,
passive settle owner and the existing screen/time budgets.

After chapter/stage selection, acquire a fresh known observation before issuing
the next action. Reacquire the chosen stage by exact observed identity; a row's
old coordinates cannot survive scrolling or a screen transition. Require the
qualified stage-detail Challenge, not any Challenge selector. After its one
dispatch, confirm the distinct preparation surface within the existing bounded
settle contract. UNKNOWN, overlays, wrong destinations or expired deadlines stop
the operation; do not replay the Challenge or add a generic UNKNOWN retry.

Keep the actual arrival screen `PNC_HERO_FORMATION` in the typed receipt and its
separately retained source stage observation. The consumer's matching current-stage
Challenge transition establishes why this formation is Campaign preparation;
the formation's own visual evidence establishes what is currently visible. A
previous stage observation cannot satisfy the current Hero Formation guard, and
neither screen is silently relabeled `PNC_BATTLE_PREP`.

Add the qualified formation return edge with its actual observed destination.
Reuse subsequent return routes. If only arrival can be proven but the return
control is not qualified, retain the evidence and mark live workflow acceptance
blocked at exit; do not press the attack control to escape.

Shared modules are partitioned by named Campaign symbols, `TaskId.CAMPAIGN`,
Campaign screen/profile/data keys and Campaign test cases. Campaign owns its
vertical slices in `navigation_core.py`, `core_workflow.py`, route registration,
policy/result exports and entrypoints; leave generic engines and other task branches
unchanged. Work in the assigned isolated copy and keep edits within those named
partitions. Do not change SELECT_CASTLE/roster semantics, Gathering march
formation, or unrelated building, Mail/Login and Research symbols.

Acceptance: production navigation selects from fresh facts, reaches preparation
once and can confirm Home. No operation dispatches formation Challenge or an
attack request.

### C3 — Implement the workflow and migrate real callers

Add the dedicated typed Campaign workflow through `WorkflowContext`. Use a
Home-to-Home `WorkflowSpec` with `NONSPENDING_STATE_CHANGE` for stage/formation
navigation only, after source and current transition evidence support that
effect. The typed receipt must retain the preparation observation before exit.
Do not assign resource-changing capability merely to permit an unmodeled action.
If current evidence shows that an intended navigation action itself consumes AP,
stop and record that concrete capability boundary instead of relabeling it. Consult
the coordinator only if the smallest fix necessarily changes a generic effect,
runner, lease or guard contract; a missing Campaign fact remains an explicit blocked
Campaign slice. DailyGo, if relevant, must call this same preparation workflow and
must not create a second battle or mutation identity.

Wire `TaskId.CAMPAIGN`, direct application/API callers and authored dispatch to
the same factory/workflow. Validate policy before connection; reuse exact active
identity preflight, one connected runtime and outer lease/cleanup ownership.
Remove the migrated Campaign legacy fallback and its replan loop. Keep unrelated
legacy tasks untouched. Adapt tests to observable typed behavior, not mock call
shape alone. Update user-facing script/API examples only where the contract changes.

Acceptance: all supported original Campaign entry points reach the typed path,
unsupported modes fail explicitly, and caller dispatch cannot silently fall back
to legacy execution or continue from preparation into battle.

## Offline validation required for changed behavior

Use the repository runner and current Python 3.13+, not raw discovery. Begin with
the affected Campaign component and new contract module. Existing anchors include
`tests/unit/app/automation/tasks/test_campaign.py`,
`tests/integration/vision/test_campaign_visual_profiles.py`, and
`tests/integration/script_runner/test_typed_core_dispatch.py`. Campaign owns the
producer and qualification assertions for its named profiles in the shared vision
test/data partitions; generic vision-engine tests remain outside this package.

Required behavioral cases, grouped into existing test owners:

- Ordered Standard/Elite selection uses positive mode/eligibility evidence;
  absent mode, locked candidates and no candidate never dispatch a stage action.
- The selected row changes/disappears after a transition: reacquisition fails
  before input. Stale geometry and label-only controls cannot be tapped.
- Identical Challenge text on stage and formation resolves only under the correct
  screen contract. A successful run contains one stage Challenge and zero formation
  Challenge/battle inputs.
- A known loading interval can settle within existing budgets; UNKNOWN, blocking
  overlay, wrong destination and expired budget produce no retry/input and no
  success. Test one meaningful representative per actual boundary, not every
  artificial combination.
- Result provenance records prior selected stage separately from the current
  preparation frame. Missing current stage/AP labels stay absent.
- Direct and authored calls use the same workflow; missing/invalid policy is
  rejected before connection; borrowed runtime is not closed by dispatch;
  execution/cleanup errors retain both causes under the canonical cleanup owner.
- The reviewed return route confirms Home while the result still proves the
  earlier preparation arrival. Unproven exit cannot report complete success.

Before enabling the consumer, replay the saved `0087`, `0088`, and `0097` pixels
through both real observer paths, `ObservationBuilder.build` and
`NavigationPerception.build`, using actual RapidOCR and their normal Campaign requests. Compare the
screen/layout identity, `GuardVerdict`, current-frame row/control ownership, frame
references, and semantic fields. The replay must preserve the following distinctions:

1. `0087` is stage 6-5 with the visible AP/cost facts; its stage Challenge is not
   the formation Challenge.
2. `0088` is an independent Hero Formation surface with no current stage/mode/AP
   facts; a successful producer must not copy those values from `0087`.
3. `0097` remains an unsupported or manually retained Victory/result frame unless a
   separate existing consumer requires it. It cannot be used to claim preparation
   coverage.

Any `UNKNOWN`, missing profile, absent mode/eligibility, wrong-screen Challenge,
overlay, or unowned control is a truthful Campaign producer gap and stops the
consumer. A passing legacy fixture or a manually built observation is insufficient
for the both-path release gate. Campaign owns producer test edits for its named
profiles; generic vision-engine tests remain outside this package.

Concrete development commands from the assigned worktree:

```powershell
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py group unit.app.automation.tasks
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py group integration.script_runner
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py affected --base origin/main --explain --json .test-impact/campaign-selection.json --results .test-impact/campaign-results.json
git diff --check
```

Run the narrow new contract group as documented when adding it; do not assume the
two existing groups cover the new workflow. `affected` includes tracked/untracked
changes and may require a full fallback for public/shared changes. Follow it once;
do not run another full suite solely to duplicate a passing gate. Historical
2,027-pass evidence belongs to the prior candidate, not this future port.

## Smallest live acceptance and permissions

Granted by the latest user request: canonical BlueStacks API testing on
`mega_old_acc`, any needed in-game action and unlimited in-game resource budget.
No new resource-budget approval is needed. For this package the sufficient proof
uses **one stage-to-preparation transition and zero battle starts/AP purchases**;
these are proof limits chosen for the scope, not a claim that permission was denied.
There is no unresolved Campaign-specific product question or additional permission
request at planning time. The mode, AP, preparation identity and return decisions
are technical evidence gates; the worker must resolve the current stage from fresh
observation and stop if it is not qualified.
The proof may start from a prepared authenticated active-castle session; it does
not certify fresh Login or alternate-castle switching.

This package does not rebudget the task, run automatic Daily maintenance, merge or
push to main, use desktop mouse/keyboard control, call a game service directly, or
perform real-money actions. The live proof stops before formation Challenge and any
battle/AP spend.

After focused checks and the Campaign-owned producer gate pass:

1. Resolve `mega_old_acc` and the required live role through configured account
   resolution. Hold the canonical process-scoped lease across entry, workflow,
   proof and cleanup. Respect pre-existing instance cleanup policy. Current active
   castle is the target; no switch is needed for this package.
2. Capture readiness and exact active identity. Record source build when visible,
   applicable policy, starting AP if actually published, and the fresh selected
   stage. If no eligible observed stage exists, record applicability/blocking facts;
   do not spend to unlock unrelated progress merely to satisfy this smoke.
3. Invoke the actual migrated production caller for the supported default mode.
   Any local probe helper must only compose that caller and write diagnostics;
   it must not implement its own route. Direct/authored parity is proven offline,
   so a second live route solely for API parity is unnecessary.
4. Save before/after frames and real observation diagnostics proving the distinct
   preparation surface, no formation Challenge dispatch and reviewed return Home.
   Process exit and a manually opened formation screen do not constitute caller
   acceptance. Do not battle again to reproduce the old 20 AP receipt.
5. On an unresponsive API/emulator, save the failure and stop at the last truthful
   state; request the needed user manual manipulation if necessary to continue.
   That recovery does not prove the production route. Use only the canonical BlueStacks API and the configured lease; desktop
   mouse/keyboard control, direct game-service calls, real-money actions, and a
   guessed selector are outside this plan. An observed-point inspection can clarify
   a missing producer, but it does not qualify a guessed production selector.
   Release the lease with truthful last state and retain execution/cleanup errors.

Write artifacts under `.local-data/artifacts/core_ports/campaign/<run-id>/`:
resolved nonsecret target, source revision/change manifest, policy, before/after
observations, navigation trace, preparation receipt, final Home/stop evidence and
cleanup disposition. Link them from the validation ledger with actual pass,
blocked or applicability outcome. Do not require private screenshots in Git.

## Completion and self-contained definition of done

Complete this package only when the requested policy coverage, Campaign-owned
producer models/IDs/bounded OCR/fixtures and both-path publication, constrained
consumer, public/authored migration, fresh offline checks, one stage-to-preparation
receipt, no formation Challenge/attack input, and reviewed Home exit pass. Report
any remaining mode/surface gap by exact producer fact and saved frame; a partial
Standard-only slice is useful but is not full two-mode contract completion. A
production-safe `UNKNOWN`, absent Home entry control, or unqualified Hero Formation
remains blocked coverage and is not Done. The final combined merge/integration is
outside this package and is not a prerequisite for its own reviewable completion.

Copyable vertical assignment:

> Execute PNC_CORE_REMAINING_04_CAMPAIGN_PLAN.md from immutable merged base
> `6bc27585fbac1244672cf4a653ea6248955a4aca`. Own the Campaign vertical end to
> end: feature-specific producer models/IDs, bounded OCR/anchors/controls,
> fixtures and qualification in both observer paths, typed stage/preparation
> workflow, named caller bindings and tests. Use the canonical runner and, when
> the gates pass, one leased `mega_old_acc` proof reaching preparation and
> returning Home, with no battle start. Existing unlimited in-game authority is
> retained. A prepared authenticated active castle may be used as the starting
> session; this proof does not certify Login or alternate castle switching. Report
> exact changed files, current test output, preparation/exit evidence and exact
> producer gaps. Do not wait for or hand off routine work to another package.
