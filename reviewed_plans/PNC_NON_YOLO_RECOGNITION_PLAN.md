# Integrate visual recognition, guarded controls, and targeted OCR

Status: ready for phased implementation after repository exploration, bounded live investigation, GPT-6 Pro consultation and final Codex audit. Future implementation and promotion gates remain pending; this planning document does not authorize game mutations.

## Context and objective

Complete the specialized recognition architecture: OpenCV identifies supported screens and overlays; reviewed geometry locates fixed controls only after their state is proved; OCR reads requested variable content in bounded regions. Preserve the canonical observation, navigation, spatial, and observed-action interfaces. Exclude YOLO and trained object detection entirely.

Repository baseline: `1026535/pnc`, `b6c1a0176bd80423ba33015440ebac6b620fe001`, verified remotely through the GitHub connector. The current worktree contains the newer recognition and journal changes described in `PNC_SCREEN_RECOGNITION_IMPLEMENTATION.md` and `PNC_FINDINGS_FOLLOW_UP.md`; those local changes take precedence over the baseline. Existing unrelated skill and instruction edits must be preserved.

## Goals and non-goals

1. Give every active screen/control a declared, tested recognition strategy; eliminate silently missing runtime template assets.
2. Recognize blocking surfaces independently of requested content and underlying screen identity. Never infer that a popup is absent solely because a background header matches.
3. Make normalized coordinates express location, not presence, enabled state, free availability, or spending authorization.
4. Read names, counts, timers, coordinates, and row labels only when needed, with explicit OCR regions and frame-local reuse.
5. Preserve postcondition verification and safe abstention, and measure latency without trading away correctness.

Non-goals: YOLO, trained detectors, replacing current world-map spatial algorithms, OCR-engine replacement, arbitrary languages/aspect ratios, new game tasks, spending resources, switching accounts/castles, or sending messages. Existing mutation workflows are not automatically approved for testing by this plan. A successful read-only proof does not establish a mutating postcondition.

## Current state

| Owner | Current behavior and remaining issue |
|---|---|
| `vision/observation_builder.py:ObservationBuilder` | Global visual candidates are computed before scoped OCR, but merged only after enrichment. Strong visual identity therefore does not yet drive a canonical content plan. Geometry can also be materialized before final conflicting evidence is resolved. |
| `vision/visual_screen_recognizer.py` and `data/screen_anchors.json` | Nine profiles, 18 packaged anchors, all-required matching, 540×960 reference and same-aspect scaling. Unsupported/ambiguous cases abstain. Profile coverage and independent negatives remain small. |
| `vision/screen_classifier.py:ScreenClassifier` | Final screen owner; current single-screen classification needs a clearly specified relationship to overlay, layout, and action eligibility. |
| `vision/selectors.py`, `selector_catalog.py`, registry YAML | Canonical normalized regions and click outcomes exist. All 76 effective template/collection paths remain missing. Some controls are actually supplied by OCR or geometry despite template declarations. |
| `vision/pnc_observation_enricher.py:PncObservationEnricher` | Central parsers, popup guards, and row association already exist. Most requests still call full-frame `read_result(image)`; restricting screen families usually restricts parsers, not pixels. |
| `vision/observation_request.py`, `pnc_ocr_capabilities.py` | Canonical request factories and parser eligibility. Coordinate-only proof is already specialized and must not acquire full-frame work. |
| `core/vision/ocr/ocr_service.py` | RapidOCR supports crops and projects results into screenshot coordinates. `CachedOcrService` caches only the most recent image/region pair, so interleaved crops can repeat work. |
| `automation/engine/observed_action_executor.py` and `navigation/screen_flows.py` | Keep sole ownership of execution, fresh observations, retry and postconditions. No new parallel navigation runner. |

The daily return-home scope bug and Settings/More split are already fixed. The journal retry is separate completed work; do not reimplement it in this plan. Current full-suite evidence is 994 tests, 17 skips, zero failures.

## Planning evidence

