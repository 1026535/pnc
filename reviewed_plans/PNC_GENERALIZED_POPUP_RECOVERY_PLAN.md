# Generalized Popup Recovery Implementation Plan

## Context

PNC automation can be interrupted by non-workflow overlays during login, account switching, game startup, and ordinary navigation. Known examples include VIP daily reset, Savannah/Lucifer promotional offers, alliance invitations, disconnect/reconnect prompts, and mandatory game-update prompts. The dismiss control is not consistently located: some overlays use a top-right `X`, some use a footer `Cancel` or `Close`, and some may expose a popup-local back arrow.

The current working tree already contains a partial popup-recovery implementation layered over `origin/main` (`b6c1a0176bd80423ba33015440ebac6b620fe001`). It centralizes interruption recovery in `ObservedActionExecutor`, recognizes VIP/update/offer/cancel variants, limits retries by frame fingerprint, and forbids blind Android Back. This plan treats `origin/main` as the comparison baseline while preserving and refining the existing working-tree changes rather than replacing unrelated work.

Repository evidence shows two important gaps:

- `PncObservationEnricher` emits reconnect `Confirm` as `PNC_POPUP_CLOSE_BUTTON`, so an affirmative action is currently indistinguishable from a generic safe dismissal.
- `_build_top_right_popup_close_additions()` recognizes offer text but synthesizes a broad resolution-relative target instead of proving the actual close glyph.

The implementation must generalize popup recovery without treating every `Confirm`, `Join`, `Apply`, `Claim`, `Buy`, or other primary action as safe.

## Goals

- Recover automatically from recognized nuisance popups before they block a workflow.
- When recognized handling is unavailable, detect a blocking modal and find a safe popup-local `X`, `Cancel`, `Close`, negative action, or strongly proven popup-local back control regardless of its absolute location.
- Keep mandatory update and reconnect confirmation as explicitly typed recovery actions, separate from generic dismissal.
- Re-observe from a fresh screenshot after every attempted dismissal; never try a second coordinate inferred from the same frame.
- Keep task-owned and potentially spending actions outside generic recovery.
- Produce deterministic evidence and bounded live validation suitable for promotion into shared runtime paths.

## Non-Goals

- Naming or classifying every promotional campaign.
- Clicking generic `Confirm`, `OK`, `Join`, `Apply`, `Claim`, `Buy`, `Upgrade`, or price-bearing controls.
- Using Android `KEYCODE_BACK` as a generic popup escape.
- Forcing a popup to appear during validation, switching accounts/castles to seek one, or spending resources merely to create test state.
- Replacing the existing observation, selector, runner, or artifact abstractions.
- Adding a learned object detector when deterministic OCR/geometry/template evidence is sufficient.

## Current State

### Runtime ownership

- `pnc_automation/app/automation/engine/observed_action_executor.py` owns preflight, navigation, and post-action interruption recovery.
- Recovery currently considers `PNC_VIP_DAILY_RESET_CLOSE_BUTTON` and `PNC_POPUP_CLOSE_BUTTON` safe, refuses task-owned popup screens/selectors, uses a bounded distinct-fingerprint budget, and performs a full-runtime observation after each tap.
- `pnc_automation/app/pnc/navigation/screen_flows.py` no longer falls back to Android Back for an untyped popup.
- Mandatory update recovery already uses the dedicated `PNC_UPDATE_CONFIRM_BUTTON` path and avoids blindly replaying an action that may already have been dispatched.

### Perception ownership

- `pnc_automation/app/pnc/vision/pnc_observation_enricher.py` recognizes:
  - VIP daily reset from OCR and its `Close` control;
  - the exact required-update message and its dedicated `Confirm` control;
  - disconnect/reconnect text and `Confirm`, currently misclassified as generic close;
  - footer `Cancel` when paired with a popup primary action;
  - offer content, followed by a synthesized top-right target;
  - a bright upper-right `X` using guarded image geometry.
