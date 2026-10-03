# V44 quality review and revised implementation sequence

## October 2 scope override

The parent's [user-directed exclusions](../V44_FULL_HOME_CITY_NAVIGATION.md#october-2-user-directed-scope-reduction)
remove Sanctum, Bank, Lost City Headquarters and Dragondom Conquest from V44's
required route work. This overrides the Bank-first and Bank/Watchtower cohort
instructions below and any earlier Bank-recognition amendment. Preserve those
historical findings and unfinished source, but stop excluded-target correction
and live validation. Continue Q4/Q5 using retained targets such as Watchtower;
Bank success is no longer their prerequisite. Shared tooling still requires its
own applicable proof, and excluded routes must not be reported as accepted.
Sol remains disabled under the user's current staffing instruction; the lead
owns complex decisions and review, with Devin handling concrete work and live
execution. Existing accepted Q1/Q2/Q3 proof remains recorded in the ledger.

Reviewed September 30, 2026 by the V coordinator. **Maintainable architecture, canonical ownership, testability and a sound development/validation workflow take priority over completing V44 quickly.** This is the user's revised priority. V44 remains incomplete; accepted route units and externally owned work retain their existing dispositions. The broader V queue is not released by this review.

## Scope, evidence and verdict

Reviewed the originating task's uncommitted `README`, `00`, `09`, `10`, `11`, `13`, `14` and `15` in `C:/Users/lebel/pnc/.local-data/worktrees/v44-review-action-plans-20260930/plans/themed/vision/modules/v44/review-actions-20260930/`. That worktree remains at `1d683cf8`; its analysis is pinned to published `a3fcc9e4184006ee22abe850d01c1f84f80b34bb`. The coordinator inspected actual published source at a3 and private V source `0618d35c114ee16ca56e86b74b60760b9549340e`, with independent bounded architecture and test-ownership audits. The originating documents were neither modified nor moved. A hash manifest and detailed review provenance are retained under the coordinator's ignored evidence directory.

**Implementation readiness:** the bounded packages below are ready with the specified corrections; the original pack is not approved as an undifferentiated refactor. **Promotion readiness:** no new runtime or live acceptance is established by this review. Existing source/evidence remains usable within its reviewed scope.

Saved path simulations select 292/410 modules for camera implementation, 225 for a camera asset, and 410 for a Home fixture. These are hypothetical body-change selections, not executed gates or promised savings. The saved e11 result reports 1,949.409 seconds of execution and 2.094 seconds of selection over an older 409-module inventory. No new test, matcher/OCR run, benchmark, emulator observation or live exploration was needed for this review.

## Actionable findings

### R1 — Prioritize a demonstrated publication defect before speculative extraction

Plan14 A3 (lines30–36) identifies duplicate assembly but leaves its first change open. At a3, `vision/observation_builder.py:881–902` publishes `ObservationAdditions.current_pnc_account_id`; `vision/navigation_perception.py:341` starts a separate content replacement that omits it. The same enricher produces that field (`pnc_observation_enricher.py:6961–7001`), and `tests/integration/vision/test_login_observation.py` asserts its legacy publication. This is a source-proven mapping difference, not a demonstrated live account-selection failure.

Start with a deterministic reproduction, establish the intended common content contract, then fix the omission and map those common fields once. Keep independent screen classification, interruption decisions, OCR scopes, visible-control selection and building-control filtering in their current owners. Never copy every additions attribute indiscriminately: content must not replace screen/control authority. Move `ObservationAdditions` to a neutral vision contract only if needed to avoid a builder/helper import cycle, preserve class identity and migrate its real producers/consumers together. Reuse `observation_provenance.py` binders. Do not create another parser or normalize away publisher-specific policy.

### R2 — Packaged camera assets have more consumers than Home screenshots

Plan09 B1 must distinguish two ownership maps before narrowing rules. Verified Home screenshot readers fit `unit.app.pnc.vision.home_city_camera` and `integration.vision.home_city_camera`. Packaged camera crops additionally reach **`unit.app.pnc.navigation` and `integration.workflows`**: `home_city_camera/catalog.py:606–613` opens every crop; `home_city_camera_target()` loads that catalog; scan/normalization tests call it, spatial pan logic calls it, and `test_open_building_core.py:459–501` constructs real navigation. Corrupting a Bank crop can therefore break a different building's caller. These are a minimum verified set, not a claim that the closure audit is finished.