| Question that affects design | Disposition | Evidence/consequence |
|---|---|---|
| Can an apparently valid header survive a blocking dialog? | `artifact_answered` | `tests/data/screen_recognition/update_over_bag.png`: raw Bag anchors pass beneath an undarkened update dialog. OCR guard must remain until an independently validated replacement proves equivalent protection. |
| Are More and Settings distinct actionable layouts? | `live_observed` | Same-day implementation traces and the new Bag route observe both distinct states and Manage Char. Separate screen contracts remain mandatory. |
| Do dynamic rows have one universal action offset? | `live_observed` | Current Bag screenshot shows Use-only versus Use-plus-bulk rows with different vertical button positions. Locate each row's actual control arrangement. |
| Are Quest tab variants and transition ambiguity observable? | `artifact_answered` | `artifacts/screen_recognition/live/20260910T195757Z_cfa84a53/trace.jsonl` includes both Quest tabs and bounded unknown recovery. |
| Can requested OCR families hide an unexpected source screen? | `artifact_answered` | Hero Hall scope regression and existing tests. Identity/guard work must be independent of optional content requests. |
| Does Android expose useful Settings labels? | `artifact_answered` | Prior same-day UI hierarchy: container/view nodes, no useful text-bearing controls. Do not plan an accessibility replacement for this observed screen. |
| Are all other runtime screens visually proven on the current build? | `unknown`, bounded scope | No. The inventory phase must distinguish existing archived evidence from unavailable feature states. No new selector geometry for those states is assumed here; a workflow remains unpromoted until its particular evidence gate passes. |
| Do Use, Claim, Recruit, Purchase or Send postconditions work after future changes? | `mutation_boundary` | Safe Bag navigation reached visible Use controls and stopped. No mutation occurred. Exact action/target/budget authorization is required before later mutation validation. |

### New bounded live investigation

Target: configured `testing` instance and currently active castle, identity observed in Manage Char without selecting another row. PNC was explicitly foregrounded through the canonical session. The tool did not record whether BlueStacks had to launch, so startup origin is unknown rather than assumed.

Command: `py artifacts/recognition_implementation/plan_bag_probe.py --account testing`. This local evidence harness reuses the existing visual-navigation proof and canonical runtime, changes the final read-only visit to Bag, and caps actions at eight/ten minutes. It is not a production implementation dependency.

Observed seven actions: Home → More → Settings → Manage Char → Settings → Home → Bag → Home. One intermediate Settings frame was unknown and the existing executor reread it before further action. All planned postconditions passed. Stop reason: Bag layout question answered, safely returned Home; no resource mutation, configuration edit, or castle switch.

Run directory: `artifacts/screen_recognition/planning_bag/20260910T203309Z_36134e9b/` (`trace.jsonl`, `summary.json`). Screenshots and OCR sidecars are under `artifacts/2026-09-10/testing/`:

- Baseline: `20260910T203313Z_visual_20260910T203309Z_36134e9b_1_baseline.png`.
- Current Bag: `20260910T203402Z_visual_20260910T203309Z_36134e9b_8_post_action_1.png`.
- Final Home: `20260910T203417Z_visual_20260910T203309Z_36134e9b_9_post_action_1.png`.

Offline prerequisite: `py -m unittest tests.test_visual_screen_recognizer tests.test_validate_visual_navigation tests.test_ocr_service` passed 13 tests. Existing 18-frame benchmark is evidence of initial feasibility, not overall production accuracy. No independent holdout exists for every profile.

## Target design

### One staged observation pipeline

Keep `ObservationBuilder.build()` as the sole entry point:

1. Establish the game viewport/reference transform and a unique captured-frame context. Reject unreviewed layouts; do not stretch arbitrary aspect ratios.
2. Collect global visual screen/overlay/loading evidence. Candidate/request hints may prioritize work but may not exclude unexpected blocking surfaces or source screens.
3. Run mandatory guard recognition, using visual evidence plus the existing full-frame OCR guard until each narrower guard is validated. Resolve identity through `ScreenClassifier` before materializing controls.
4. Build the minimum content OCR plan for the resolved screen, tab, layout, and requested facts. Reuse any full-frame result already acquired for guards rather than unnecessarily OCRing contained crops again.
5. Parse content through existing family parsers; evaluate control-state predicates and row associations; materialize only controls allowed by the final decision.
6. Return the existing typed observation data and diagnostic provenance. Let the observed executor decide and verify actions.

