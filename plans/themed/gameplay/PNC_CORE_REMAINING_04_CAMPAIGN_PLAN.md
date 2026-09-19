# Remaining package 04 — Campaign policy, workflow and callers

Revised 2026-09-15. This is the remaining Campaign core port after the
[V01–V43 scope split](../vision/PNC_CORE_REMAINING_VISION_BOUNDARY.md). It consumes qualified
Campaign perception/navigation. It does not implement those deliverables again
or add Campaign battle execution.

## Outcome and dependencies

The existing caller selects an eligible observed stage under its canonical
policy, uses the qualified operation to reach preparation, retains a typed
preparation receipt and finishes Home. Direct and authored calls share one
workflow. Home alone is not evidence that preparation was reached.

| Owner | Output consumed here |
|---|---|
| [V01](../vision/modules/V01_EXISTING_OPENCV_FOUNDATION.md) | Shared observation, bounded OCR, guard and frame-provenance contract |
| [V02](../vision/modules/V02_HOME_CAMERA_AND_NAVIGATION.md) | Qualified Home acquisition; endpoint mapping alone does not prove a usable Campaign portal |
| [V13](../vision/modules/V13_CAMPAIGN_MAP_AND_CHAPTERS.md) | Map/chapter identity, current stage rows/states, measured selection/reacquisition and navigation |
| [V14](../vision/modules/V14_CAMPAIGN_STAGE_AND_FORMATION.md) | Stage facts/controls, distinct Hero Formation, nonspending stage-to-formation and return operations, source-stage/current-frame separation, existing Campaign consumer endpoint correction |

Record supplying revisions, fields, operations and evidence before enabling the
path. Policy/caller work may proceed against the agreed typed contract while
qualification is pending; manually supplied facts do not establish integrated
coverage. Only required outputs gate acceptance, not completion of all 43 plans.

Excluded deliverables: screen models/IDs, profiles, templates, OCR regions,
parsers, both-path publication, measured navigation/return edges and their visual
qualification. V02/V13/V14 own them. Do not add a local parser, second navigation
operation or duplicate endpoint fix to bypass a missing dependency. Hero
optimization, formation editing/saving, battle, sweep, AP replenishment, reward
claims, automatic Daily and a global stage catalog are also outside this package.

## Current code and evidence to reuse

Read current AGENTS.md, applicable implementation skills and
[CORE_WORKFLOW_PORTING](../../../instructions/CORE_WORKFLOW_PORTING.md). Reuse a suitable
isolated task checkout, preserve ongoing work and record actual code/plan
revisions. The old merged `6bc27585fbac1244672cf4a653ea6248955a4aca` is historical
context, not an instruction to reset a resumed feature or discard newer fixes.

At planning checkpoint `dc2fdbd`, reconcile these anchors with newer work:

| Concern | Existing owner and remaining responsibility |
|---|---|
| Policy | `pnc_automation/app/pnc/domain/policy_models.py`: `CampaignPolicy.from_params`, ordered `enabled_modes`, `CampaignMode.STANDARD`/`ELITE` |
| Legacy caller | `pnc_automation/app/automation/tasks/campaign_task.py`: `CampaignTask.plan`, `verify`, `choose_priority_entry`, `_tap_entry`; preserve selection/no-candidate behavior during migration |
| Workflow | `pnc_automation/app/automation/engine/core_workflow.py`: `WorkflowContext`, `CoreWorkflowRunner`; compose V-owned constrained operations without raw taps or a `TaskContext` leak |
| Navigation dependency | `pnc_automation/app/automation/engine/navigation_core.py` and Campaign screen contracts; consume V13/V14 outputs without taking their edge/profile work |
| Entrypoints | `TaskRegistry`, `CoreScriptDispatcher`, `AutomationApi.campaign`, `AutomationSession.campaign`, module helper and authored `TaskId.CAMPAIGN` |
| Result | Existing typed workflow/result conventions; add only the missing caller result, reusing supplied observations and route receipts |