Full rules precede resource rules (`tools/test_selection/planner.py:80–101`); resource matches union owners (`ownership.py:26–28`). A narrow pattern cannot override `tests/data/*` or the broad `vision/data/*`. First implement the audited screenshot subtree, retaining unknown/shared fallback. Narrow packaged assets only after closure mapping; replace their broad overlap while explicitly retaining owners for existing sibling assets. Unknown new paths must fall back. Do not add precedence tricks, exclusions that hide consumers, or a new selection engine. Update the synthetic inventory in `test_scoped_ownership.py:14` when adding groups, or rule validation will reject empty groups.

### R3 — Discovery needs an explicit capture and dispatch contract

Plan15 C2/C3 correctly identifies a missing capability, but must specify how a task-owned unknown menu survives capture. `CoreRuntime.observe()` invokes automatic interruption recovery (`core_runtime.py:115–145`); its existing single-capture path is private. The tracked discovery adapter needs a supported single persisted capture/perception operation that does not auto-dismiss the task-owned surface. Reuse the existing capture implementation and lease; do not duplicate perception or call private internals from a growing script family.

`ActionExecutor._authorized_input()` rejects raw points on blocked/coordinate-only observations (`action_executor.py:469–531`). A developmental measured-control operation must have its own narrow, reviewed authority at that boundary, or a development-only adapter with one canonical implementation using session provenance and actual receipts. It must not become a generic workflow raw-tap API, disable the ordinary policy, forge a clear decision, or reclassify a task menu as an unrelated popup. `BlueStacksSession.authorized_input()` remains the session/epoch/latest-frame/input-sequence/age/no-replay owner.

The reviewed ignored helper provides migration evidence, not the target architecture: it has scoped policy interception and a manual session path. Its concurrent request/response mechanics passed synthetic checks, but real visual turnaround inside its 20-second annotation window is unproved. Do not promote that window or copy its monkeypatching as a general contract. The first discovery can succeed with an identified native menu capture and no menu input. Subsequent input requires a freshly identified control; never extend frame age or replay old coordinates to make the pilot appear successful.

### R4 — Agree the minimal result contract before implementing the runner

Plan11 D1 follows the live-tooling work too late if interpreted as a separate schema retrofit. The base `evidence.json` v2 template has candidate/case/artifact fields, but does not standardize all helper bindings or primitive receipts D1 proposes to validate. Live030 already adds ad hoc `helper`, `dispatches` and `budget` structures, including both logical counters and physical-boundary counters. Formalize those existing concepts with C2 first; do not assume `attempts` means physical inputs.

Use one versioned assignment binding and one typed result extension/envelope referencing existing `InputDispatchRecord`/`InputDispatchFailure` data. Include selected case IDs/purpose, candidate/import root, helper or tracked-tool binding, artifact references, actual receipt attribution, cleanup and incident references. Preserve historical v2 files and their independent reviews; an absent historical field is explicitly unsupported evidence, not a fabricated value. Update the active producer and parser together. No `eval` of historical repr timestamps or automatic promotion from worker `passed` labels.

Independent acceptance references immutable result paths/hashes and records retained proof with reasons. Rendering changes only the V coordinator-owned current block; the coordinator is its sole writer. Map existing readers/writers before retiring active duplicate fields, preserve historical records, and avoid leaving two current blocks with equal authority. Incident index ownership stays with the weekly collector. A broader reporting service or whole-history conversion is unnecessary.

### R5 — Bound extraction and workflow changes to demonstrated needs

Plan14 A1 is a useful pilot only when the whole import closure is addressed. Importing `home_city_camera.models` still runs the eager package initializer. Move the cohesive value cluster outside that implementation package, not just the import spelling. A neutral domain sibling for catalog/target geometry may be clearer than mixing it into the existing camera-proof module; establish the dependency graph first. Preserve supported facade aliases as the same objects. Real catalog/localizer consumers remain selected. Stop further moves if measured import reach is unchanged and no independent ownership benefit is demonstrated.

Defer A2's larger Home extraction: `_HomeCityOperation`, scan and reacquired entry share one deadline, actuator and frame lifetime, while `home_city_scan.HomeCityScanState` already has a focused owner. Extract the cohesive operation only for a concrete upcoming change whose testability/ownership improves. No second normalizer, universal route registry or all-feature migration.

C4's development-owner pilot requires an explicit phase contract before dispatch. Keep the existing acceptance live-only mode immutable. A bounded implementation owner may perform an authorized frozen live phase, stop/release its live processes and task leases, make a routine scoped correction, run focused checks, and freeze the next candidate. Complex or shared-contract uncertainty returns to the lead. The lead still independently reviews final source and acceptance evidence. This review does not silently change an already issued immutable brief.