Introduce a small typed `ScreenDecision` owned by `ScreenClassifier`, containing base candidate, effective actionable screen, layout/profile identity, guard outcome, and evidence references. `Observation.screen_type` must have one source of truth: derive it from the decision when migrating constructors/callers, rather than independently updating two authoritative screen fields. Keep raw candidates only as diagnostic evidence. Avoid a general scene graph or a second navigation state machine.

Blocking evidence dominates base evidence. Multiple contradictory blockers or unrecognized occlusion produce an unknown guard and no underlying action eligibility. Known blocking overlays expose only their own independently proved controls. Conflicting base candidates abstain. Loading permits bounded observation waits, never background taps. A content parser cannot clear a blocker or authorize an action on another screen.

The coordinate-only movement proof stays explicitly non-action-authorizing. Its cheap coordinate observation cannot be reused to authorize unrelated taps; action execution needs the normal guarded observation path.

Use four explicit guard states: `clear`, `blocked`, `unresolved`, `not_evaluated`; never infer a successful guard from a default false flag. Migration regressions must prove that supporting evidence cannot cancel incompatible evidence, and same-screen profiles with incompatible layouts cannot authorize geometry. Reconcile contradictions discovered during semantic OCR before publication, clearing rejected rows, spatial targets and text-field states as well as buttons. Geometry cannot prove its own screen prerequisites. Execute required guards even with no visual match or a non-UNKNOWN coarse screen: current loading checks are coarse-screen-gated in both `requires_ocr()` and enrichment. Migrate the capability table as part of moving exact visual classification earlier; its current Bag entry excludes `PNC_BAG`, so merely passing an exact screen into the old gate would suppress Bag parsing.

### Enforced action freshness and read-only policy

Before recognition migration canaries, extend existing capture/observation metadata with a typed frame reference (session epoch, capture sequence/time and input sequence), preserving the existing timestamp. Capture identity is distinct from encoded fingerprints and decoded dataset hashes. Bind verified UI targets and row references to that frame and source state. The canonical observed executor must acquire or validate a fresh proof, re-resolve the intended target, check the allowed effect, dispatch once, then observe the outcome. Reject stale session/input/frame proofs, changed layouts and ambiguous rows; do not rely on an age threshold alone. Extend existing models rather than creating a second action subsystem.

Restrict low-level UI dispatch to this verified path and migrate single-action, explicit-point, list-entry and recovery callers. Coordinate movement retains its existing specialized proof boundary and algorithms. Read-only canaries allow only reviewed navigation from a proved state; UNKNOWN permits passive recapture, not Android Back. Enforce the same policy in `screen_flows.py` and automatic update recovery. Keep resource authorization and reconciliation in their existing canonical owners. Tests must cover bypass attempts and an intervening input, not only normal navigation.

### Catalog and asset ownership

Extend existing typed catalog models, rather than creating a separate control registry. Separate the existing geometric `relative_bounds` from explicit presence/state requirements. Use one detection strategy per selector: visual template, guarded fixed geometry, OCR region, existing dynamic/spatial resolver, or explicitly unsupported.

For the 76 missing paths, enumerate actual callers and assign a disposition. Populate a packaged template only when appearance proof is necessary; convert truly fixed reviewed navigation to guarded geometry; retain cropped OCR for semantic labels and existing typed spatial/row resolvers for dynamic targets. Retire obsolete unused IDs and migrate callers. Unsupported controls must disable the dependent workflow with an actionable diagnostic, not silently disappear; merely marking an active required workflow unsupported does not count as completing its integration.

