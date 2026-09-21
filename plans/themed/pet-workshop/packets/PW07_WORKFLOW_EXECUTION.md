# PW07 — Observed execution, workflow and continuation results

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW02](PW02_RECOGNITION_CONTROLS.md), [PW04](PW04_ONE_STEP_SOLVER.md), [PW06](PW06_AUTHORITY_JOURNAL.md). PW05 is a live-use gate, not an offline implementation prerequisite.

## Read before implementation

- [Plan 03: lifecycle, survey and freshness](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#3-workflow-gestures-and-receipts)
- [Plan 03: operation-specific gestures and receipts](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#operation-specific-validation)
- [Plan 03: target sequencing and failure results](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#4-independent-runs-daily-integration-and-failure-results)
- [Plan 01: route-evidence provenance](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#evidence-that-can-be-used-without-live-access)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** observed-workflow worker. **Prerequisite detail:** accepted PW02 observation/controls and route-evidence table, PW04's real planner/shared validator, and PW06 authority/journal. Can run alongside PW05 using the same accepted recognition/solver commits. No live emulator access for this offline handoff.

1. Own the typed Workshop action session: translate logical intents to guarded measured actions, reuse the actual policy validator, and interpret settled before/after evidence into the existing reconciliation result. Bind the session through PW06's boundary/dispatcher; do not recreate authority or journal state. Keep the action session and workflow as focused components under this one worker's ownership.
2. Cover selection/production, ordinary and generator merges, exact food-to-generator feeding, grey activation, finite exhaustion, two-piece submission and restricted recycling. Journal before the earliest consumptive input, including confirmation-disabled recycle. Require native frame provenance and settled receipts; no ambiguous action is retried. The operation table in Plan 03 owns the exact preconditions/results.
3. Compose the workflow/session, `WorkflowContext` methods, reviewed routes/strip survey, common target sequencing/continuation and typed run result. Implement the [canonical two-way continuation decision](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#continuation-and-later-invocations): `CONTINUE` or `STOP_INSTANCE`, with detailed outcome reasons retained separately. Derive that decision once from result/evidence; do not add redundant continue variants or a persistent instance quarantine. Own the connected Workshop methods of `CoreMutationBoundary`; PW06 already owns its authority/dispatch extension. Register no navigation edge before PW02's relevant control/destination evidence is accepted.
4. Add offline action and lifecycle checks using the real parser/planner/boundary plus supplied typed observations or connected-runtime test doubles as appropriate. Update execution/navigation/result sections of the canonical documentation. Parser functions, reward policy, CLI bindings and Daily configuration stay with their packet owners.

### Home entry ownership after the V44 review — 2026-09-21

**PW07 owns the Illusory Beast Manor target and its Home-entry qualification.** The lead reviewed the V01–V44 epic, building coverage map and V44 plan at `4dfbe8f` on `codex/vision-v44-home-navigation`. V44's inventory records client type `5016` / `BEAST_MANOR` as an unbound system node; neither its named route coverage nor another vision packet assigns the Manor-specific route. An inventory entry is not a qualified route. V44 retains sole ownership of shared camera localization, zoom, slots, occupancy, scanning and navigation contracts. Its plan is `plans/themed/vision/modules/V44_FULL_HOME_CITY_NAVIGATION.md` on that branch, still awaiting integration at this review.

Extend the existing semantic Home catalog and canonical observation producer with the actual Manor target, evidence-backed labels/body geometry and its known destination. Use `NavigationCore.open_building` and the accepted acquisition contract, then Workshop's measured Manor entry/return controls. Distinguish Illusory Beast Manor from the nearby generic `Manor` label and Trap Workshop. Register only evidence-qualified targets/edges; a semantic selector name, client ID, projected point or one exploratory tap is not sufficient click evidence. Reconcile the `5016` binding with V44's single catalog/slot owner when integrated; APK-derived facts remain offline references. Remove any superseded unused Workshop selector declaration when migrating to the accepted canonical target, without adding a parallel coordinate route.

The lead owns this separate Home-entry slice while the current PW07 worker completes the independent action/session package. Do not modify V44's shared implementation in parallel or consume its unaccepted branch. If acquisition needs an unintegrated V44 capability, mark that route awaiting the specific accepted dependency and target qualification; continue PW05 and independent PW07 offline work. Completion of unrelated V44 routes is not a prerequisite for Workshop parsing or action-session tests. Until the required acquisition path is accepted, production Home entry must return a truthful unavailable result and full Workshop route acceptance remains pending.

Use saved native Home captures through both production publishers for target/geometry evidence and generic-Manor, wrong-building and stale/post-pan negatives where applicable. The source capture `20260921T175215Z_c2_home_scan_1.png` under `.local-data/artifacts/2026-09-21/pet_workshop_pw02_board_scoped_b405304/` and its following Manor/Workshop trace establish observed presence, not production acquisition qualification. PW10 must prove the final candidate's Home → Manor → Workshop → Manor → Home route through canonical acquisition on an authorized eligible non-Hopeful castle. Preserve the existing lease, exact-candidate and non-spending route-validation requirements; do not repeat unchanged inner-route proof unless integration affects it.

## Acceptance

A connected-runtime test double exercises the complete production workflow and action session with zero generic mutation retries. Every mutation uses the actual shared validator, fresh measured geometry and PW06's durable boundary; ambiguous evidence retains a pending result. Both invocation adapters can call the accepted workflow factory/result contract without implementing policy, gestures or sequencing. Offline acceptance may precede PW05. Before a production gameplay caller is invoked, PW05 must be accepted and the lead must establish PW10's identity, target, lease and action-budget prerequisites. Scoped canaries then collect the live transition proof required for unattended promotion.

## Focused validation

Cover settled success, optimistic intermediate state, no effect and ambiguous action outcomes; exact ingredient consumption/finite transform; native provenance; selected reward-piece hazards; and both recycle-confirmation preferences. Observed zero blocks submission/recycle as well as production. Verify the policy validator and journal are actually invoked, rather than reproducing their logic in a test-only executor.

Use a connected-runtime test double for a run longer than five actions, fresh order surveys, continuous cooldown timing, C24 applicability and safe/unsafe exits. Exercise common target sequencing so unknown state stops one physical instance for the current invocation while independent instances remain usable. Use the canonical A/B invocation scenario: later explicit B needs fresh identity/safe-screen proof and leaves A's unresolved journal entry intact; later A cannot replay it. Retain supported feeding/activation/rebuild behavior before reporting a blocked production path, per Plan 02. Route definitions require PW02's accepted evidence table; current production-route and consumptive-transition proof remains in PW10.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Accepted action session, workflow factory/context/result and target-runner interfaces, registered route evidence, action/lifecycle tests and ownership notes. PW08 and PW09 receive the same immutable accepted implementation commit without waiting for PW05 reports or a live window. Neither adapter can enable gameplay ahead of the common live-use gates.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.

### Delegation — 2026-09-21 UTC

**Delegated, offline only.** Persistent authority session `fearless-sprite`, turn 005, starts from accepted `1f14e06` in `pet-workshop-authority`. Brief: `.local-data/devin-briefs/pw07-implementation.md`; run: `.local-data/devin-implement/pw06`. It owns the action/session/workflow/continuation package through the existing policy validator, boundary and journal. The canonical simulator may aid logical tests. PW05 proceeds independently; it remains a live-use gate. Home→Manor has no accepted measured production control, so the worker must preserve a truthful unavailable-entry disposition and must not register an inferred edge. No live/account/config access. Lead owns status, independent review and subsequent exact-candidate live assignment.