The old task accepts `PNC_BATTLE_PREP`; V14 owns correction for the actual
`PNC_HERO_FORMATION` arrival. Consume that correction before migrating the caller.
Generic Hero Formation elsewhere is not Campaign preparation. Keep the actual
screen identity and originating stage transition; never alias the frame to
`PNC_BATTLE_PREP`, publish two primary identities, or add every formation page to
the Campaign-ready family.

Read the [Campaign workflow note](../../../docs/game-reference/workflows/campaign-navigation.md)
and [capture findings](../../reviewed/vision/PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md) before exploring.
Historical captures under
`C:/Users/lebel/pnc/.local-data/worktrees/workflow-recognition-integration/.local-data/artifacts/`
and reports under
`C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation/.local-data/reports/`
are read-in-place evidence; other numbered capture roots are in the findings.
Missing evidence is reported by exact path rather than replaced by a guess.

| Saved frame | Consumer constraint retained |
|---|---|
| `0087_campaign_stage6_5_detail.png` | Stage `[6-5] Marsh of Tear`, AP `120/120`, Challenge cost `20`; historical values, not runtime defaults |
| `0088_campaign_stage6_5_challenge.png` | Hero Formation has its own identity/controls; stage, mode and AP are absent from this frame |
| `0097_campaign_victory_receipt.png` | Historical battle result, neither preparation proof nor a new battle requirement |
| Home `0026` replay at `10740eb` | Home/CLEAR with zero published buildings did not prove Campaign entry; V02 supplies acquisition |

These captures do not establish every mode or current route. V13/V14 own their
producer tests and qualification. The client-source note distinguishes opening
formation from its callback that requests attack; it is not proof of current
control geometry or permission to invoke game services. Do not repeat a battle
or the historical recognition inventory for this caller port. Preserve landed
loading-only `observe_ready`, no-claim protection and canonical cleanup.

## C1 — Preserve policy and define the caller result

1. Trace current selection/public parameters. Retain enabled-mode order, default
   Standard and original finite selection semantics. Unobserved mode stays
   unknown; do not invent Standard or eligibility. Record any required unsupported
   chapter/mode as the precise V13/V14 dependency.
2. Select only qualified current candidates. Locked, absent or unknown eligibility
   cannot become an action. Preserve no-candidate skip/unsupported behavior using
   existing typed result conventions.
3. Reuse delivered stage/preparation receipts. Add a thin typed caller result only
   where missing: selected chapter/stage and proven policy facts; preparation
   screen/layout/frame/artifact; outcome; final Home or exit-failure evidence.
   Keep source-stage context separate from current formation content.
4. When displayed stage AP/cost is required by the supported contract, consume
   and validate its current numeric facts before the stage operation. Missing,
   stale or malformed facts block input. Any insufficient-AP predicate follows
   qualified UI/source behavior, not an assumed cost or a new battle policy.

Acceptance: policy/result behavior is explicit without new perception,
undocumented metadata, unbounded traversal or legacy-engine calls. Standard-only
acceptance remains partial if Elite is required but unsupported.

## C2 — Compose qualified operations

1. Implement the typed Campaign workflow through `WorkflowContext` and the existing
   runner. Use a Home-to-Home `WorkflowSpec` with `NONSPENDING_STATE_CHANGE` only
   for the qualified nonspending navigation path.
2. Pass the exact selected identity to V13/V14's operation. Its fresh revalidation,
   measured input, loading settlement and destination checks stay in the canonical
   navigation owner. Do not duplicate them in a caller loop or add raw taps.
3. Consume one verified stage-to-preparation result. Wrong destination, UNKNOWN,
   blocked/stale controls or expired budgets stop without replaying Challenge.
   Stage Challenge and formation Challenge are different actions; this workflow
   performs zero formation Challenge/attack inputs.
4. Retain preparation evidence, then use the qualified return operation to confirm
   Home. Exit failure preserves the earlier receipt and error; it cannot become
   complete success or trigger another preparation attempt.