## Proposal dispositions

| Proposal | Decision | Required change or limit |
|---|---|---|
| A1 neutral contracts | Accept revised pilot | Audit parent initializers and the complete value cluster; retain real composition consumers and class identity. No promised selection reduction. |
| A2 Home extraction | Defer | Require a concrete next ownership/testability benefit; preserve the single operation lifetime. |
| A3 common publication | Accept, first source priority | Reproduce account-field divergence; share content binding only, preserving guard/control policies. |
| A4 entry effects | Reuse existing work | Private0618 already owns classification and effect-aware admission. Reconcile its net change; do not add a second contract/allowlist or repeat collection permission requests. |
| B1 fixture/assets | Accept in two bounded steps | Screenshot owners first; separate complete packaged-asset closure including navigation/workflow consumers. Preserve shared/unknown fallback. |
| B2 expensive tests | Accept audit; defer deletions | No redundant native replay has yet been proved. Remove only with an old-to-new assertion map; keep real publisher/provenance and independent native negatives. |
| B3 proof reuse | Accept now | Focused development checks; one final coherent candidate gate; retain only demonstrably unaffected proof. |
| C1/C2 purposes and tracked harness | Accept revised | Agree minimal D1 binding first; one supported composition path, typed Python cases, no copied action-policy engine. |
| C3 developmental controls | Accept with R3 contract | Preserve task-owned captures; a capture result is separate from public-route acceptance. |
| C4 same-owner development | Accept bounded pilot after contract amendment | Frozen phases and released task resources between edits; acceptance stays independent. |
| C5 invalidation | Accept | Review changed behavior/assets and actual consumers; a new SHA alone neither invalidates everything nor proves independence. |
| D1/D2 validation/current view | Accept staged | D1 minimum accompanies C2; D2 renders one cohort/current block afterward, retiring duplicate active writers. |
| E capacity/slicing | Accept immediately | One heavy owner plus one prepared package as the initial WIP limit; useful independent light work allowed. No blanket M/PW hold or new scheduler. |
|13 measures | Accept lightweight recording | Use actual existing timestamps; unknown stays unknown. No benchmark prerequisite, historical reconstruction project or claimed percentage savings. |

Rejected approaches: changing import spelling without dependency isolation; weakening selector recall to make suites smaller; deleting expensive tests based only on timings; copying the full ignored driver into tracked tooling; a generalized raw-input bypass; a second acceptance database/scheduler; and treating all five initiatives as a prerequisite for every unrelated V/M/PW change.

## Revised sequence and initial work packages

| Package / owner | Bounded deliverable and dependency | Owning/downstream proof | Live applicability |
|---|---|---|---|
| **Q1 — Shared publication contract / Sol implementation, lead acceptance** | R1 reproduction, common typed content binding, minimal neutral additions contract if required; migrate both publishers and real imports. No camera algorithm, classifier or control-policy redesign. Coordinate shared publisher fields with M before editing. | `tests.unit.app.pnc.navigation.test_navigation_perception`, `tests.integration.vision.test_login_observation`, focused both-publisher contract using `tests/support/pnc/publication.py`, relevant provenance/blocked-content suites, architecture/API/static import consumers. | Pure mapping parity is offline-provable. Review connected consumers; if an identity/action decision changes, include that boundary in the next assigned non-Main batch. Do not switch accounts merely to exercise the field. |
| **Q2 — Home evidence ownership / Devin concrete implementation, lead acceptance** | B1 fixture-first rules and consumer/fault map, with packaged-asset closure as a separate handback. Existing `selection_rules.yaml`, selector tests and tests guide only. Can proceed beside Q1 with disjoint ownership. | `unit.test_selection`, `test_harness`; controlled owning-reader failure; owned/shared/unknown/mixed resource cases, coverage filtering, declaration/import retention and real-rule inventory. Final infrastructure affected fallback remains full. | None for selection/test-only changes. |
| **Q3 — Neutral camera values / Sol after Q1 contracts stabilize** | One complete value-cluster import pilot, before further broad Home-camera feature additions. Preserve real loader/localizer dependencies; no A2 operation extraction. | Catalog/target/scan/normalization groups, public import identity, architecture boundaries; same-path before/after static selection with identical method. Final changed-declaration consumers remain selected. | None for demonstrated behavior-equivalent value/import relocation. |
| **Q4 — Tracked live case/result path / lead design, Sol complex boundary, Devin concrete migration** | Minimum C1/C2+D1 together: typed assignment/cases/results, canonical composition and receipts, one migrated V44 cohort. Reuse existing discovery analyzers/audit tooling where appropriate; no recursive artifact inventory during handback. Reconcile0618 entry-effect work before collecting-entry cases. | Existing session/frame/executor/runtime lifecycle tests, `tests.unit.tools.test_discover_selector_registry_tool`, new owning tool fakes for wrong binding, missing/extra case, stale/unknown control, uncertain receipt and cleanup; one saved accepted030 package exercises parser compatibility. | One already-needed157_farm batch proves actual lifecycle, dispatch and cleanup; no extra trip solely for report formatting. |
| **Q5 — Qualified developmental cohort / Devin owns frozen live phases, lead acceptance** | C3/C4 pilot after Q4 boundary and brief/skill phase amendment. Reuse Watchtower source/holdout correction and effect-aware entry; develop retained menu/return facts and ordinary coverage in compatible batches. Final acceptance calls real production routes. Apply the October 2 exclusions; Bank is parked. | Scoped geometry/publication/route and effect tests after meaningful changes; one final affected gate on the coherent source, then distinct changed-boundary live cases. Existing accepted Market/Hall/Campaign proof retained only with reviewed scope rationale. | Required for retained body/menu/destination/return and changed dispatch/effects. Non-Main resource allowance applies; Main and foreign reservations remain protected. |
| **Q6 — Consolidate proven waste / coordinator with owning implementer** | D2 single current view, B2 assertion-preserving test consolidation, and any justified A2 extraction. Use Q4/Q5 experience; neither dashboard work nor speculative extraction blocks an otherwise accepted unit. | Parser/renderer fixtures and surviving unique assertions, owning/downstream suites for any changed implementation. | Renderer/test-only work needs none; changed runtime mechanics need their affected production proof. |

