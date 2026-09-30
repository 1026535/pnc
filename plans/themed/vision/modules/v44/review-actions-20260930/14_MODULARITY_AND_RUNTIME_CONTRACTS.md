# A — Reduce feature coupling and settle entry contracts earlier

Goal: a local feature change should have a local implementation/test owner, while actual shared contracts retain their downstream consumers. This addresses architectural causes behind repeated route and test repair. It is not a plan to finish the remaining building list.

## Evidence and scope

Execution priority follows the [coordinator review](../V44_QUALITY_REVIEW_AND_SEQUENCE.md): A3/Q1 first, A1/Q3 after the shared contracts stabilize, A2 deferred until a concrete benefit is demonstrated. A4 consumes the existing reviewed net effect-aware work rather than creating a competing model.

[Root-cause analysis](00_ROOT_CAUSES.md) establishes 292/410 selected tests for camera implementation paths despite the existing `home_city_camera/` package split. At source snapshot a3, `home_city_scan.py` imports the value type `HomeCityCameraTarget` through that package's eager facade, which also imports concrete localization and target publication. The core navigation file owns routing, Home normalization/acquisition, feature transitions and reviewed edge composition; the observation enricher composes many feature producers. Size alone does not justify splitting any of these.

The two observation paths already share `observation_provenance.py` binders and `tests/support/pnc/publication.py`. They still assemble `Observation` content separately in `ObservationBuilder._publish` and `NavigationPerception._build_with_ocr_context`. That is a concrete wiring seam to examine; it does not justify deleting one publisher or making all tests traverse both.

Owners: existing navigation/perception owners; one integration owner for public interfaces. Preserve `NavigationCore`, `WorkflowContext`, public entry points, selector identities and shared input/provenance authority. Use the [existing core-porting contract](../../../../../../instructions/CORE_WORKFLOW_PORTING.md) and existing test-runtime slices, rather than building a replacement core.

## A1 — Contract imports before implementation extraction

1. Trace the reverse-import chains for the 292-module camera cases using the existing selector graph. Identify imports used only for types/constants, package facades that eagerly expose concrete implementation, and test helpers that construct unrelated feature composition. Include package initialization: importing `home_city_camera.models` still executes its eager `__init__.py`; the selector correctly models this in `tools/test_selection/python_graph.py`. Changing the import spelling alone cannot remove that dependency.
2. Pilot relocating the smallest complete shared value-contract cluster containing `HomeCityCameraTarget` from `vision/home_city_camera/models.py` outside the eager implementation package. The existing `domain/home_city_camera.py` owns camera proof; use that domain boundary or a cohesive sibling if mixing catalog geometry with proof would weaken ownership. Audit its dependencies first. Move the canonical definitions, migrate internal contract-only users and implementation imports together, and preserve only required supported facade re-exports of the same objects. Do not duplicate models, introduce dynamic imports to hide consumers, or claim isolation while a parent initializer still imports the implementations.
3. If `ObservationAdditions` and its protocols require unrelated producers to depend on the large `observation_builder.py`, extract those value contracts into one neutral vision-contract module only after mapping callers. Keep dataclass identity and field defaults stable; migrate callers. This is a dependency boundary change, not a behavioral rewrite.
4. Repeat the same path-selection probes. Record remaining actual composition consumers and selected groups. A reduction is expected only if an accidental dependency path was removed. If unchanged, inspect the next real path before doing further file moves.

**Acceptance:** one owner per value type; the neutral contract's import closure does not load camera localization/target implementations; public imports, shared class identity and runtime behavior are preserved; actual reverse-import reach is documented before/after. Add one focused import-boundary check for this regression and retain static downstream tests for declaration/import changes. Do not weaken selector rules to manufacture this result.

## A2 — Extract one cohesive navigation responsibility, if the pilot warrants it