Use the existing packaged visual-data tree for screen and control assets. Add explicit relative asset paths to the canonical catalog loader where needed, with bounds/mask/reference-size metadata and eager validation. Require every enabled template strategy to resolve a valid packaged asset. Remove the old implicit missing-directory convention after all callers migrate. Package-build validation must prove assets survive installation, not just editable checkout.

The local `pyproject.toml` already declares `data/*.json` and `data/screen_anchors/*.png`; preserve that newer change. The pinned GitHub baseline's absent declarations are not a current missing implementation. Installation proof and any additional control-asset directories are still required. `selectors.py` currently synthesizes template filenames from selector IDs; change this canonical loader contract so registry regeneration cannot restore the retired missing-path convention.

Version profiles by layout/build evidence and include source-frame decoded hashes and review provenance. Thresholds are calibrated on independent positives/negatives per profile; do not treat one global similarity score as a probability. Cache decoded templates/normalized frame representations once per applicable frame, preserving existing matching semantics.

### Control eligibility and repeated rows

Continue using normalized `relative_bounds` and explicit `action_point` in the selector registry for fixed locations. Presence requires a resolved layout and guard; disabled/free/cooldown states require separate visual or OCR predicates. Preserve `materialize_relative_bounds: false` where presence cannot be inferred safely.

For Bag, Quest and other repeated lists, reuse `DetectedListEntry` and existing semantic identity/metadata contracts. First establish each complete row's bounds; resolve the actual button within that row; crop its requested text/count/state; bind the action to that row on the same frame. Do not select a generic Use/Claim label globally, reuse a stale row index after scrolling, or infer a button's Y coordinate from a different row variant. Partial/clipped rows, duplicate ambiguous names and missing controls abstain. Existing mutating authorization and journal ownership remain unchanged.

Retain `resource_inventory.py` card segmentation/blue single-Use detection and `daily_quest_rows.py` row geometry. Their header prerequisites must accept explicit proved screen/tab context when body-only OCR is introduced. Unreadable content is not empty inventory; contradictory Go/Claim labels are unresolved. Revise navigation outcomes that depend on incidental mutation controls: the current Bag destination requires `PNC_BAG_USE_BUTTON`, which must become stable screen/tab evidence instead. Separate maturity from resolver support so `PLANNED` cannot silently mean both disabled and working geometry.

### Targeted OCR and frame reuse

Add an application-owned typed `OcrRegionPlan` (family/purpose, `Bounds`, required fact, failure policy) compiled from resolved screen + request. Keep crop definitions in existing canonical family/catalog owners and move ad hoc duplicates into that owner during each migration. `OcrService.read_result(image, region)` remains the engine boundary and returns screenshot coordinates.

Replace the shared last-result cache with an `ObservationOcrContext` created for each captured frame and threaded through selector detection, enrichment, and debug/discovery consumers. Preserve the `OcrService` protocol and migrate all `CachedOcrService` callers rather than leaving competing caches. Cache by frame, region and preprocessing mode; the context owns one immutable captured image and bounded results, never a mutable cross-thread/global frame cache. Release it after its observation and requested artifacts are complete. Test interleaved A/B/A crops, independent contexts, changed pixels/new captures, and coordinate offsets. No cache reuse across sessions or captures based merely on matching dimensions. If full-frame OCR is already available, select complete contained lines/words where semantics allow; do not manufacture accurate character boxes by clipping an unrelated line. Dedicated crop OCR remains available when segmentation differs.

Include debug sidecars and selector-discovery tooling in this migration: both currently can ask for full-frame OCR after another crop has evicted the one-entry cache. World-coordinate processing must retain its filtered-bar/raw-bar/top-HUD fallback ordering while caching each preprocessing variant separately. A diagnostic export must not silently incur another full-frame engine call.

Crop migration order: fixed fields and coordinates; identity/name and timer panels; Quest rows; Bag rows; remaining active family parsers. Preserve normalization, numeric units, punctuation and ambiguity rules. A requested fact absent from a valid crop remains unknown or receives one named same-frame fallback; it never becomes zero or false automatically.