- `Observation` exposes `blocking_popup` and selector-backed elements but has no typed representation of the modal bounds, candidate control semantics, evidence source, or candidate ranking.
- Because `visible_elements` is keyed by `UiElementId`, it cannot faithfully represent several same-kind candidate controls without prematurely selecting one in vision.

### Existing evidence disposition

| Claim | Evidence | Disposition |
|---|---|---|
| Savannah-style offer has a top-right `X` and blocks the underlying screen | `artifacts/2026-08-31/serious_stuff/20260831T121627Z_popup_recovery_before.png` and related post-action captures | `artifact_answered` |
| Alliance invitation exposes safe `Cancel` beside mutating `Join/Apply` | `tests/data/screen_recognition/alliance_invitation.png` (and matching artifact copy) | `artifact_answered` |
| Required update uses exact update text plus `Confirm` | `artifacts/2026-09-09/serious_stuff/20260909T123533Z_inspect_reconnect_popup.png` | `artifact_answered` (filename is misleading; content is update) |
| VIP reset exposes a popup-local `Close` | Existing OCR fixture/test in `tests/test_capture_and_vision.py` | `artifact_answered` for the current layout |
| Disconnect/reconnect uses affirmative `Confirm` | `tests/data/world_map/world_map_disconnect_popup_live_20260615.png` plus local fixture-backed test | `artifact_answered` where local fixture is configured |
| Arbitrary popup-local back-arrow layouts can be safely identified | No reviewed screenshot currently proves this family | `unknown`; keep disabled until fixture or naturally occurring live evidence exists |

Existing artifacts answer the material current-layout questions needed to design the first implementation slices. No additional live interaction is required during planning. Unknown popup-local back behavior is an explicit promotion gate, not an assumption.

## Target Design

### 1. Model popup evidence separately from authorization

Add a canonical popup domain model, preferably in `pnc_automation/app/pnc/domain/popup.py`, and attach it to `Observation`/`ObservationAdditions`:

- `PopupControlKind`: `CLOSE_X`, `CANCEL`, `CLOSE_TEXT`, `NEGATIVE_ACTION`, `POPUP_BACK`, `UPDATE_CONFIRM`, and `RECONNECT_CONFIRM`.
- `PopupEvidenceKind`: `KNOWN_LAYOUT`, `OCR_TEXT`, `TEMPLATE`, and `GEOMETRY`.
- `PopupDismissCandidate`: control kind, measured bounds, exact action point, confidence, evidence kind, optional normalized/extracted text, and reason.
- `PopupOverlayObservation`: measured modal bounds when available, recognized-layout identifier when available, ordered candidate tuple, and evidence confidence.

Perception remains descriptive: it reports what control was detected and why. It must not decide that a control is allowed merely because its text or location resembles a button.

### 2. Keep one authorization owner

Add a small typed recovery policy beside `ObservedActionExecutionPolicy` in `observed_action_executor.py` (or a focused `popup_recovery_policy.py` if the executor would otherwise become unwieldy). It selects at most one candidate from the current observation.

Priority and authorization order:

1. Exact required-update `Confirm`, handled by the existing dedicated update workflow.
2. Exact recognized nuisance-layout dismiss control (`Close`, `Cancel`, or measured `X`).
3. Generic `Cancel`, `Close`, `Not now`, `Later`, `No`, or equivalent reviewed negative text inside a proven modal.
4. A measured `X` attached to or inside a proven modal boundary.
5. A measured popup-local back arrow only after its evidence gate is satisfied.
6. Abstain and fail with the current screenshot/evidence when no authorized candidate exists.

Reconnect `Confirm` is a distinct typed recovery action, not a generic close. It may be authorized only when the exact disconnect/reconnect message is recognized. Generic affirmative controls are never selected.

Task-owned screens and controls continue to take precedence. At minimum, building upgrade, speedup, march confirmation, mail compose, chat send/profile, alliance member management, coordinate dialog, alliance `Join/Apply`, purchases, rewards, and other workflow-owned actions remain excluded from interruption recovery.

### 3. Recognized-first perception with generic fallback

Refactor `_build_popup_additions()` into an ordered recognizer pipeline:

1. VIP reset.
2. Required update.
3. Disconnect/reconnect.
4. Known offer layouts (Savannah/Lucifer and structurally equivalent offer evidence).
5. Known alliance invitation/footer layouts.
6. Generic modal-bound control discovery.

A recognized layout must still return a measured control from OCR, template, or glyph geometry. Recognition of the popup body alone must not synthesize a click target. Replace `_build_top_right_popup_close_additions()` with actual close-control localization; if the glyph cannot be measured, return blocking-popup evidence with no candidate so the executor fails closed.

Generic fallback must first prove a modal or blocking overlay using multiple cues, such as a coherent panel boundary, dimmed/background discontinuity, popup-local text/action grouping, or full-screen promotional overlay evidence. It then searches relative to the measured modal, not fixed screen coordinates:

- OCR negative labels inside the modal/footer.
- `X` glyph candidates on or near modal corners/edges.
- Popup-local back glyph candidates on the modal header edge only after the dedicated evidence gate.

Reject candidates that lie on the underlying HUD, bottom navigation, resource bar, or outside the modal ownership region. A full-screen promotional overlay may use the screen boundary as its modal ownership region only when the overlay itself is proven.

### 4. Fresh-frame transaction semantics

Treat each dismissal attempt as a one-frame transaction:

- Select exactly one candidate from observation fingerprint `F`.
- Dispatch exactly one tap at the candidate's captured action point.
- Capture a new full-runtime screenshot before any further decision.
- If the new frame has fingerprint `F`, fail as unchanged; do not try another candidate from `F`.
- If a different blocking popup is present, select from only that new observation.
- Retain the existing maximum distinct-popup budget and loading/unknown settle behavior.
- Persist the before frame, selected candidate/evidence, action point, after frame, and result reason in normal runtime artifacts/logging.

Fingerprint deduplication is a safety guard, not proof of freshness by itself. The observation callback must perform a real capture; cached observations cannot satisfy the post-tap recapture contract.

### 5. Compatibility and migration

- Keep `PNC_UPDATE_CONFIRM_BUTTON` for the exact update path.
- Add `PNC_RECONNECT_CONFIRM_BUTTON` and migrate reconnect recognition/tests/callers away from `PNC_POPUP_CLOSE_BUTTON`.
- Retain `PNC_POPUP_CLOSE_BUTTON` temporarily as the compatibility selector for one selected safe negative/X candidate, while the richer popup evidence becomes authoritative for ranking and auditability.
- Add `PNC_POPUP_BACK_BUTTON` only when popup-local back is promoted; do not map it to Android `KEYCODE_BACK`.
- Remove the synthesized offer target once every caller uses measured candidates.
- Keep `blocking_popup` as a derived compatibility field until all callers consume `popup_overlay`; define it from typed overlay evidence rather than independent ad hoc checks.

## Implementation Phases

### Phase 0 — Freeze the evidence corpus and executable safety contract

**Files**

- `tests/data/popup_recovery/` (new curated fixture directory)
- `tests/test_popup_recovery.py`
- `tests/test_capture_and_vision.py`
- `tests/test_visual_screen_recognizer.py`

**Work**

- Curate representative, non-secret screenshots for Savannah-style `X`, alliance `Cancel`/`Join`, VIP `Close`, required-update `Confirm`, and reconnect `Confirm` using existing repository artifacts/fixtures.
- Record expected modal ownership region, allowed control, forbidden controls, and action point tolerances in test cases rather than a second production registry.
- Add negative fixtures/crops for HUD crosses, price/upgrade/claim buttons, alliance `Join/Apply`, task-owned confirms, and crossed artwork.
- Add contract tests proving recognized-first ordering, no generic affirmative action, no Android Back, one candidate per frame, and mandatory recapture.
- Do not copy a local-only artifact into tracked fixtures unless repository policy permits it; when unavailable, keep the test behind `require_local_fixture_artifact()` with a clear skip.

**Acceptance checks**

