# Independent code slices for test runtime and modularity

Date: 2026-09-28. Planning baseline: `07563e98bc99fb10de00873b51dc8291484ea7ba`.

Execution authorized 2026-09-29 with persistent GPT-5.6 Luna xhigh workers and lead-owned orchestration/review. Execution first incorporates `origin/main` at `1c04b313`, preserving the newer exact-slot and Castle-body fixes. Feature workers start from the subsequently recorded S0 commit.

This is the execution breakdown for the remaining work in the [test modularity plan](PNC_TEST_MODULARITY_AND_RELEVANCE_PLAN.md). Current code and this document supersede that older plan's original inventory, timing, and blanket shared-contract fallback assumptions. Preparing these assignments does not launch workers.

## Current acceptance and remaining objective

Already completed: immutable template caching; camera and navigation unit-suite splits; four CI execution partitions; immediate failure tracebacks; three Windows path regressions; and scoped owner/downstream/API selection with a static floor for declarations and import changes. Preserve these changes.

Full candidate CI passed with 381 modules and 3,421 cases: 3,415 passed and six skipped. [Pre-merge run](https://github.com/1026535/pnc/actions/runs/36494793091) took 23m12s; [main run](https://github.com/1026535/pnc/actions/runs/36497245766) took 14m21s on the same commit. These are observed complete runs, not isolated optimization benchmarks or guarantees about every future runner.

The remaining objective is to remove genuinely repeated expensive test work, give large feature modules smaller cohesive owners, and make internal feature edits select less work where dependencies allow. Keep standard CI below its existing 30-minute job limit. A smaller selected set is not acceptance if it loses meaningful assertions or downstream consumers.

## Assignment structure

Five feature slices are independent of one another. Each owns a different production feature, its tests, and its support package. A small shared preparation precedes the parallel work; integration and coverage measurement follow it.

| ID | Package | Existing production lines | Existing captured-suite lines | Suggested executor |
| --- | --- | ---: | ---: | --- |
| S1 | Home Camera catalog, calibration, localization and publication | 2,382 | 923 | Luna xhigh; Devin with the settled brief |
| S2 | Pet Workshop board, orders, overlays and OCR | 1,583 | 1,527, plus 398 analysis | Luna xhigh; Devin with the settled brief |
| S3 | Bag identity parsing, rows and previews | 750 | 802 | Devin or Luna xhigh |
| S4 | Research tree, detail and queue readers | 998 | 521 | Devin or Luna xhigh |
| S5 | Campaign map, chapter and publication | 786 | 1,170 | Devin or Luna xhigh |

These counts establish scope and responsibility boundaries; line count alone is not a reason to split a cohesive function. The earlier local complete run identified these captured suites among its expensive modules. Each worker measures its own comparable before/after workload rather than treating older timings as a current benchmark.

```text
S0: settle and publish the shared test-construction helper
                         |
        +--------+-------+-------+--------+
        S1       S2      S3      S4       S5
        +--------+-------+-------+--------+
                         |
S6: integrate, validate affected selection/CI, and measure coverage once
```

Start all feature workers from the same recorded commit after S0. Use separate task-owned worktrees. Devin branches use `devin/`; Luna/Codex branches use `codex/`. Run up to three substantial packages concurrently; remaining packages need only a free worker slot, not another feature's output. A worker may finish one package and then take another.

## Fixed interfaces and common acceptance

- Preserve existing public import paths, constructor signatures, returned typed values, screen/layout identities, frame provenance, abstention rules, bounded OCR, and measured control geometry. No game behavior, threshold, selector asset, fixture provenance, or resource-spending change belongs to these slices.
- Convert a genuinely mixed feature module into a package at the **same import path**, with one implementation owner per concept. For example `vision/research.py` becomes `vision/research/__init__.py` plus cohesive internal modules. The package boundary exports the existing supported API; internal units import their canonical owner. Remove the superseded `.py` file and migrate private helper imports. Do not introduce a second implementation or a permanent obsolete-file shim.
- Use the existing `selector_catalog.default_selector_asset_root()` for packaged `vision/data` assets. Every listed source currently anchors assets beside `__file__`; moving code must preserve those actual asset paths. Keep all authored assets and fixtures read-only.
- Unit and integration subpackages mirror the new production owner, such as `tests/unit/app/pnc/vision/research/` and `tests/integration/vision/research/`. Existing test IDs may move, but their covered contracts must remain. Small files should follow responsibilities, not arbitrary line or method quotas.
- Keep a compact old-test/subtest-to-new-test ledger, including fixture, viewport, publisher, assertion/contract, and whether a case moved or was consolidated. Delete a test only when another test proves the same contract at the same meaningful boundary. Report nonduplicates instead of deleting them to meet a count target.
- Move parsing, geometry, classification and failure cases to direct feature units when they do not need both production publishers. Use direct producer/localizer tests on captured frames for pixel regressions that do not exercise publisher wiring. Keep a small real publication set covering supported surfaces, publisher agreement, provenance, guards and actual OCR boundaries. Preserve distinct viewport/art assertions at their meaningful owner; they need not each traverse both publishers. A native/reference resize is not independent capture evidence.
- Reuse immutable setup only. Each observation keeps fresh frame identity, OCR context and mutable recording state. Do not cache `Observation` outputs, OCR answers, negative-test state, or publishers across tests that mutate them.
- Do not edit `core/vision`, shared observer/enricher implementations, selector catalogs, other features, runner/policy/CI, resource rules, or shared documentation. If a necessary edit falls outside the owned set, return the exact caller/interface and proposed change to the lead before editing it.
- An internal helper body edit should have an explained scoped plan without an unknown-owner full fallback. Keep actual API/downstream consumers even when that remains broad. Report remaining import/composition coupling; do not weaken selection to manufacture a smaller number.

## S0 — shared preparation, one lead-owned writer

Before dispatch, record the common acceptance SHA and create one coordinator ledger under ignored `.local-data/ci-runtime-feature-slices-20260928/` in the primary checkout. The lead owns that ledger, shared interfaces, integration, and final validation. Workers return handbacks; they do not maintain competing status files.

Create one small test-construction helper at `tests/support/pnc/publication.py`. The current `_wire` / `_production_components` helpers repeatedly construct a real `ObservationBuilder` and `NavigationPerception`. Settle this interface before parallel migrations:

```python
def make_publication_pair(
    *,
    selector_registry: SelectorRegistry,
    matcher: OpenCvTemplateMatcher,
    enricher: NavigationGuard,
    ocr_service: OcrService,
    ocr_backend_revision: str | None = None,
) -> tuple[ObservationBuilder, NavigationPerception]:
    ...
```

It constructs fresh publishers over the supplied real dependencies and the existing packaged visual recognizer. Navigation uses the builder's recognizer, classifier, enricher and `create_ocr_context`. Leave the builder's existing backend-revision default authoritative when no override is supplied. It imports no concrete feature producer, chooses no screen, creates no default producer graph, and introduces no caching or configurable factory framework. Feature wrappers still own their producer injection, capture creation, OCR wrappers and exceptional request semantics.

Use the first feature's migrated real publication case to qualify the helper, then reuse that stable interface. A constructor-only test that mirrors its arguments is not sufficient proof. Do not migrate other workers' callers in S0. This preparation is intentionally small; the lead can complete it without launching another worker.

## S1 — Home Camera

**Owned existing files:** `pnc_automation/app/pnc/vision/home_city_camera.py`; the nine `tests/unit/app/pnc/vision/test_home_camera_*.py` modules; `tests/integration/vision/test_home_camera_publication.py`; `tests/support/pnc/capture_vision/home_camera_fixtures.py` and `home_camera_doubles.py`.

**Owned new packages:** `vision/home_city_camera/`, matching unit/integration `home_city_camera/` packages, and `tests/support/pnc/home_city_camera/`.

1. Separate catalog/normalization loading and immutable catalog values from localization and target publication. Existing seams include `load_home_city_camera_catalog`, `_load_view_normalization`, `_CameraVote`, `_CameraHypothesis`, `_fit_zoom_translation`, `home_city_camera_target`, and `merge_camera_target_objects`. Keep tightly coupled consensus fitting together; do not invent a plugin strategy or duplicate fitting rules.
2. Move the existing already-split unit modules under the new canonical feature owner, preserving their cases. Further split only where a module still mixes independent responsibilities.
3. Make existing tracked assets and calibrated scene geometry the basis of deterministic catalog, transform and projection units. For useful synthetic localizer cases, compose assets at independently specified poses; expected values must not come from the localizer under test. Do not make portable tests depend on ignored APK/Devin evidence or add a speculative renderer. If a necessary verified texture is not tracked, return its provenance and the smallest proposed portable fixture to the lead.
4. Divide captured cases by localization/zoom proof, measured target publication, and negative/provenance boundaries. Run pixel regressions directly against their localizer/producer unless publisher wiring is part of the assertion. Retain both real publishers where agreement/provenance is the contract and qualify S0 through the existing feature wrapper.
5. Record a compact captured-evidence matrix: frame, build/source, crop-source versus regression versus independent holdout, covered obligation, and required test boundary. Keep the smallest saved-frame set preserving observed native zoom, HUD occlusion, wall-corridor, target-body and negative-match regressions. A synthetic scene or reused crop-source cannot replace independent rendered-pixel evidence. Existing captures suffice for this refactor; no fresh live acquisition is assigned.

**Acceptance:** catalog assets still load from their original packaged paths; all original fixture/zoom/target/provenance obligations have a ledger destination; missing/conflicting/clipped evidence still abstains; native zoom and wall/Goddess/Tower/Institute cases remain covered; the owned workload passes and comparable expensive work decreases or its remaining necessity is documented.

**Why keep some captures:** [packaged layout evidence](../../../docs/game-reference/workflows/home-city-layout.md) establishes the 5.0.203/233 scene structure; [calibrated slot evidence](../../../docs/game-reference/workflows/home-city-slots.md) provides search geometry, not occupancy or tap authority. The later [native camera evidence](../../../docs/game-reference/workflows/home-camera-navigation.md) includes 5.0.204/235 wheel frames: an off-grid zoom changed Institute matching, restored zoom did not restore pan, and the Goddess column was darker in the baseline and occluded in another view. Asset-driven units cover known geometry efficiently; those saved frames check observed rendering and abstention. Neither replaces fresh frame/body proof during actual navigation. Preserve each source's recorded build rather than claiming current installed-build verification.

**Focused baseline:** the named home-camera unit modules and `tests.integration.vision.test_home_camera_publication`. After migration use `group unit.app.pnc.vision.home_city_camera` and `group integration.vision.home_city_camera`.

## S2 — Pet Workshop

**Owned existing files:** `pnc_automation/app/pnc/vision/pet_workshop.py`; `tests/unit/app/pnc/vision/test_pet_workshop_publication.py`; `tests/integration/vision/test_pet_workshop_publication.py` and `test_pet_workshop_analysis.py`. The shared synthetic domain fixtures at `tests/support/pnc/pet_workshop.py`, solver support and domain solver are read-only. Keep that canonical fixture owner at its existing path: moving it into publication support would unnecessarily couple domain/solver tests to a publication package.

**Owned new packages:** `vision/pet_workshop/`, matching unit/integration `pet_workshop/` packages, and `tests/support/pnc/pet_workshop_publication/`.

1. Keep `WorkshopContentProducer` as the public entry point. Separate board/cell reading, order/reward/card segmentation, and OCR text/count processing using the existing `_read_cells`, `_read_orders`, `_read_strip_rewards`, `_join_region_lines`, `_count_zone_ocr_image`, and `_detect_card_extents` seams. Split only connected groups that have an explicit input/output boundary.
2. Move the scripted header/count-context cases out of the expensive publication suite into direct feature units. Separate board/selection, modal surfaces, real header OCR and saved-frame analysis suites. Adopt S0 while keeping feature-specific matcher injection.
3. Consolidate repeated full-stack setup or assertions only where the ledger proves equivalent coverage. Retain each distinct LV6/LV8/LV10, RGBA, selected-state, clipped-card, overlay, and observed energy/count regression.

**Acceptance:** typed board/order/reward/control outputs and frame/layout provenance remain identical; conflicting counts and incomplete item/selection evidence remain unknown; excluded storage/foreign Manor behavior remains covered; real OCR cases remain real; no solver or live-action behavior changes.

**Focused baseline:** the three named Workshop modules above. After migration use `group unit.app.pnc.vision.pet_workshop` and `group integration.vision.pet_workshop`.

## S3 — Bag

**Owned existing files:** `pnc_automation/app/pnc/vision/bag_items.py`; `tests/unit/app/pnc/vision/test_bag_items.py`; `tests/integration/vision/test_bag_items_publication.py`. Bag layout/domain/navigation code is read-only.

**Owned new packages:** `vision/bag_items/`, matching unit/integration `bag_items/` packages, and `tests/support/pnc/bag_items/`.

1. Separate OCR identity/count parsing from card geometry/projection and preview reward publication. Existing seams include `_CardLine`, `_owned_count`, `_identity_for_tab`, `_speedup_identity`, `_military_identity`, `_misc_identity`, and `_mark_duplicate_identities`. Keep one canonical identity parser and duplicate-marking rule.
2. Separate parsing units, family/tab publication, and chest-preview publication. Parsing permutations and duplicate identity decisions use direct units; real OCR/native/reference geometry and both-publisher agreement stay in integration where required.
3. Adopt S0; keep the Bag bounded-OCR wrapper and independent preview identities. Preserve fresh frame/call records per case.

**Acceptance:** Speedup/Treasure/Military/Misc identities, applicability/counts, tab-switch isolation, Arena/Common previews, duplicate reward rows, native/reference geometry and provenance retain coverage. Bag frames must not publish preview facts and preview frames must not publish Bag items.

**Focused baseline:** `tests.unit.app.pnc.vision.test_bag_items` and `tests.integration.vision.test_bag_items_publication`. After migration use `group unit.app.pnc.vision.bag_items` and `group integration.vision.bag_items`.

## S4 — Research

**Owned existing files:** `pnc_automation/app/pnc/vision/research.py`; `tests/unit/app/pnc/vision/test_research_category_facts.py`; `tests/integration/vision/test_research_captured_acceptance.py`. Research domain, navigation and resources are read-only.

**Owned new packages:** `vision/research/`, matching unit/integration `research/` packages, and `tests/support/pnc/research/`.

1. Separate tree/node discovery, detail/cost/control reading, and queue/timer parsing. Existing seams include `_discover_label_components`, `_derive_icon_bounds`, `_node_level_readings`, `detail_additions`, `queue_additions`, `_queue_row`, and `_queue_timer_after`. Keep `ResearchContentProducer` and its typed outputs stable.
2. Separate category/tree, detail and queue captured suites; move pure label/level/timer parsing and projection assertions to direct units. Retain real OCR and measured geometry for distinct categories, repeated art, MAX/locked nodes and detail controls.
3. Adopt S0 while retaining `research-acceptance` backend revision and the current distinct capture provenance of the two publishers.

**Acceptance:** category identities, clipped-node decisions, levels/MAX/locks, queue readiness/timers, premium-cost controls and provenance retain ledger coverage. No duplicate catalog values or widened OCR crop is introduced.

**Focused baseline:** the two named Research modules above. After migration use `group unit.app.pnc.vision.research` and `group integration.vision.research`.

## S5 — Campaign

**Owned existing files:** `pnc_automation/app/pnc/vision/campaign.py`; `tests/unit/app/pnc/vision/test_campaign.py`; `tests/integration/vision/test_campaign_visual_profiles.py`. `campaign_ocr_regions.py`, domain, navigation, selectors and catalog assets are read-only inputs.

**Owned new packages:** `vision/campaign/`, matching unit/integration `campaign/` packages, and `tests/support/pnc/campaign/`.

1. Separate map badge/lock/node extraction from chapter/path-node parsing, with only genuinely shared geometry/row construction below them. Existing seams include `_map_rows`, `_chapter_rows`, `_circle_candidates`, `_map_badge_row`, `_map_lock_row`, `_path_node_row`, and `_chapter_identity`. Keep `build_campaign_additions` as the supported entry point.
2. Separate map/chapter identity, owned controls/overlays, bounded real OCR, and frame/provenance suites. Move pure OCR-plan scaling and geometry calculations into units; keep measured controls and native animation/art variants as distinct integration evidence.
3. Adopt S0 only where its existing context semantics match the case. Preserve the controlled/scripted OCR wrappers and `campaign-visual-test` revision; do not silently turn a scripted context into a different integration boundary.

**Acceptance:** map/chapter exclusivity, owned Home/detail close/challenge controls, blocking overlay suppression, clipped/foreign/partial abstention, stage numbers, native Grandia frames and explicit provenance retain coverage. No stage-detail screen is promoted to an unrelated generic popup.

**Focused baseline:** `tests.unit.app.pnc.vision.test_campaign` and `tests.integration.vision.test_campaign_visual_profiles`. After migration use `group unit.app.pnc.vision.campaign` and `group integration.vision.campaign`.

## Worker validation and handback

Use the repository runner for new component groups. `tests/README.md` also permits direct named `unittest` modules for the pre-migration narrow check; use the portable fixture profile and keep all live flags off. Do not use raw discovery. Do not guess that `group` accepts a full module filename: its current matching is directory/component based.

After each meaningful risky slice, run the smallest relevant cases. Run the complete owned groups once on the finished package, including all retained boundary cases. Compare before/after on the same interpreter, dependencies, fixture set and workload; record wall time and measured expensive calls where the wrapper already records them. Do not assert timing thresholds in unit tests.

The coordinator owns the single final integrated `affected --explain` validation and any full fallback/CI run. Package creation/deletion and shared support changes can correctly require full selection; workers do not each launch the whole portable inventory. This is one multi-package candidate with one broad acceptance owner, not five unrelated full-run assignments.

Return `READY_FOR_REVIEW`, `NEEDS_LEAD`, `BLOCKED`, or `FAILED`, with:

- base/candidate SHA, worktree/branch, changed and pending paths;
- implementation summary, supported API exports, and completed test/subtest ledger;
- focused checks with passed/failed/skipped status, durations and exact ignored artifact paths;
- representative affected-selection evidence and remaining real coupling, when available;
- any lost/retained coverage concern, unresolved design decision, and confirmation that owned test processes are finished.

Return `NEEDS_LEAD` if preserving behavior requires a shared observer/selector change, a domain-contract redesign, new live evidence, or a cross-feature extraction. Do not start a competing writer or make an unobserved behavior correction inside a performance assignment.

For Devin execution use the [Devin handoff format](../../../.agents/skills/devin-implement/references/handoff.md) and its pinned local worker workflow. For Luna use the same slice brief with the user-requested xhigh effort. This plan does not require consulting Pro again or spawning additional review agents.

## S6 — one coordinator integration and coverage owner

Integrate terminal feature handbacks on one authoritative candidate. Review the combined diff and ledgers, resolve any shared-resource/source-as-data mappings once, and update shared testing documentation once. Shared ownership rules stay additive and fail closed. Keep the current static declaration floor, policy version compatibility checks, four shards, stable gate and 30-minute limits.

Migrate the existing `tests/integration/vision/test_campaign_chapter_five.py` imports from the removed mixed Campaign test module to S5's canonical support helper. The lead owns this caller update and preserves its assertions; the feature worker returns the final helper path and exported names instead of editing the outside-scope test or retaining a test-module shim.

Inspect the finished migration selection once with `py tools/run_tests.py affected --base <recorded-common-base> --dry-run --explain`; package creation/deletion can correctly select the full inventory. Execute that selection through the exact merge-candidate CI run. Reuse valid focused worker evidence and the complete offline coverage run below instead of duplicating a full local execution. Verify disjoint shard modules/case IDs, artifact provenance and complete job durations on the exact revision before acceptance.

Produce one fresh coverage/context measurement of the accepted integrated tree with the existing `measure --contexts` path, in a separately owned offline measurement scope rather than ordinary CI. Publish ignored line/branch and component evidence plus a policy-compatible seed. Do not have five workers contend over one coverage database. The September 14 percentage is historical, not a current ratchet or a valid before/after comparison.

Map current uncovered branches to the five responsibilities and identify meaningful gaps after moved/consolidated assertions. Add only contract-relevant missing tests; if a gap needs a new feature or behavior decision, return it to the lead. Do not promise that splitting modules eliminates real composition-root consumers or that coverage alone proves import/resource ownership.

Final acceptance: all retained behavior obligations have an owner; no unrelated code or authored fixtures changed; internal ownership is explainable; required downstream/API checks remain; exact candidate CI passes below 30 minutes; and fresh coverage limitations are stated. Commit/push/merge authority and any worker launch are handled by the execution request, not implied merely by preparing this plan.