Full-frame guard/fallback remains an intentional supported strategy for unseen layouts, contradictory evidence, unsupported popups and required-update handling. Crop-only promotion needs representative blocker negatives and equivalent safety outcomes; a failed benchmark keeps the guard in place. The goal is justified OCR cost, not zero OCR at any cost.

## Implementation phases

| Slice | Deliverable, files/components | Dependencies and acceptance |
|---|---|---|
| A — Coverage and measurement | Extend `tools/benchmark_screen_recognition.py`, fixture manifest/annotations, catalog validation and a generated coverage report. Record stage timings, OCR calls/area, full-frame reasons, expected screen/overlay/state, action-point containment and row identity. | Inventory every enabled workflow and all 76 missing paths; establish manual labels, independent source groups, and supported target/layout cells. No runtime behavior change. |
| B0 — Freshness and read-only dispatch | Existing screenshot/observation models and service, `domain/action_requests.py`, both canonical executors, `screen_flows.py`, live-tool wiring. | Depends A. Frame/input provenance, one-use verified UI dispatch, no direct-point/list/recovery bypass; passive UNKNOWN, update confirmation blocked, no unintended roster persistence. Preserve specialized world-map proof. |
| B — Decision and guard ownership | `screen_classifier.py`, `observation_builder.py`, `domain/observation.py`, `observation_request.py`, `pnc_ocr_capabilities.py`; move guard orchestration out of content-family ordering. | Depends B0. One final decision, mandatory guards independent of content scope, no geometry before guard resolution. Migrate constructors/tests and prevent coordinate-only observations authorizing ordinary actions. |
| C — Catalog and fixed controls | `selector_catalog.py`, `selectors.py`, YAML, packaged assets, discovery/updater/validator tools, `pyproject.toml`; caller migrations. | Depends B. First canary Home/More/Settings/Manage Char; then remaining active fixed screens in separate sub-slices. Zero unresolved asset references for enabled template strategies; state predicates block disabled/absent controls. |
| D — OCR planning/cache and fixed fields | `ocr_service.py`, application OCR-plan models, request/capability factories, existing enrichment parsers; retain RapidOCR adapter. | Depends B; coordinate with C regions. Exact coordinate semantics, same-frame reuse, typed missing values, named bounded fallback. Preserve coordinate-only proof cost/contract. |
| E1 — Quest rows | Existing Quest parser helpers, `DetectedListEntry`, Quest follow-up request, row-state fixtures and live read-only probe route. | Depends C/D. Main/Daily distinction, scrolling/clipped rows, duplicated Claim/Go labels and disabled/completed states; correct row/action pairing. No claims. |
| E2 — Bag rows | Existing Bag/resource inventory parsers and consumers, region/row recognition, same-frame button geometry, dedicated saved current Bag fixture. | Depends C/D. Use versus Use-plus-bulk variants, quantity formats, duplicate/partial rows, no cross-row association. No Use or bulk clicks. |
| F — Remaining active family coverage and promotion | Apply C/D pattern to every remaining inventory entry; remove obsolete OCR branches/aliases only after migration, update authored workflow contracts and documentation. | Depends earlier slices. Every required active family has a working strategy and target evidence; unsupported cells remain blocked, not counted as complete. No new object detector. |

For C/F, split work by screen family rather than assigning one worker the entire registry. Luna xhigh can implement bounded assets/schema/caller/test migrations after the controlling agent settles interfaces and reviews evidence; the controlling agent owns ambiguous recognition, thresholds, safety and integration decisions.

## Slice-by-slice live validation matrix

Only one canary target is named: `testing`, its observed active castle. Never infer results for other accounts. All future slices begin `blocked: implementation not yet present`; replace each cell with `passed`, `applicability_skip` with an observed predicate, or a precise blocker after implementation. Current planning observations do not count as future implementation passes.