- Every currently supported popup family has a positive test and at least one adjacent false-positive test.
- Test names state whether the expected action is dismiss, typed recovery, task-owned, or abstain.
- Current implementation is expected to fail the reconnect-selector and synthesized-target contracts, demonstrating that the tests detect the known gaps.

### Phase 1 — Introduce typed popup evidence without changing runtime decisions

**Files**

- `pnc_automation/app/pnc/domain/popup.py` (new)
- `pnc_automation/app/pnc/domain/observation.py`
- `pnc_automation/app/pnc/vision/observation_builder.py`
- `pnc_automation/app/pnc/vision/pnc_observation_enricher.py`
- `tests/test_capture_and_vision.py`
- `tests/test_screen_classifier.py`

**Work**

- Add the popup models and propagate `popup_overlay` through `ObservationAdditions` and `Observation`.
- Preserve existing selector output during this slice so downstream runtime behavior remains unchanged.
- Make overlay ownership clear: when popup evidence wins, background controls are suppressed and only popup-owned actionable controls survive.
- Derive `blocking_popup` from the typed overlay plus legacy screen types during migration.

**Acceptance checks**

- Model validation rejects out-of-image bounds, missing action points, unsupported kinds, and duplicate indistinguishable candidates.
- Existing observation/classifier tests still pass.
- New tests prove multiple descriptive candidates can be represented without vision authorizing one.

### Phase 2 — Correct recognized popup handlers and remove synthetic targets

**Files**

- `pnc_automation/app/pnc/enums/ui_element_id.py`
- `pnc_automation/app/pnc/vision/data/selector_registry.yaml`
- `pnc_automation/app/pnc/vision/pnc_observation_enricher.py`
- `pnc_automation/app/pnc/vision/pnc_ocr_capabilities.py`
- `pnc_automation/app/pnc/vision/screen_classifier.py`
- `tests/test_capture_and_vision.py`
- `tests/test_screen_classifier.py`
- `tests/test_selectors.py`

**Work**

- Emit `PNC_RECONNECT_CONFIRM_BUTTON` and typed `RECONNECT_CONFIRM` evidence for only the exact reconnect message.
- Continue emitting `PNC_UPDATE_CONFIRM_BUTTON` only for the exact required-update message.
- Convert VIP, recognized offer, and alliance invitation handlers to measured candidates.
- Replace synthesized top-right offer coordinates with actual X localization; recognized body plus missing X becomes an undismissed blocking popup.
- Keep known handlers ahead of generic fallback.

**Acceptance checks**

- Reconnect `Confirm` is absent from the generic safe-close selector.
- Update and reconnect near-matches abstain.
- Offer tests assert the action point is centered on detected glyph bounds, not on a fixed percentage region.
- Alliance invitation chooses `Cancel` and never `Join/Apply`.

### Phase 3 — Add generic modal-bound safe control discovery

**Files**

- `pnc_automation/app/pnc/vision/pnc_observation_enricher.py`
- Optionally `pnc_automation/app/pnc/vision/popup_detection.py` if extraction keeps the enricher focused
- `pnc_automation/core/vision/template/` only if reviewed glyph templates are necessary
- `tests/test_capture_and_vision.py`
- `tests/test_visual_screen_recognizer.py`
- `tests/data/popup_recovery/`

**Work**

- Detect modal/full-screen-overlay ownership before discovering generic controls.
- Search relative to modal bounds for reviewed negative OCR labels and measured X glyphs.
- Score candidates using semantic safety, modal containment/attachment, evidence strength, and confidence; emit all descriptive candidates in deterministic order.
- Reject controls on background navigation/HUD regions and all generic affirmative labels.
- Keep popup-local back disabled in production in this phase.

**Acceptance checks**

- Fixtures with shifted/resized X and footer labels resolve to their measured positions.
- The same glyph outside modal ownership is rejected.
- A popup with only `Confirm`, `Join`, `Apply`, `Claim`, `Buy`, `Upgrade`, or a price has no generic dismiss candidate.
- Ambiguous or low-confidence modal/control geometry yields blocking evidence plus abstention.

### Phase 4 — Move candidate authorization into the executor

