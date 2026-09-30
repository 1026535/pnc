# 02 — Qualify Bank and Watchtower from safe body through return

> Supporting V44 case study from the first planning pass. The [velocity roadmap](README.md) and [cause assessment](00_ROOT_CAUSES.md) supersede its priority and current-status assumptions. Reconcile historical candidate, ownership and policy notes before execution; this document is not a live assignment.

Priority: next V44 route package. Owners: V acquisition/capture owner, V40 Bank and V35 Watchtower feature owners, V acceptance lead. Live prerequisite: [01](01_CANDIDATE_GATE.md). Review coverage: §2 Bank acquisition, Bank/Watchtower chains and new capture gap; §3; §5 safe evidence package.

## Evidence and source scope

[E3–E5](README.md#evidence-index) establish Bank as fixed `sys_1/5001`, without an ordinary slot; its older positive body points lie outside the unchanged safe input band. Watchtower is ordinary slot4. Recovered Bank entry is direct below an auction-level condition and menu-mediated above it; Watchtower opens a body menu. These are build-scoped semantics, not current menu coordinates or accepted routes.

Canonical code: `app/automation/engine/navigation_core.py` (`locate_building`, `open_building`, `reviewed_navigation_edges`), `app/pnc/navigation/home_city_scan.py`, `app/pnc/vision/home_city_camera/{catalog,targets,localization}.py`, `app/pnc/domain/building_catalog.py`, and the existing selector/recognizer publishers under `app/pnc/vision/`. All production paths are relative to `pnc_automation/`. Screen controls belong to the selector catalog and existing perception owners; callers use `WorkflowContext`/`CoreWorkflowRunner`.

The frozen historical helper is under primary `.local-data/worktrees/v44-publish-core-20260928/.local-data/v44-live030-reviewed/`. It is reference evidence only: its Bank case is locate-only and its manual recovery does not authorize task-owned menu interaction. A newer **unreleased** preparation already exists at sibling `v44-next-bank-ordinary-preparation/` ([E8](README.md#evidence-index)): Bank locate, Watchtower locate, one ordinary passive survey and only necessary typed Campaign setup. Reuse/review that draft rather than creating a competing helper. It still needs focused fake/lifecycle checks, corrected candidate binding and final release; leave frozen evidence unchanged.

## A. Acquire the current safe body

1. Reconcile the prepared Sol capture package before creating competing work. Preserve the reviewed loading settle implementation and existing deadline/camera policy.
2. In one released batch, call production `locate_building(BANK)` once from current clear Home. Record every pan's native before/after frame and final same-frame TEMPLATE body. Bank must retain fixed-node identity with no fabricated ordinary slot, and its action geometry must fit the existing safe band and exclude the floating status badge.
3. Qualify Watchtower's actual current slot4 body using the accepted matcher. Old source/holdout matches remain supporting evidence; they do not authorize a fresh tap.

**Pass:** fresh localized bodies with valid provenance and admissible geometry. **Stop:** no qualified body within canonical bounds, unknown screen or uncertain input. No Bank/Watchtower entry occurs in this locate-only phase unless separately selected and released below.

## B. Close the task-owned menu capture gap

1. Add only the narrow discovery cases needed by this cohort to the owned live helper: selected target/body, originating frame, current screen, measured geometry, allowed next action and cumulative budget. Use the existing runtime and observed executor/receipts. Do not expose an arbitrary coordinate/selector tap to production workflows or widen generic popup dismissal.
2. Release a discovery body tap only after the current safe body is positively identified and the helper uses a truthful effect/capability path. Capture the resulting direct panel, locked state, or on-city menu before further input. A task-owned menu must not be auto-dismissed as an unrelated popup. The later non-Main collection policy does not supply missing menu identity or waive current-frame action checks.
3. If a reviewed selector for the next control is absent, **stop that dependent chain at the native menu capture**. Curate its identity/control evidence offline and add a typed, current-frame selector through the existing publisher. A bounded new capture stage may then use that reviewed selector. Do not derive a point from Lua `Btn1`, image proportions, an old frame or popup-recovery authority.
4. Capture Bank/Watchtower destination identity and measured return in the same way. Bank Auction, deposit and claim controls are outside the navigation package. Where a return control cannot yet be qualified, retain the screen and report it; do not guess Android Back.

This can need more than one discovery checkpoint when the first frame supplies the next selector. Batching compatible passive work reduces launches but does not eliminate that dependency. Prefer capture-only progress over making an unreviewed control executable.

## C. Implement one coherent production route package

- Curate native fixtures into `tests/data/home_city_slot_bodies/` and/or `tests/data/screen_recognition/`, with provenance in their existing manifests. Store generated originals/reports under ignored `.local-data/`.
- Add the observed menu control and destination/return recognition through the existing selector catalog, visual recognizer, `ObservationBuilder` and `NavigationPerception`. Use current evidence to choose a direct or menu edge; do not add an unobserved universal direct/menu compatibility system.
- Connect the route in `NavigationCore` using its existing body acquisition and reviewed edges. Keep `_require_reviewed_building_route` admission meaningful. Do not bypass it with the discovery helper to claim public acceptance.
- Preserve no-slot Bank semantics, exact slot4 Watchtower selection and current-frame action lifetime after every camera/input transition. Menu/action feature ownership stays with V40/V35.

## D. Validation and completion

Focused checks: camera body tests, `tests/unit/app/pnc/navigation/test_navigation_core_buildings.py`, `test_configurable_route_prerequisites.py`, `tests/integration/vision/test_building_route_captured_observers.py`, and both-publisher tests where wiring changes. Cover observed direct/menu shape, wrong or ambiguous control, stale frame, missing return refusal, and safe-body bounds. Use the appropriate `tools/run_tests.py group` owners, then the shared final affected gate once.

Final live cases, on the exact reviewed candidate:

| Case | Production boundary / precondition | Observable pass |
|---|---|---|
| B-ACQ | `locate_building(BANK)`; clear Home, corrected normalization | Fresh fixed-node Bank body safely actionable; locate-only proof |
| B-ROUTE | Actual public `open_building(BANK)`; qualified route and non-spending authority | Fresh body → any observed Bank menu → typed Treasure Cave endpoint → canonical verified Home return |
| W-ROUTE | Actual public `open_building(WATCHTOWER)`; observed slot4 | Fresh body → qualified Watchtower menu → intended typed panel → canonical verified Home return |

The release defines one attempt per selected entry plus exact cumulative pan/detent/return budgets. Keep native source, physical receipt, intermediate menu, endpoint and returned Home evidence. Stop dependent input on ambiguity or unknown return; do not repeat a confirmed body/menu action to improve evidence. Discovery-only passes never mark B-ROUTE/W-ROUTE accepted. Reuse unchanged accepted routes; no Campaign/Market/Alliance Hall tour is required solely because this package is new.