| Slice | Exact entry point after offline checks | Expected proof and mutation boundary | Current target disposition |
|---|---|---|---|
| A | Existing saved-image benchmark; no emulator action required | Measurement/manifest/call-site inventory only | `applicability_skip`: no runtime behavior change |
| B0 | After adding a bounded `--route navigation` to the existing visual-navigation tool, `py tools/validate_visual_navigation.py --account testing --route navigation` | Passive observation/identity proof then Home/More/Home; enforce fresh dispatch and policy on every path, at most eight transitions total | `blocked`: freshness/policy and route not implemented |
| B | `py tools/validate_visual_navigation.py --account testing` | Home/More/Settings/Manage Char/Quest/Home, no click on unknown/blocked background; retained trace | `blocked`: new decision pipeline not implemented |
| C first family | `py tools/validate_navigation_selectors.py --account testing --selector PNC_BOTTOM_NAV_MORE --selector PNC_MORE_SETTINGS --output-dir artifacts/screen_recognition/navigation` | Each reviewed navigation outcome matches; then canonical safe-root unwind | `blocked`: new eligibility/catalog migration not implemented |
| D fixed fields | Extend `tools/validate_visual_navigation.py` with `--route fields` in slice D; invoke `py tools/validate_visual_navigation.py --account testing --route fields` | Read only already-observed identity/field screens; compare annotated facts and OCR regions, return Home | `blocked`: route and OCR planner not implemented |
| D coordinates | `$env:PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION="1"; py -m unittest tests.test_live_world_map_movement_calibration_smoke` after reviewing its exact navigation contract | Existing coordinate-proof behavior preserved; no march/attack/gather | `blocked`: changed OCR path not implemented; inspect route before opt-in |
| E1 | Extend same canonical live tool with `--route quest`; invoke `py tools/validate_visual_navigation.py --account testing --route quest` | Main/Daily and one bounded read-only scroll if needed; row-state/association observed; no Claim/Go mutation | `blocked`: row OCR migration not implemented |
| E2 | Extend same canonical live tool with `--route bag`; invoke `py tools/validate_visual_navigation.py --account testing --route bag` | Bag labels/counts/button variants on a fresh frame, optional bounded scroll, Home; no Use/bulk | `blocked`: row OCR migration not implemented |
| F each family | Add a named read-only route to that same tool or use an existing family smoke whose terminal actions are inspected first | Observe the feature and safe exit; stop before any mutation; record family-specific applicability | `blocked`: coverage inventory and family implementations pending |

Every live sub-slice: run smallest offline tests, then full suite when shared owners change. Foreground PNC, verify target identity through canonical observation, allow at most eight navigation transitions/ten minutes for planning-style probes, and preserve unique before/after traces plus screenshots/OCR diagnostics. Existing executor settles transient frames; never add blind click retries. Stop on unrecognized popup, unresolved unknown, second identical transition failure, identity mismatch, or mutation boundary. Return Home through the safe-root flow when possible. Split longer routes into independent bounded runs; do not silently enlarge the budget.

Required future live-tool changes must add allowlist tests, safe route selection and a strict no-resource-action boundary. They may not weaken the existing default proof's safeguards. A pre-existing broad daily/chat smoke is not automatically a read-only substitute.

Count attempted inputs and retries against the transition budget. Cap passive settling at three observations; unresolved state ends the route without a blind unwind. Permit evidence/debug artifacts, but suppress roster-store synchronization in read-only probes through the canonical observation-service configuration. `ObservationService._sync_castle_roster()` exists in the current runtime; prior planning evidence proves no game mutation, not absence of every persistence side effect. Do not change authored configuration or install an alternate observation service.

Before any further canary, add an explicit read-only recovery policy to the canonical `ObservedActionExecutionPolicy` and enforce it inside `recover_update_if_required`. The current executor can automatically dispatch update Confirm after a navigation action, bypassing a tool's top-level action allowlist. Slice B must block and retain evidence instead, including pre-action, post-action, settling and recovery paths; preserve separately authorized ordinary-runtime behavior. Test an update appearing only after the allowed tap and assert no confirmation or recovery mutation is dispatched. The completed planning probe encountered no update and its retained trace contains only the seven navigation actions; this does not prove the latent recovery boundary safe.