**Files**

- `pnc_automation/app/automation/engine/observed_action_executor.py`
- Optionally `pnc_automation/app/automation/engine/popup_recovery_policy.py` (new)
- `pnc_automation/app/pnc/navigation/screen_flows.py`
- `pnc_automation/app/automation/daily_maintenance/canary_runtime.py`
- `pnc_automation/app/automation/tasks/popup_recovery_task.py`
- Other popup-selector callers found by `rg` during migration
- `tests/test_popup_recovery.py`
- `tests/test_automation_framework.py`
- `tests/test_daily_canary_runtime.py`

**Work**

- Implement the recognized-first authorization order over typed popup evidence.
- Handle reconnect as a dedicated non-spending recovery case and update as the existing dedicated long-running recovery case.
- Dispatch one observation-bound candidate action, then require a fresh full-runtime observation.
- Fail closed on unchanged fingerprints, missing evidence, task-owned controls, ambiguity, exhausted distinct-popup budget, or recapture failure.
- Preserve no-replay behavior when an update interrupts an already-dispatched workflow action.
- Migrate direct `PNC_POPUP_CLOSE_BUTTON` checks to the canonical policy; keep only explicit compatibility adapters.

**Acceptance checks**

- Recognized controls outrank generic candidates on the same frame.
- A second candidate from the original frame is never attempted.
- Two distinct stacked popups may be dismissed only from two distinct captures/fingerprints.
- No recovery path emits `KeyEventAction(KEYCODE_BACK)`.
- Failures include screenshot path, fingerprint, candidate evidence, and abstention reason.

### Phase 5 — Gate and add popup-local back-arrow support

**Files**

- `tests/data/popup_recovery/` or local fixture manifest
- `pnc_automation/app/pnc/enums/ui_element_id.py`
- `pnc_automation/app/pnc/vision/data/selector_registry.yaml`
- `pnc_automation/app/pnc/vision/popup_detection.py` or the canonical enricher
- `tests/test_capture_and_vision.py`
- `tests/test_popup_recovery.py`

**Entry condition**

- At least one reviewed screenshot of a real blocking popup with a popup-local back arrow and one adjacent negative screenshot of an ordinary navigation back arrow.

**Work**

- Add a reviewed shape/template detector constrained to the proven modal header/edge.
- Emit `PNC_POPUP_BACK_BUTTON`/`POPUP_BACK`; tap its measured screen coordinate as a UI control.
- Never translate this control to Android Back and never infer it from location alone.

**Acceptance checks**

- The real popup-local arrow fixture is detected at its measured bounds.
- Ordinary page-navigation arrows and Android/system navigation areas are rejected.
- If the entry condition remains unmet, record `applicability_skip`; do not enable this candidate kind.

### Phase 6 — Documentation, cleanup, and promotion

**Files**

- `scripts/README.md`
- Relevant example configuration only if a new policy knob is genuinely required
- All legacy popup call sites returned by `rg`

**Work**

- Document recognized-first/generic-fallback behavior, forbidden affirmative actions, bounded recapture semantics, and live smoke usage.
- Remove obsolete duplicated predicates and the synthesized target helper.
- Avoid exposing a broad user-configurable safe-label list unless there is a demonstrated need; safety policy should remain code-reviewed and typed.
- Verify the final diff against `origin/main` and preserve unrelated working-tree changes.

**Acceptance checks**

- One canonical perception pipeline and one canonical authorization policy remain.
- No caller independently guesses popup coordinates or uses Android Back for generic recovery.
- Selector registry, enums, tests, and documentation agree.

## Slice-by-Slice Live Validation Matrix

All live checks use account `testing`, configured BlueStacks instance id `bs-main-1`, display name `testing`, and the castle already active at test start. They must not switch accounts/castles or spend in-game resources. The proposed narrow smoke entry point is:

```powershell
$env:PNC_RUN_LIVE_POPUP_SMOKE='1'
py -m unittest tests.test_live_popup_recovery_smoke
```

