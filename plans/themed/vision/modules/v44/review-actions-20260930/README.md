# Delivery velocity: root causes and execution plans

Revised September 30, 2026. The objective is to reduce the time and repeated work needed to develop, validate and accept repository changes. The first version emphasized completing the V44 route backlog. This revision replaces that priority with five systemic plans; the route documents remain supporting case studies.

Start with [the root-cause assessment](00_ROOT_CAUSES.md). It distinguishes observed failures, source-proven coupling, existing norms that already permit faster work, and hypotheses that need a bounded pilot. The [original review](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/V44_BLOCKERS_AND_VELOCITY_REVIEW_20260930.md) supplies examples, not a requirement to implement every route before improving the workflow.

## Five primary plans

The V coordinator's [published quality review and execution sequence](../V44_QUALITY_REVIEW_AND_SEQUENCE.md) is the implementation authority for this pack. Maintainability, canonical ownership and testability take priority over completing V44 quickly. Its reviewed order is Q1 shared publication, Q2 fixture ownership, Q3 neutral camera values, Q4 coupled live case/result/discovery tooling, Q5 the development cohort and Q6 evidence-backed consolidation. The proposal documents below retain their subject grouping, not an independent execution order.

| Plan | Cause addressed | First useful deliverable | Acceptance |
|---|---|---|---|
| [A — Modularity and runtime contracts](14_MODULARITY_AND_RUNTIME_CONTRACTS.md) | Feature contracts depend on broad concrete composition; entry effects are learned late | Audit camera reverse imports including eager package initialization; relocate one shared value contract outside concrete composition | Actual dependency reach improves without hiding consumers; public behavior and provenance remain correct |
| [B — Test ownership and validation cost](09_FIXTURE_DEPENDENCY_OWNERSHIP.md) | Coarse fixture/asset ownership and expensive composition at the wrong test boundary | Audit Home fixture AND packaged-image readers, narrow owned rules, preserve unknown/shared fallback | All verified consumers selected, controlled defect still caught, fewer unrelated modules; final infrastructure gate passes |
| [C — Live discovery and development](15_LIVE_DISCOVERY_AND_VALIDATION.md) | Copied ignored drivers, missing discovery boundary, acceptance-style handoffs during development | One tracked reusable case/result path and one supported frame-bound menu-discovery operation; pilot one development owner across frozen phases | Next compatible case avoids copied input policy; real lease/receipt/cleanup proof remains; final acceptance uses production routes |
| [D — Acceptance and current state](11_COVERAGE_AND_CURRENT_STATE.md) | The same facts are manually maintained across briefs, manifests, reviews and ledgers | Validate the existing evidence schema and render repeated views from result plus independent acceptance records | Missing cases, wrong candidates and receipt mismatches fail mechanically; a coordinator can resume from one current view |
| [E — Queueing and acceptance slices](10_CAPACITY_AND_SEQUENCING.md) | Shared host capacity and whole-epic gates make ready work wait | One running heavy batch plus prepared next batch as a starting WIP limit; explicit dependency-ready acceptance units | Waits have owners and release triggers; usable slices are accepted separately; any broader queue exception has an explicit decision |

[13 — Delivery measurements](13_DELIVERY_MEASUREMENTS.md) supports all five with existing execution, review and wait timestamps. It is a small record of outcomes, not a new monitoring platform or a prerequisite measurement project.

## Why these changes, rather than another route checklist

Read-only analysis of published source a3fcc9e4184006ee22abe850d01c1f84f80b34bb found:

- A hypothetical camera implementation change selects **292 of 410 modules** through real import/ownership paths. File splitting has not by itself isolated the feature.
- One packaged camera image selects **225 modules**; one Home test fixture triggers **all 410**. Fixing only the fixture fallback leaves two other causes of broad validation.
- The saved e11 gate spent approximately **32.5 minutes executing** and **2.1 seconds selecting** tests. This supports reducing unnecessary test work before optimizing selector calculation.
- A frozen live package contains several thousand lines of ignored helper/driver/fake-test code, while case selection, scopes and report counts are maintained in multiple structures. Recorded metadata repair and missing menu-capture support expose the maintenance problem.
- Current live norms already allow focused pre-live checks, batching, identity continuity and reuse of unchanged proof. Repeated full gates and fresh identity tours are not blanket policy requirements.