Q1 and Q2 are the first ready implementation packages. Source work and tiny deterministic checks may overlap within the declared allocation; matcher/OCR, broad gates and live work wait for the heavy owner. Integrate disjoint infrastructure changes coherently when ready and let one final affected gate cover the exact combined candidate; do not run separate duplicate full suites for unchanged content. Independently useful packages need not wait for a delayed peer. Each result records its own focused proof and the exact shared final gate it consumed.

Q3/Q4 replace the old automatic trigger to launch another copied Bank/Watchtower helper immediately after CPU return. The private0618 branch, geometry diagnosis and reviewed helper are preserved as reusable implementation/evidence. Do not mix the known failing Watchtower candidate into Q1/Q2's infrastructure baseline or hide its failed holdout with narrower selection. Reconcile source from then-current main and port reviewed net changes with explicit consumer review; no whole-file copy or blind cherry-pick that imports unrelated pending code.

## Coordination, holds and release conditions

- **V:** hold new route fan-out, further mutable ignored-helper expansion and the previously prepared live release while the affected Q3/Q4 contracts are unresolved. Continue Q1/Q2 and saved-evidence preparation. Existing route acceptance and publication stay recorded; V44 completion still requires remaining owned behavior proof.
- **M:** current clean `a79f3168` final gate owns heavy CPU, as acknowledged during this review. Do not interrupt it. Before Q1/Q4 source edits, exchange exact shared `ObservationAdditions`/publication, `NavigationCore`/`WorkflowContext`, action/executor/provenance and runtime fields with M. Serialize integration and affected revalidation only at those overlaps. Unrelated M implementation is not held.
- **PW:** retain the user's pause and feature ownership. Do not wake it for this review. Record any shared publication/workshop contract impact for its next authorized resumption; never claim its feature accepted from a V route.
- **Gate owners:** workers own implementation evidence and frozen live execution; V lead owns design, independent review, invalidation, integration and publication. M returns the heavy window explicitly; that return releases capacity, not the old superseded live brief. CPU ownership never substitutes for a configured instance lease/reservation.
- **Broader V queue:** retain V44-first and delegated-ownership exclusions. Partial accepted units may be published. A named downstream queue exception requires an explicit sequencing decision when not already authorized; whole-V44 completion, route readiness and queue release remain separate facts.

Record readiness/waits, actual execution and review timestamps, repair findings and accepted units in the existing ledger. Do not infer starts/releases from file times, silence or green process exit. The existing worker callbacks/waits provide continuation; no additional polling automation is required.

## Review completion and limits

This review used source inspection, saved result/selection evidence and two bounded independent audits. The document changes require link/structure checks and `git diff --check`, not unit or live tests. Implementation, runtime parity, selector recall improvements and any performance benefit remain to be demonstrated by their owning packages. No publication or acceptance of private0618 is implied.