The first candidate is Home acquisition/operation mechanics currently in `app/automation/engine/navigation_core.py`, coordinated with existing `app/pnc/navigation/home_city_scan.py`. Separate feature-independent route execution from feature-owned route descriptions. Keep one actuator, deadline budget, session continuity and source-frame authority; a facade forwarding to the canonical owner is acceptable, a second normalizer/executor is not.

Before editing, write the small interface in terms of existing typed target/slot/request/result contracts and named callbacks. Assign the exact methods/edges and tests. Do not move all feature transitions or create a universal plugin registry. Migrate one owner, remove its old implementation, and let remaining features stay where they are until evidence justifies their migration.

**Acceptance:** the next target/profile addition changes its feature-owned data/route description without editing camera mechanics; wrong/stale bodies, wrong slots and uncertain input still fail at the canonical boundary. Home acquisition's public behavior is unchanged. Shared assembly tests remain, but pure Home logic can be tested through its owner without unrelated content parsing.

## A3 — One publication contract instead of parallel field lists

The first defect to reproduce is the a3 source divergence: `ObservationBuilder` copies `current_pnc_account_id` from additions while `NavigationPerception` omits it. Establish its intended common contract with a deterministic test before fixing it; this is not evidence of a live account-selection failure. Use `tests/integration/vision/test_login_observation.py`, navigation-perception tests and the shared publication helper. Retain publisher-specific identity/control authority.

Compare only shared field/provenance assembly in the two publishers. Reuse existing binders. If a newly added field requires parallel hand edits, extract the smallest typed assembly helper that binds those common fields once. Keep publisher-specific guard, OCR scope, decision filtering and capture responsibilities explicit; do not unify different policies for code-count savings.

Test the helper's provenance/guard invariants at its owner, plus a small real both-publisher contract suite. Each feature's native recognition cases stay at the feature producer unless their purpose is publisher wiring. This addresses omitted publisher coverage without replaying every native case through the entire application twice.

**Acceptance:** a supported feature field is mapped once; both real publishers preserve the same relevant frame/content contract; negative/blocked-frame behavior remains covered. No cached observation or OCR answer crosses a frame boundary.

## A4 — Entry semantics are an input to implementation

Before broad route implementation, use one small typed/catalog-owned contract for known body-entry behavior: target identity, initial menu/panel behavior, actual possible side effect and destination/return owner. Keep user/environment authorization separate from game semantics. A setting permitting non-Main collection cannot make collection `READ_ONLY`; a rejected runtime capability is not a reason to ask again for granted permission.

Reconcile with the current effect-aware entry work before creating competing symbols. The shared entry path must reuse `OpenBuildingPolicy`, workflow effect/capability interfaces, read-only policy and executor, with explicit supported semantics for military/resource/Trap families. No giant permissions framework or per-building bypass. Saved APK facts are build-scoped and current UI may refine them; use the same contract in future assignment readiness and tests.

**Acceptance:** one canonical effect classification consumed by callers; a newly supported collecting type does not require scattered ad hoc allowlists; read-only and protected-Main behavior is retained; a valid non-Main assignment reaches the supported runtime path without duplicate approval. Building-specific action workflows remain separate.

## Verification and migration order

Run A3/Q1 first for its demonstrated divergence, then A1/Q3 as a bounded import-closure pilot. A2 remains deferred until an actual upcoming change demonstrates its ownership/testability benefit. A4 consumes active effect-aware work. For each slice, run its owning unit/contract groups and one finished-candidate affected gate; infrastructure/module-migration full fallback is expected. Reuse the existing architecture ownership tests instead of adding a parallel lint framework.

No fresh live test is required solely for an import/data-contract move with deterministic behavior parity. If routing, current-frame lifetime, effects or dispatch behavior changes, require one final-candidate case through the affected production boundary on the assigned non-Main target, with actual receipt, endpoint and return. Stop dependent input on unknown identity/control/result. Reuse unaffected routes and proof; do not tour all buildings to validate a module split.

Deliver source/consumer map, exact interface/caller migration, focused and final test evidence, unchanged live-proof rationale or required changed-boundary live evidence, and before/after selection results. Defer further extraction if it only changes filenames.