The selected counts are static body-change probes, not actual tests or a speedup benchmark. The saved timing run had 409 modules on an older candidate. They do not establish which delay dominates end-to-end delivery; [00](00_ROOT_CAUSES.md#static-selection-evidence) records the method and limits.

## Execution order and boundaries

1. **Start A3/Q1's demonstrated publication divergence and B1/Q2's fixture ownership.** Reproduce the account-field mapping difference, centralize the intended shared content contract and preserve distinct guard/control policies. Prepare fixture ownership independently; packaged assets require a separate complete consumer map.
2. **Pilot A1/Q3's complete neutral-contract boundary; defer A2's larger extraction.** File moves alone are insufficient. Require an actual ownership/testability benefit and retain legitimate composition consumers.
3. **Design C2 and minimal D1 together in Q4.** Agree the typed case/result extension before migrating one cohort. Provide task-owned capture without automatic dismissal and a narrow supported action contract. Q5 development and final production-route acceptance follow that boundary.
4. **Apply E now; use Q6 for current-view rendering and proven test consolidation.** Retain unique assertions, independent acceptance and existing evidence. Keep 13's outcome measures lightweight. Preserve the coordinator's specific affected-boundary holds and existing cross-epic resource arrangements.

Each plan identifies ownership, migration, deliverables and observable acceptance. There is no promised percentage speedup. Stop an extraction that only moves files, a test consolidation that drops unique assertions, or tooling that duplicates runtime policy.

These documents propose work; this planning task has not changed runtime code, launched workers, run application tests, entered BlueStacks or altered another coordinator's allocations. Current non-Main testing resource authority is published at a3; the old collection-permission wait is resolved. Main protection, current user restrictions, target/role/lease authority and truthful runtime effect classification remain.

## Original review coverage and supporting case studies

| Review theme | Systemic treatment | Supporting V44 detail |
|---|---|---|
| Late behavior discoveries and cross-cutting entry fixes (§2, §4A, §5) | A's early effect contract; C's supported discovery | [04 — Military entry](04_MILITARY_ENTRY_AUTHORITY.md), [05 — Resource buildings](05_RESOURCE_BUILDINGS.md), [06 — Trap Workshop](06_TRAP_WORKSHOP.md), [07 — Entry inventory](07_ENTRY_BEHAVIOR_INVENTORY.md) |
| Candidate repair, missing menu/endpoint/return evidence, discovery→implementation→proof (§2–3, §7) | A's canonical boundaries; C's distinct purposes and short correction loop | [01 — Candidate gate](01_CANDIDATE_GATE.md), [02 — Bank/Watchtower](02_BANK_WATCHTOWER_CAPTURE_AND_ROUTES.md), [03 — Ordinary routes](03_SAFE_ORDINARY_ROUTES.md) |
| Fixture inventory, missing publisher proof, copied metadata/config errors (§4B, §5) | B's test ownership; C's common harness; D's mechanical validation | [08 — Handoff requirements](08_COMPLETE_HANDOFFS.md) |
| Broad fallback and CI cost (§4C/F, §5) | B's resource AND test-boundary work; A's genuine dependency reduction | [12 — CI follow-up](12_CI_FOLLOW_UP.md); existing sharding/static selection are already implemented |
| Capacity serialization and downstream readiness (§4D, §5) | E's WIP/dependency slices; D's accepted-unit state | Partial publication does not itself revoke the V44-first queue |
| Stale state, coverage denominators and reconstruction (§1–3, §4E) | D's authoritative result/acceptance/current views | Geometry, occupancy and accepted public routes remain distinct |
| Velocity measures (§6) | [13 — Delivery measurements](13_DELIVERY_MEASUREMENTS.md) | Reuse existing artifacts; missing timing stays unknown |

Documents 01–08 and 12 are supporting material from the first pass, not nine additional primary initiatives or a current executable dispatch. Their historical candidate, owner and pending-policy notes must be reconciled before implementation. The systemic plans above supersede their priority assumptions.

## Common verification rule

Use focused owning checks while developing, then the repository's final affected gate for an ordinary finished source candidate. Keep full fallback for genuine infrastructure/unknown ownership and preserve static declaration/import consumers. Do not follow a passing full fallback with another local full run. A documentation-only slice uses relevant structure/link validation and whitespace checks.

Live proof is required for a materially changed live boundary that offline evidence cannot establish. Use one representative assigned target unless the contract or observed variation requires more, prove the actual changed public boundary, and retain unchanged accepted cases with a defensible scope rationale. Follow the [canonical live skill](C:/Users/lebel/pnc/.agents/skills/test-bluestacks-live/SKILL.md), [batch contract](C:/Users/lebel/pnc/.agents/skills/test-bluestacks-live/references/live-test-batch.md) and [failure reporting](C:/Users/lebel/pnc/.agents/skills/test-bluestacks-live/references/failure-reporting.md). C's development mode is a proposed amendment, not authority to edit source during a currently immutable live-only assignment.

## Source and document baseline

The deeper analysis is pinned to published a3fcc9e4. Original route evidence remains attributed to private candidate 1d683cf8 and accepted e11 records; neither is asserted to be today's active V candidate. The task-owned plan worktree remains based on 1d683cf8 so unrelated active work is untouched. Before implementation, resolve the then-current source and canonical policy; historical hashes are evidence, not permanent launch targets.

## Evidence index

These links point to local evidence in the primary checkout; they will not exist in a fresh clone. Stable source contracts are tracked; raw artifacts stay ignored. No active evidence or ledger was edited by this planning task.

- **E1** — [Review](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/V44_BLOCKERS_AND_VELOCITY_REVIEW_20260930.md), [coordinator ledger](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/status.json), [active QA history](C:/Users/lebel/pnc/.local-data/live-test-batches/v44-4-integrated-navigation-20260929.md).
- **E2** — [e11 offline review](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/v44-final-offline-e11dc3bb-20260930.json), [live030 review](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/v44-live030-independent-review-20260930.json), [live030 brief](C:/Users/lebel/pnc/.local-data/devin-live-test/briefs/v44-stage-bank-live030-20260930.md).
- **E3** — [Bank safe-body gap](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/v44-bank-sys1-evidence-gap-20260930.md), [Bank settling review](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/v44-bank-loading-independent-review-20260930.json).
- **E4** — [Watchtower review](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/v44-watchtower-independent-review-20260930.json), [ordinary native inventory review](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/v44-ordinary-evidence-independent-review-20260930.json).
- **E5** — [Ordinary entry semantics](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/v44-ordinary-entry-knowledge-review-20260930.md), [military side effects](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/v44-military-entry-auto-collection-20260930.md), [tracked navigation knowledge review](../V44_NAVIGATION_KNOWLEDGE_REVIEW.md).
- **E6** — [CI diagnosis/correction handoff](../../../../testing/PNC_CI_AFFECTED_TESTS_HANDOFF.md), [existing runtime slices](../../../../testing/PNC_CI_RUNTIME_INDEPENDENT_SLICES.md), [test modularity plan](../../../../testing/PNC_TEST_MODULARITY_AND_RELEVANCE_PLAN.md), [performance instrumentation plan](../../../../testing/PNC_LIVE_TEST_PERFORMANCE_INSTRUMENTATION_PLAN.md).
- **E7** — [Building ownership](../../BUILDING_MENU_COVERAGE.md), [core porting contract](../../../../../../instructions/CORE_WORKFLOW_PORTING.md), [portable test guide](../../../../../../tests/README.md).
- **E8 — Post-review changes** — `v44_implementation_slices.slices.V44-4.{turn031_disposition,resource_authority,resource_allocation}` in the [ledger](C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/status.json); [Sepia031 probe](C:/Users/lebel/pnc/.local-data/devin-implement/runs/v44-2-perception-20260926-recovered/turn-031/probe-evidence.json); [geometry proposal](C:/Users/lebel/pnc/.local-data/worktrees/v44-publish-core-20260928/.local-data/v44-next-bank-ordinary-preparation/WATCHTOWER_GEOMETRY_REVIEW.md); [unreleased preparation](C:/Users/lebel/pnc/.local-data/worktrees/v44-publish-core-20260928/.local-data/v44-next-bank-ordinary-preparation/PREPARATION.md); [current canonical live skill](C:/Users/lebel/pnc/.agents/skills/test-bluestacks-live/SKILL.md). E8 superseded parts of E1; the resource policy subsequently published at a3fcc9e4. These historical records do not establish today's active candidate or capacity owner.


- **E9 — Systemic analysis** — [Static selector/coupling evidence](C:/Users/lebel/pnc/.local-data/worktrees/v44-review-action-plans-20260930/.local-data/velocity-analysis/static-selection-and-coupling.json), [saved gate timing summary](C:/Users/lebel/pnc/.local-data/worktrees/v44-review-action-plans-20260930/.local-data/velocity-analysis/saved-gate-timing.json), and [cause assessment](00_ROOT_CAUSES.md). These are read-only analysis of pinned source and saved results, not new qualification runs.

All implementation checklists remain pending. The delivered outcome is this revised, repository-grounded planning pack.