## Data, config and migration notes

- Do not modify real account/castle/daily-maintenance config or local fixture configuration. Authored recognition YAML and packaged assets are in scope after implementation is requested.
- Inventory runtime selectors, authored YAML references, navigation outcomes, and test fixtures before removing an ID. Keep no legacy aliases merely to avoid migrating callers.
- Freeze evaluation groups before tuning. Require at least two independent capture sessions and a held-out source group for every promoted profile/layout; include different supported resolutions, modal occlusion, loading, wrong tabs, disabled controls and unrelated screens. Synthetic transforms supplement real evidence and are never counted as independent sessions.
- Keep one manifest with decoded-image SHA semantics explicitly documented. Store manual intended control/row boxes separately from implementation-produced boxes to avoid circular tests.
- Different game versions/locales/aspects remain separate evidence cells. A new variant cannot silently inherit a prior variant's action authorization.

## Validation and promotion rules

Representative offline commands: `py -m unittest tests.test_visual_screen_recognizer tests.test_screen_classifier tests.test_capture_and_vision`, `py -m unittest tests.test_selectors tests.test_navigation_selector_validator tests.test_selector_registry_updater`, `py -m unittest tests.test_ocr_service tests.test_daily_live_session`, and existing family tests discovered by A. Add tests for new typed contracts alongside their owner. Run `py -m unittest discover -s tests` for each shared-interface migration and final integration; `git diff --check` for the final artifact.

Acceptance gates for each promoted family:

1. Zero wrong actionable screen/layout/control classifications, zero click-through of annotated blockers, and zero cross-row actions on the reviewed suite. Correct abstention is allowed and counted separately. This is a test gate, not an asserted real-world error probability.
2. Every emitted action point lies inside its independently annotated intended control at supported resolutions. Disabled/missing/ambiguous controls emit no actionable target. Exact-state mutations remain subject to existing authorization.
3. Requested OCR facts equal reviewed expected values or explicitly abstain; compare known-field recovery to baseline so rejecting everything cannot pass. Report per-field errors/missing values, not just screen accuracy.
4. Every active template path resolves in an installed-package smoke; no silent missing-file fallback. Every active workflow's required controls have a completed strategy.
5. Measure at least five warm replays per frame on the same host without concurrent heavy work. Report p50/p95 total observation and stage latency, OCR area/calls/cache hits, and fallback reasons. For crop-migrated families target at least 20% lower median OCR time with p95 observation time no more than 10% above baseline, holding the correctness gates. If unmet, retain the safe path and investigate instead of promoting on a speed claim.
6. The specific canary route passes with no wrong actions. Any unavailable feature produces a typed applicability skip proven on that target; an unobserved feature is blocked. Other targets require their own later authorization/evidence before rollout.

Rollback removes the newly promoted profile/strategy or reverts its coherent code/catalog/assets slice to the last verified revision. Keep one canonical fallback inside the same builder, with explicit reasons; do not maintain two production pipelines or weaken guards to make a test pass. Preserve failure artifacts and add a deterministic regression before retrying.

## Risks, decisions and execution checklist

Primary risks: unknown popups defeat a header-only fast path; dynamic row layouts invalidate fixed offsets; full-frame guard cost may dominate after cropping; stale caches corrupt facts; catalog cleanup can break hidden callers; blanket UNKNOWN can hide lost functionality. The staged guard, row binding, measured cache, caller inventory, and baseline-recovery gates above address these individually.

Open validation questions: which remaining active families lack current fixtures; which guard regions are genuinely sufficient across popup variants; and which family-specific feature states are available on testing. Do not invent those answers. Resolve each during the bounded family evidence gate before defining its coordinates or promoting its behavior.