The smoke test must use the canonical application/runtime wiring, capture a before observation, and return one of three explicit outcomes: `passed`, `applicability_skip` when no relevant popup naturally exists, or `blocked` with artifacts and reason. It must never manufacture a popup by performing a purchase, upgrade, claim, join, or account switch.

| Slice | Live purpose | Preconditions | Allowed action | Required postcondition | Stop/recovery conditions | Required artifacts | Promotion rule |
|---|---|---|---|---|---|---|---|
| Phase 1: typed evidence | Prove current capture/build path still reports the visible state | `testing` instance resolvable and ADB connected | Screenshot/observation only | Observation completes; if a popup exists, typed evidence and legacy fields agree | Stop on ADB/config/capture failure | Before PNG, observation/OCR sidecars | `passed` or `applicability_skip`; `blocked` prevents runtime promotion |
| Phase 2: recognized handlers | Validate a naturally present known popup's measured control and semantic type | Known popup naturally visible | One non-spending dismiss, reconnect confirm, or required-update confirm only when exact recognized evidence authorizes it | Fresh frame no longer shows the same popup; update may enter bounded update recovery | Stop on ambiguous OCR, wrong semantic type, spending/task-owned control, or unchanged frame | Before/after PNG, OCR, candidate bounds/point, fingerprints | At least one recognized family `passed`; absent families may be fixture-proven plus `applicability_skip` |
| Phase 3: generic discovery | Shadow-evaluate generic modal and control candidates without clicking | Any naturally occurring unrecognized blocking overlay | Screenshot/observation only | Candidate is modal-contained/attached and no forbidden control is marked safe | Stop on uncertain modal ownership or background-HUD overlap | PNG, modal/candidate overlay debug image, OCR JSON, scores | Offline corpus passes and live is `passed` or `applicability_skip`; no click promotion from a single unreviewed detection |
| Phase 4: executor policy | Prove one-tap/one-recapture behavior end to end | Naturally present authorized popup | At most one safe dismissal per captured fingerprint | New capture has a distinct fingerprint and popup is gone or a newly observed popup is independently handled | Stop on same fingerprint, missing candidate, task-owned selector, budget exhaustion, or capture failure | Ordered before/action/after artifacts and policy reason | `passed` required when a suitable popup is available; otherwise repeated `applicability_skip` leaves generic live actuation unpromoted until a natural case is reviewed |
| Phase 5: popup-local back | Validate modal-local arrow without confusing page navigation | Reviewed real popup-local arrow fixture/live occurrence exists | One measured popup-arrow tap only | Fresh frame proves popup transition/dismissal | Stop if arrow ownership is not proven or any system/page back region overlaps | Before/after PNG, detector overlay, fingerprint pair | Must be `passed`; otherwise feature remains disabled with `applicability_skip` |
| Phase 6: regression smoke | Confirm shared workflow no longer stalls when a supported popup appears | Live target healthy; no forced state changes | Canonical popup smoke, then smallest relevant existing workflow smoke | Workflow reaches its existing postcondition with no unauthorized action | Stop on any spending prompt, account mismatch, castle ambiguity, or update timeout | Popup artifacts plus workflow artifacts/log | Required affected slice `passed`; unrelated naturally absent families may remain `applicability_skip` |

## Data, Configuration, and Migration

- No account, castle, credential, or resource-budget configuration changes are required.
- Do not modify `config/accounts.yaml`, `config/castles.yaml`, `config/daily_maintenance.yaml`, or `tests/data/local_fixture_artifacts.json` as part of implementation.
- Add no runtime toggle for “click any confirm.” Exact update/reconnect authorization is code-owned.
- If thresholds need configuration after evidence review, use a typed policy object with validated conservative defaults; do not place raw coordinates in authored YAML.
- Migrate reconnect fixtures and assertions to the dedicated selector in one slice.
- During migration, derive legacy `blocking_popup`/safe-close selector output from typed evidence; remove compatibility only after every `rg`-identified caller has moved.

## Validation

### Focused offline checks after each slice