An absent operation or safe return is a concrete V13/V14 dependency; continue
independent caller work without taking over route implementation. If evidence
shows the intended transition spends AP, retain that capability blocker rather
than classifying it as nonspending or starting battle.

## C3 — Migrate callers and remove migrated legacy dispatch

Bind `TaskId.CAMPAIGN`, direct application/API/session/module callers and authored
dispatch to the same typed factory/workflow. Validate parameters before connection;
reuse exact active-identity preflight, one connected runtime and outer lease/cleanup
ownership. Authored dispatch borrows its runtime without closing it.

Remove the migrated Campaign fallback/replan loop once supported callers use the
typed path. Preserve other task branches. Do not redo V14's endpoint correction.
Update examples only where the public contract changes. A Daily-Go adapter, if
already required, invokes this same preparation workflow and adds no battle path
or mutation identity.

Acceptance: supported original entrypoints converge, unsupported modes are
explicit, and no caller falls back to legacy execution or continues into battle.

## Validation and completion

Consumer anchors include `tests/unit/app/automation/tasks/test_campaign.py`,
the typed workflow tests and
`tests/integration/script_runner/test_typed_core_dispatch.py`. Cover:

- Ordered Standard/Elite policy, missing/locked/no candidates and validation
  before connection.
- Propagation of changed/missing targets or failed V-owned operations without
  caller replay; one preparation request and zero battle requests.
- Prior-stage/current-formation provenance, absent current stage/AP labels,
  preparation evidence after Home exit and truthful exit failure.
- Direct/authored parity, one runtime, borrowed cleanup and preservation of both
  execution and cleanup errors.

Typed consumer fixtures prove decisions. Reference V-owned producer/route evidence
for visual coverage; do not duplicate their qualification in 04. Run the narrow
applicable repository group and
`py tools/run_tests.py affected --base origin/main --explain`; follow any required
fallback. Historical counts are not current acceptance.

After dependencies and offline checks pass, run one production caller proof:
fresh authenticated identity → policy selection → preparation → Home, under the
canonical process-scoped lease and current assignment's configured target/role.
Preserve pre-existing instances and stop before formation Challenge, battle or AP
purchase. Reuse an existing compatible caller proof if it establishes this exact
contract; a V-only route or manually opened formation does not prove the migrated
caller. No duplicate live run solely for API parity is needed. No eligible stage,
unqualified exit or unresponsive API remains an exact blocker; do not spend to
unlock progress or substitute desktop input/direct game services.

Keep artifacts under `.local-data/artifacts/core_ports/campaign/<run-id>/`:
nonsecret target, code/plan/dependency revisions, policy, observations, trace,
preparation receipt, final Home/stop state and cleanup disposition. Historical
`mega_old_acc` allocations/unlimited budgets are not a new authorization; follow
the current execution session and scope amendment.

Done requires the requested policy coverage, typed caller migration, relevant
offline checks, dependency qualifications and production caller preparation/exit
proof. Missing modes, facts, operations or live evidence remain incomplete. Final
combined integration is separate. This planning revision needs document checks
only, with no unit or live run.

## Copyable worker kickoff

> Implement package 04 using this revised plan and
> PNC_CORE_REMAINING_VISION_BOUNDARY.md. Preserve resumed work and record actual
> code/plan revisions. Consume V02/V13/V14's qualified acquisition, facts,
> navigation, endpoint correction and receipts; do not implement their profiles,
> parsers, controls or routes again. Own Campaign policy, typed workflow/result
> composition, public/authored caller migration, legacy-path removal and consumer
> acceptance. Preserve ordered Standard/Elite policy and separate source-stage
> context from current Hero Formation. Stop before battle. Use the current assigned
> live target/authority after offline and dependency gates pass. Report changed
> files, tests, supplying V revisions, preparation/exit evidence and exact gaps;
> continue independent work while a specific V output is pending.