- [x] Complete Pro consultation and audit recommendations against local evidence.
- [ ] B0: enforce fresh dispatch and read-only recovery before further canaries.
- [ ] A: freeze coverage inventory, labels and baseline metrics.
- [ ] B: settle typed decision ownership and migrate all observation callers/tests.
- [ ] C/D: implement first fixed-navigation and field/caching slices; pass offline/live gates.
- [ ] E1/E2: migrate Quest and Bag rows with independent association/control-state tests.
- [ ] F: finish every remaining required family and remove obsolete paths.
- [ ] Pass installed-asset checks, full regression and per-target promotion matrix; document any precise blockers.

Primary technical references: [OpenCV template matching and masks](https://docs.opencv.org/4.13.0/de/da9/tutorial_template_matching.html), [RapidOCR upstream](https://github.com/RapidAI/RapidOCR). The installed adapter and tests, rather than assumptions about upstream API changes, govern this migration; no dependency upgrade is required by the plan.

## Pro consultation and Codex audit

Completed in [Plan Vision Integration](https://chatgpt.com/c/6aa314f2-7014-83ea-a646-b9fba0e4db14), in Chat mode with visible `6 Pro`, the existing `pnc bot` Project and GitHub connector. Pro explicitly confirmed `b6c1a0176bd80423ba33015440ebac6b620fe001`, inspected root instructions and the recursive tree, and distinguished the narrow inline local overlay from inspected GitHub files. No binary fixtures, screenshots, account config or unrelated content were sent. Pro did not run local tests or independently inspect uncommitted code/assets; Codex supplied and verified those facts locally.

Pro's recommendation: keep one staged observation pipeline and one enforced dispatch boundary; resolve guards and conflicting evidence before geometry; inventory every active selector; preserve specialized row/spatial owners; introduce frame-scoped OCR reuse; promote individual capabilities only after offline and bounded live proof. Broad popup/loading OCR remains necessary on current evidence. Codex agrees and incorporated those requirements.

Codex independently confirmed the consequential findings: loading remains coarse-screen-gated; Bag's capability gate excludes its own exact screen; classifier compatibility uses `any` supporting evidence; low-level taps trust the supplied observation; update recovery and UNKNOWN Back can bypass a superficial allowlist; template paths are synthesized; Bag's navigation outcome requires Use; roster synchronization is an observation side effect. B0/B/C now name those migrations and their regression gates. Existing Bag card/button parsing is retained rather than duplicated.

Corrections and limits: local `pyproject.toml` already includes JSON/PNG data and a direct OpenCV dependency, so baseline omissions do not describe the current worktree. Installed-wheel proof remains pending. Matching aspect ratio alone does not prove viewport insets or control geometry. The matcher's 256-candidate cap is bounded search, not a guaranteed combined-score optimum; fallback/abstention and confusing-negative tests must cover it. Crop caching must distinguish backend/configuration revision and preprocessing, preserve successful empty results, and never cache exceptions as success. OCR offsets apply exactly once; synthesized word boxes are not precision click boundaries. No global OCR-free fast path or mutation success claim is accepted.

Most relevant files Pro reports inspecting at that exact commit: `AGENTS.md`, planning skill/references, `pyproject.toml`, screenshot service, OCR/template services, app entrypoint, observation/action models, builder/enricher/request/capabilities/classifier, selectors/catalog/interactions/YAML, resource inventory, daily rows, world-map coordinates/proof, screen flows, both action executors, daily live session and mutation dispatcher; tests for OCR, daily session, resource inventory, classification, selectors, capture/vision, world-map movement, automation framework and flows/tasks. Large files were inspected in relevant sections, not audited end to end. The linked consultation retains the full file list and reasoning.

Readiness verdict: the phased plan is concrete enough to implement. Unknown family/layout coverage is an explicit implementation evidence gate, not assumed support. Mutation postconditions remain outside this planning authorization. No product decision requires clarification before beginning the non-mutating implementation slices.

Planning validation: targeted prerequisite command passed 13 tests; bounded Bag investigation passed seven navigation actions and returned Home; `git diff --check` passed. Full suite was not rerun for this planning-only artifact; the separately recorded 994-test result is the pre-plan baseline, not a validation claim about future changes.