```powershell
py -m unittest tests.test_popup_recovery
py -m unittest tests.test_capture_and_vision
py -m unittest tests.test_screen_classifier
py -m unittest tests.test_visual_screen_recognizer
```

Add `tests.test_selectors`, `tests.test_automation_framework`, and affected daily/task tests when enums, selector registry, or executor integration changes.

### Selector/navigation validation

```powershell
py tools/validate_navigation_selectors.py --account testing
```

Classify failures by popup relevance. Existing unsupported source screens or unavailable optional UI are not evidence that popup recovery failed, but any changed popup-related selector failure blocks promotion.

### Full regression suite

```powershell
py -m unittest discover -s tests
```

Required for this cross-cutting observation/executor change. Screenshot-backed local fixtures may skip clearly when not configured; newly tracked deterministic fixtures must not skip.

### Live checks

Run the narrow popup smoke first. Run `PNC_RUN_LIVE_SMOKE=1 py -m unittest tests.test_live_account_navigation_smoke` only when popup recovery touches shared account-navigation behavior and its authored script target has been reviewed; do not use it merely to provoke login/account-switch popups. Required live validation that cannot run must be reported with the exact command, blocker, and captured evidence.

## Risks and Mitigations

- **False-positive X on HUD/artwork:** require modal ownership and guarded glyph evidence; retain negative fixtures.
- **Generic affirmative action causes spending/state mutation:** authorize only reviewed negative semantics; keep update/reconnect as exact typed exceptions.
- **Recognized offer but wrong assumed close location:** remove synthesized coordinates; abstain without measured control evidence.
- **Background control leaks through overlay:** suppress underlying actionable elements whenever the topmost modal is proven.
- **Repeated tap on stale UI:** one tap per fingerprint plus mandatory real recapture; fail on unchanged frame.
- **Stacked popups:** allow another dismissal only after a distinct new observation and within the bounded episode budget.
- **Popup-local back confused with navigation back:** require real positive/negative evidence and modal attachment; never emit Android Back.
- **OCR localization/language variation:** combine reviewed OCR with glyph/geometry evidence, normalize only a small reviewed negative vocabulary, and abstain on uncertainty.
- **Dirty working tree overlap:** inspect each target diff against `origin/main`, preserve unrelated edits, and avoid bulk formatting or regeneration.

## Open Questions

- Which real popup family uses a popup-local back arrow, and what adjacent ordinary navigation arrow is the best negative control? This blocks only Phase 5, not X/Cancel/Close recovery.
- Should exact reconnect confirmation remain automatically recoverable everywhere, or only during bootstrap/navigation interruption windows? Default plan: allow it only through the centralized interruption executor, with exact message evidence and no generic selector alias.
- Are Savannah/Lucifer layouts stable enough for a template, or should body recognition plus measured generic X remain the canonical path? Decide from the curated fixture corpus, favoring the smallest robust detector.

## Execution Checklist

- [ ] Rebase the implementation view on `origin/main` while preserving the current working tree and catalog overlapping edits.
- [ ] Curate positive and negative popup evidence without copying secrets or local-only data into tracked fixtures.
- [ ] Add failing safety-contract tests for reconnect typing and synthesized offer coordinates.
- [ ] Introduce typed popup overlay/candidate models and propagate them through observations.
- [ ] Separate update, reconnect, negative dismissal, X, and popup-local back semantics.
- [ ] Convert recognized popup handlers to measured controls and remove synthetic targets.
- [ ] Add generic modal-bound X and reviewed negative-label detection.
- [ ] Centralize candidate authorization and enforce one-tap/one-recapture semantics.
- [ ] Keep popup-local back disabled until its evidence gate passes.
- [ ] Migrate all callers and remove duplicate/ad hoc popup logic.
- [ ] Run focused tests and selector validation.
- [ ] Run the full offline suite.
- [ ] Run bounded live smoke on `testing`/`bs-main-1` with no account/castle switch or resource spending.
- [ ] Record each live slice as `passed`, `applicability_skip`, or `blocked` with artifact paths.
- [ ] Update `scripts/README.md` and report remaining evidence gaps.
