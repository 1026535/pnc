# PNC Selector Resolution Sub-Plan

## 1. Purpose

This document defines the canonical runtime design for selector interaction resolution when a selector has a fast primary interaction strategy first, but should explicitly fall back to the existing OCR workflow if that primary interaction does not satisfy the reviewed command outcome.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SELECTOR_REFINEMENT_SUBPLAN.md), which owns selector discovery and registry maturity,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable navigation flows,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which owns bootstrap and castle targeting,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns bounded feature-task behavior.

This file owns only the missing selector-resolution behavior:

- fast-primary selector interactions, with geometry-backed taps as the phase-1 slice,
- explicit OCR promotion after a verified settled primary miss,
- one canonical runtime path shared by automation and selector validation,
- provenance and diagnostics required to make that behavior reliable and reviewable.

## 1.1 Implementation status

Status:

- completed in repo on 2026-03-12,
- runtime observation is now staged through typed observation requests instead of unconditional OCR,
- selector provenance is now recorded as canonical runtime data,
- reviewed navigation outcome matching and settled-primary-miss evaluation are now centralized,
- automation and live validation now share one observed selector-interaction path with bounded settle and one OCR retry for eligible geometry-backed navigation taps,
- popup states remain handled through the existing shared popup recovery flow rather than through selector-level double taps,
- automated validation now covers staged observation cost, provenance, selector fallback behavior, validator reporting, and negative retry cases.

## 2. Why this is needed

The current repository already has the required building blocks, but they are not yet connected into one explicit selector-resolution policy.

Current facts:

- the selector registry is canonical and stores the selector id, screen scope, interaction metadata, reviewed click outcomes, and optional `relative_bounds`,
- the current observation pipeline runs OCR on every screenshot through `PncObservationEnricher`, which is correct functionally but more expensive than most action follow-ups need,
- some selectors already have OCR-derived visible-element synthesis for the same `UiElementId`,
- geometry materialization already fills in stable click regions for selectors that were not otherwise detected,
- the low-level action executor only taps the current visible target and does not know whether that target came from geometry or OCR,
- the automation runner only retries whole task increments,
- the navigation validator only settles and evaluates final outcomes.

That means the system can incidentally benefit from OCR on a later observation, but it does not have explicit code that says:

1. this command used a fast primary interaction strategy,
2. that primary attempt did not satisfy the reviewed outcome,
3. OCR guard facts show whether the result is a popup, loading, transition, or settled miss,
4. the selector is now available from an OCR-backed target,
5. retry the same selector once through OCR before escalating to normal task failure.

That missing explicit step is the gap this document closes.

## 3. Current architecture relevant to this change

### 3.1 Selector registry

The current runtime model is centered on one `SelectorDefinition` in [selectors.py](/c:/Users/lebel/pnc/pnc_automation/vision/selectors.py).

One selector may currently carry:

- `detection_kind`,
- `interaction_kind`,
- `click_outcomes`,
- `relative_bounds`,
- `materialize_relative_bounds`,
- optional OCR-region metadata in the runtime defaults.

This is already the correct ownership boundary. This sub-plan must not introduce a second selector-definition system.

### 3.2 Observation pipeline

The current observation path in [observation_builder.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_builder.py) is:

1. detect probe selectors,
2. classify an initial screen,
3. run full OCR enrichment unconditionally,
4. reclassify with additional evidence,
5. detect selectors scoped to the resolved screen,
6. materialize geometry-backed selectors that are still missing.

Important consequence:

- OCR already exists as a canonical observation workflow,
- the current runtime pays that OCR cost on every observation, even when the current action only needs cheap selector or geometry state,
- geometry is already treated as a fallback source of visibility for missing selectors,
- but the observation model currently drops the provenance of the resulting visible element.

Target consequence for this sub-plan:

- keep one canonical observation pipeline,
- split that pipeline into a cheap base pass plus on-demand OCR enrichments,
- only pay for OCR when the current screen state or current action actually requires OCR-backed facts.

### 3.3 OCR-backed selector synthesis already exists

The OCR enrichment layer in [pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py) already synthesizes selector-backed visible elements for several real UI controls, including:

- bottom navigation labels such as `PNC_BOTTOM_NAV_MORE`,
- the More overlay action `PNC_MORE_SETTINGS`,
- Settings-menu items such as `PNC_MORE_MANAGE_CHAR`,
- popup close controls,
- loading reconnect controls,
- some screen-local buttons and headers.

This is important because the OCR fallback we want should reuse these existing emitted selectors. It must not invent a parallel click-target table.

### 3.4 Current failure behavior

The low-level action path in [action_executor.py](/c:/Users/lebel/pnc/pnc_automation/automation/action_executor.py) does this for `TapAction`:

- resolve the visible element from the current observation,
- use `action_point` if present, otherwise `bounds.center()`,
- tap once.

It does not know:

- whether that visible element came from geometry or OCR,
- whether the selector has a reviewed navigation contract,
- whether the click likely missed,
- whether a second attempt should deliberately switch to an OCR-derived target.

The runner in [runner.py](/c:/Users/lebel/pnc/pnc_automation/automation/runner.py) then retries the entire task increment only after verification fails. That is too coarse to be the selector-resolution policy.

## 4. Problem statement

The desired policy is:

- use the fastest reviewed primary strategy first when one exists,
- use OCR guard facts to classify whether a post-action failure is really a popup, loading state, transition, or settled miss,
- if the primary command still resolves to a settled miss, explicitly promote the same selector to the OCR workflow when OCR can provide a better target,
- do that once, centrally, with deterministic logging and artifacts.

The current implementation does not provide that behavior. It only provides:

- geometry-backed visibility,
- OCR-backed visibility,
- task-level retries after later verification.

That gap causes three concrete architectural problems.

### 4.1 No canonical selector-level retry

The runner can retry a whole task, but that is not the same thing as a selector-resolution retry. A task retry:

- re-runs planning,
- may include unrelated actions,
- hides which selector source actually failed,
- cannot cleanly report that geometry missed and OCR recovered the click.

### 4.2 No provenance

The observation model does not currently record whether `VisibleElement(PNC_BOTTOM_NAV_MORE)` came from:

- template detection,
- OCR,
- or geometry materialization.

Without that, the runtime cannot make a clean decision about when OCR fallback is justified.

### 4.3 Automation and validation would diverge if this is patched locally

If OCR fallback were added only to:

- one task,
- one screen flow,
- or only the live validator,

the system would immediately violate the single-canonical-implementation rule.

The fallback behavior must therefore live in one shared runtime interaction path.

## 5. Vision

The target design is one canonical staged observation plus selector interaction loop:

1. Capture a cheap base observation for the current action.
2. Run OCR only for the guard states or screen facts that are relevant to that action.
3. Resolve one selector from the resulting observation.
4. If the resolved source is already OCR-backed or template-backed, use it directly.
5. If the resolved source is primary-backed and the selector has a reviewed safe navigation contract, perform one primary interaction attempt.
6. Capture a follow-up observation using only the guard and destination facts needed for that command, including popup or loading classification when that classification requires OCR.
7. If the follow-up observation proves success, stop.
8. If the follow-up observation proves a popup, stop and let the shared popup path handle it.
9. If the follow-up observation is transitional, enter one bounded shared settle loop that re-observes until the result becomes success, popup, settled miss, or settle-budget exhaustion.
10. If the settled result is still a settled miss on the same source screen, issue one OCR-targeted retry observation for that selector and retry the tap once from the OCR-derived target.
11. Capture a second follow-up observation and evaluate the same reviewed contract.
12. If it still fails, return control to the existing task or validator failure path.

This keeps the behavior:

- explicit,
- deterministic,
- primary-strategy-first,
- OCR-assisted,
- shared by both automation and validation.

## 6. Goals

- Fast reviewed workflows stay primary. Geometry-backed selector taps are the first implemented slice.
- OCR fallback becomes an explicit selector-resolution step, not an accidental side effect of later retries.
- OCR can also be requested as a guard classifier so the runtime can recognize popup-caused or transition-caused primary failures before retrying.
- One shared implementation serves both `AutomationRunner` and `NavigationSelectorValidator`.
- OCR cost is paid only when the current action or current screen state actually requires OCR-backed facts.
- The runtime records whether a selector came from geometry, OCR, or template detection.
- The reviewed selector contract remains the single success criterion for navigation selectors.
- The implementation stays lean and does not require a second selector catalog or hardcoded selector capability list.

## 7. Non-goals

- Do not resurrect the old multi-step selector-resolution engine described in older review notes. The current codebase no longer has that architecture.
- Do not add task-local OCR heuristics.
- Do not add a second registry file or a second selector-definition format.
- Do not auto-retry monetized or unsafe selectors.
- Do not add generic fallback for `InputTextAction` or arbitrary same-screen action buttons in the first slice.
- Do not let OCR fallback double-tap during loading transitions, popup transitions, or other unsettled states.
- Do not make OCR scheduling task-local by raw task id or by assuming one exact expected screen.

## 8. Architectural requirements

- Single canonical implementation per concept.
- No duplicated click-outcome matching logic.
- No duplicated geometry-versus-OCR capability tables.
- Observation-cost control must be driven by one typed observation request or scope model, not by ad hoc caller heuristics.
- Fail fast when selector provenance is missing or inconsistent.
- Fail fast when a fallback-eligible selector has no reviewed safe outcome contract.
- Minimal boilerplate: phase 1 should not require selector-catalog schema churn unless the current generic policy proves insufficient.

## 9. Canonical design

### 9.1 Selector provenance must become first-class runtime data

The system needs a typed source marker on observed selectors.

Recommended model:

- add `VisibleElementSourceKind` to [observation.py](/c:/Users/lebel/pnc/pnc_automation/pnc/observation.py),
- add the same source marker to `SelectorMatch` in [image_models.py](/c:/Users/lebel/pnc/pnc_automation/vision/image_models.py),
- add `source_kind` to `VisibleElement`.

Lean source-kind set for the current codebase:

- `TEMPLATE`
- `OCR`
- `GEOMETRY`

Why this is enough:

- template and geometry need to stay distinguishable,
- OCR-region detection and OCR-synthesized visible elements can both collapse to `OCR` for the current fallback policy,
- the current requirement is to decide whether the original tap used geometry and whether the retry target is OCR-backed.

Population rules:

- template or collection selector-engine matches emit `TEMPLATE`,
- OCR-region selector-engine matches emit `OCR`,
- OCR-enricher-created visible elements emit `OCR`,
- `RelativeBounds.materialize(...)` emits `GEOMETRY`.

This is the minimum provenance required to support explicit fallback cleanly.

### 9.2 Navigation outcome matching must move to one shared helper

The current reviewed navigation matching logic lives only in [navigation_selector_validator.py](/c:/Users/lebel/pnc/pnc_automation/vision/navigation_selector_validator.py).

That is the wrong ownership boundary once the runtime itself needs the same logic to decide whether a geometry click actually failed.

Required refactor:

- move reviewed navigation outcome matching into a shared module, for example `pnc_automation/vision/selector_interactions.py`,
- keep `NavigationSelectorValidator` as a consumer of that helper,
- make the automation-side OCR fallback decision consume that same helper.

Recommended shared functions:

- `safe_navigation_outcomes(selector: SelectorDefinition) -> tuple[ClickOutcome, ...]`
- `match_reviewed_navigation_outcome(observation: Observation, reviewed_outcomes: Sequence[ClickOutcome]) -> tuple[ClickOutcome | None, tuple[UiElementId, ...]]`
- `is_settled_primary_navigation_miss(selector: SelectorDefinition, before: Observation, after: Observation, source_element: VisibleElement) -> bool`

This keeps one canonical definition of selector success.

### 9.3 Observation must become staged and policy-driven

The runtime should not keep running full OCR enrichment unconditionally after every screenshot once this work lands.

Recommended model:

- add one small typed `ObservationRequest` or `ObservationScope` model owned by the vision layer,
- let callers describe the current screen family and fact families of interest,
- keep one canonical `ObservationService` and `ObservationBuilder`,
- never let tasks or flows call OCR parsers directly.

The request model should be capability-driven, not task-name-driven.

Recommended contents:

- candidate source or destination screens,
- required fact families, split into universal guard facts versus workflow-owned facts,
- universal guard facts such as popup guard, loading guard, or transition classification,
- workflow-owned facts such as account bootstrap, login or account-switch parsing, castle roster, or selector OCR retry,
- whether unknown-screen escalation is allowed.

Important ownership rule:

- the generic first post-action guard step may request only universal guard facts,
- login or account-switch OCR belongs to the account bootstrap workflow, not to generic popup handling,
- castle-roster OCR belongs to castle-selection workflows, not to generic popup handling.

Base observation should always do the cheap work:

- probe selector detection,
- initial screen classification,
- screen-scoped selector detection after classification,
- geometry materialization.

OCR should run only when the request requires it, for example:

- popup or loading guard facts are needed,
- the current workflow explicitly needs OCR-only screen facts such as login/account identity or castle-roster parsing,
- the base pass left the screen `UNKNOWN`,
- a primary interaction attempt needs OCR to determine whether the result is a popup or other guarded failure mode,
- a geometry-backed selector tap produced a settled same-screen miss and OCR retry is now justified.

This keeps one canonical observation system while ensuring most action follow-ups do not pay for full OCR by default.

### 9.4 OCR fallback must live in a shared observed-action layer

The current `ActionExecutor` is a low-level hardware executor. That is still the correct responsibility.

Do not push selector-fallback policy into that low-level class.

Instead, add one shared higher-level executor, for example:

- `ObservedActionExecutor`, or
- `SelectorInteractionExecutor`

Recommended placement:

- automation layer, because it coordinates taps plus follow-up observations,
- but it must consume the shared selector-interaction helpers from `vision`.

Recommended responsibilities:

- execute the existing `ActionRequest` sequence,
- delegate raw taps, key events, swipes, and text entry to the low-level `ActionExecutor`,
- request only the observation scope needed for the current selector interaction,
- intercept selector-backed taps that are eligible for explicit OCR fallback,
- reuse one observation callback to capture post-action states,
- return the final observation exactly once to the caller.

This preserves one low-level action abstraction and one high-level observed selector interaction abstraction.

### 9.5 Initial fallback scope must be intentionally narrow

Phase 1 fallback scope should be intentionally narrow even though the ownership model is broader.

Phase 1 scope should be:

- `TapAction`,
- `observe_after=True`,
- selector exists in the registry,
- selector `interaction_kind == navigation`,
- selector has at least one `safe_to_click` reviewed outcome,
- initial visible element `source_kind == GEOMETRY`.

Why this narrow scope is correct:

- navigation selectors already have a typed success contract,
- the system can detect a miss without guessing,
- action selectors often expect same-screen state changes and do not yet have a uniform reviewed contract,
- geometry-backed selector taps are the current implemented primary path,
- this avoids unsafe or heuristic double taps.

Future extension is allowed, but only after a shared success contract exists for non-navigation selectors or for additional fast primary workflows such as event, world-map, or city-map interaction layers.

### 9.6 Canonical fallback algorithm

The fallback algorithm must be primary-strategy-first and conservative. In phase 1, that primary strategy is a geometry-backed selector tap.

Recommended flow for one eligible `TapAction`:

1. Resolve `selector = selector_registry.require(action.selector_id)`.
2. Resolve `source_element = before.require(action.selector_id)`.
3. Confirm `source_element.source_kind == GEOMETRY`.
4. Execute the original tap through the low-level executor.
5. Capture `first_after` using a narrow observation request that includes only the universal guard facts and destination facts relevant to that tap.
6. Evaluate the reviewed safe outcomes with the shared matcher.
7. If a reviewed outcome matched, stop.
8. If `first_after` shows a blocking popup, stop and let the shared popup path handle it.
9. If `first_after` is transitional, enter one bounded settle loop that performs passive follow-up observations using the same narrow guard scope until one of the following happens: reviewed success, blocking popup, settled same-screen miss, or settle-budget exhaustion.
10. If the settle loop ended in reviewed success, stop.
11. If the settle loop ended in a blocking popup, stop and let the shared popup path handle it.
12. If the settle loop exhausted its budget while still transitional or unknown, stop and return control to the normal task or validator failure path without any OCR retry.
13. If the settled result is still a settled miss on the same source screen, issue one second observation request that enables source-screen OCR for that selector.
14. Require that the replacement visible element exists and has `source_kind == OCR`.
15. Execute one second tap using that OCR-derived target.
16. Capture `second_after` using the same narrow follow-up observation request used in step 5.
17. Evaluate the same reviewed safe outcomes again.
18. Return `second_after` to the caller regardless of success or failure.

The implementation must cap this at one OCR retry. No unbounded retry loops.

The settle loop is bounded and observational only:

- it may re-observe and classify,
- it may hand off to popup recovery when a blocking popup becomes visible,
- it must not perform additional taps for the original command during transition settling,
- it must stop before OCR retry if the UI never reaches a stable result within the configured settle budget.

### 9.7 What counts as a primary miss in phase 1

A geometry-backed primary click should be considered eligible for OCR promotion only when all of the following are true:

- the selector is navigation-scoped and safe to click,
- the original tap source was `GEOMETRY`,
- the first post-tap observation does not match any reviewed safe outcome,
- the first post-tap observation is still on the same settled source screen,
- the first post-tap observation is not a known transient state,
- the first post-tap observation does not contain a blocking popup that should be handled by the existing popup path first.

Recommended transient exclusions:

- `ScreenType.UNKNOWN`
- `ScreenType.PNC_LOADING`
- any observation with `blocking_popup=True`
- `ScreenType.PNC_POPUP`

Rationale:

- a loading or popup state is evidence that the tap may already have worked,
- double tapping during those states is more dangerous than helpful,
- the shared settle and popup-recovery mechanisms should remain authoritative for those transitions,
- OCR is still useful there, but as a guard classifier, not as justification for an immediate second tap.

### 9.8 OCR retry target selection

The OCR retry target must come from the current post-miss observation, not from the stale pre-tap observation.

Rules:

- use the same `UiElementId`,
- require `source_kind == OCR`,
- use `action_point` if present,
- otherwise use `bounds.center()`,
- do not invent a new coordinate from the selector registry at this stage.

This rule is important because the OCR workflow already knows how to compute better tap points for some controls, for example:

- bottom-navigation labels,
- More overlay actions,
- popup dismissal controls.

If a selector should benefit from OCR retry but no OCR parser currently emits that selector, the fix belongs in the OCR parser for that same `UiElementId`, not in a fallback-specific side table.

### 9.9 No selector-catalog schema change in phase 1

The current registry already contains enough information to support the first implementation slice:

- selector identity,
- interaction kind,
- reviewed click outcomes,
- relative geometry,
- screen scope.

The fallback policy can therefore be generic for phase 1:

- geometry-backed source,
- safe reviewed navigation selector,
- settled same-screen miss,
- OCR-backed retry target exists.

Do not add a new catalog field yet.

Add schema only later if live evidence proves the generic policy is too broad or too narrow for a subset of selectors, or when a future non-geometry primary workflow needs typed configuration that cannot be inferred from the existing reviewed interaction contract.

### 9.10 Shared implementation must cover both automation and validation

The live selector validator must use the same fallback path as automation.

Required direction:

- `AutomationRunner` uses the new shared observed-action executor,
- `NavigationSelectorValidator` also uses that same executor or the same shared selector-tap helper,
- both consume the same reviewed-outcome matcher.

This is mandatory. If validation and automation tap selectors differently, the validator stops being authoritative.

### 9.11 Diagnostics must make fallback visible

Every fallback attempt must be explicit in logs and, where relevant, in validation results.

Required log fields:

- `selector_id`
- `source_screen`
- `initial_source_kind`
- `fallback_attempted`
- `fallback_source_kind`
- `first_after_screen`
- `final_after_screen`

Recommended validator-report additions:

- `initial_destination_artifact_path`
- `final_destination_artifact_path`
- `initial_source_kind`
- `fallback_used`
- `fallback_source_kind`

This keeps artifact review honest and avoids mixing the first miss with the final successful retry.

## 10. Concrete integration points

### 10.1 Typed observation request model

Add one small typed observation-request model owned by the vision layer, for example in:

- `pnc_automation/vision/observation_request.py`, or
- next to `ObservationBuilder` if a separate module would be overkill.

Responsibilities:

- describe the current candidate screens and fact families of interest,
- let callers request universal guard facts without enabling unrelated OCR,
- let callers ask OCR to classify whether a failed primary attempt is actually blocked by a popup or transition,
- keep workflow-specific OCR families opt-in so login, account-switch, and castle parsing remain owned by their proper workflows,
- let the selector-fallback path request source-screen OCR only when a geometry miss is actually suspected.

### 10.2 `pnc_automation/pnc/observation.py`

Add:

- `VisibleElementSourceKind`
- `VisibleElement.source_kind`

Update helper constructors and test helpers to require or default that field explicitly.

### 10.3 `pnc_automation/vision/image_models.py`

Add:

- `SelectorMatch.source_kind`

This prevents provenance from being lost before matches are converted into visible elements.

### 10.4 `pnc_automation/vision/observation_builder.py`

Update:

- the builder contract so callers can pass the typed observation request,
- the build flow so the cheap base pass always runs first,
- OCR escalation so it runs only when the request requires it,
- template and OCR-region matches to emit `SelectorMatch.source_kind`,
- `_matches_to_visible_elements(...)` to carry that source into `VisibleElement`,
- geometry materialization to emit `VisibleElement(source_kind=GEOMETRY)`.

### 10.5 `pnc_automation/vision/pnc_observation_enricher.py`

Update:

- all `_make_visible*` helpers to emit `source_kind=OCR`,
- the enricher entry point so it does not immediately run full-image OCR unconditionally,
- screen and fact-family OCR passes so they can be invoked from the typed observation request.

This must happen centrally inside helper functions so the provenance does not get duplicated across each parser.

### 10.6 New shared selector-interaction helper module

Create a new module, for example:

- [selector_interactions.py](/c:/Users/lebel/pnc/pnc_automation/vision/selector_interactions.py)

Move or add:

- shared reviewed-navigation matching,
- safe outcome filtering,
- settled primary-miss evaluation, implemented initially for geometry-backed sources.

This module becomes the canonical owner of selector interaction success rules.

### 10.7 New observed-action executor

Create a shared high-level executor, for example:

- [observed_action_executor.py](/c:/Users/lebel/pnc/pnc_automation/automation/observed_action_executor.py)

Responsibilities:

- mirror the existing `execute_actions(...)` contract,
- delegate low-level mechanics to `ActionExecutor`,
- request only the narrow observation scopes needed for initial follow-up and OCR retry,
- intercept eligible geometry-backed `TapAction`s,
- request OCR guard classification when popup or transition diagnosis is needed after the primary attempt,
- perform one OCR retry when the shared primary-miss predicate says it is justified.

### 10.8 `pnc_automation/automation/runner.py`

Wire the runner to use the shared observed-action executor instead of directly using only the low-level executor for observed selector taps.

Important rule:

- the runner keeps owning task retry and replan policy,
- the new executor owns selector-level primary-to-OCR promotion for the geometry-backed phase-1 slice,
- those two retry layers must not be merged.

### 10.9 `pnc_automation/vision/navigation_selector_validator.py`

Refactor the validator to use the same observed selector-tap execution path.

Also update result reporting so the first miss and the final evaluated capture are not conflated.

## 11. Expected phase-1 beneficiaries

The first practical targets should be selectors whose current OCR workflow already emits a better target for the same registry id.

High-value current examples:

- `PNC_BOTTOM_NAV_MORE`
- `PNC_MORE_SETTINGS`
- any future More-overlay or popup selector where OCR provides a raised or corrected `action_point`

Important scope note:

- `PNC_LOGIN_USERNAME_FIELD`, `PNC_LOGIN_PASSWORD_FIELD`, `PNC_LOGIN_SUBMIT_BUTTON`, `PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON`, and `PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON` are currently geometry-backed after OCR screen classification, but they are not yet emitted as OCR-backed visible selectors themselves.
- They should therefore stay out of the explicit fallback path in phase 1.
- If live evidence later shows geometry misses there, the correct fix is to extend the OCR parser to emit those same selector ids, not to special-case them in the executor.

## 12. Detailed implementation phases

### Phase A: Introduce staged observation requests

Implementation:

- add one typed observation-request or observation-scope model,
- split observation into a cheap base pass plus request-driven OCR enrichments,
- keep popup and loading guards as reusable universal fact families rather than task-local code,
- keep login, account-switch, and castle-roster OCR as workflow-specific fact families rather than generic post-action guards,
- make sure selector-tap follow-ups can request only the facts they need.

Exit condition:

- the runtime no longer has to run full OCR on every observation by default.

### Phase B: Add selector provenance

Implementation:

- add `VisibleElementSourceKind`,
- add `source_kind` to `VisibleElement` and `SelectorMatch`,
- populate provenance in template matching, OCR-region matching, OCR syntheses, and geometry materialization,
- update all supporting test helpers.

Exit condition:

- every selector-backed visible element tells the runtime whether it is `TEMPLATE`, `OCR`, or `GEOMETRY`.

### Phase C: Centralize reviewed selector outcome matching

Implementation:

- move reviewed navigation outcome matching into one shared helper module,
- add one shared settled primary-miss predicate,
- update the validator to consume the shared helper instead of its private copy.

Exit condition:

- there is one canonical reviewed-outcome matcher and one canonical primary-miss predicate.

### Phase D: Implement shared primary-to-OCR promotion for geometry-backed selectors

Implementation:

- add the shared observed-action executor,
- make it request a narrow post-tap observation first, including popup-classification OCR only when needed,
- make it own one bounded settle loop for transitional post-tap states before any OCR retry decision,
- make it request source-screen OCR only on a settled miss,
- wire one OCR retry for eligible geometry-backed `TapAction`s,
- ensure the OCR retry only runs after a settled same-screen miss,
- preserve existing low-level pacing and observation timing.

Exit condition:

- one geometry-backed navigation tap can explicitly promote to OCR exactly once when the shared predicate says the settled first attempt missed.

### Phase E: Wire automation and validation to the shared path

Implementation:

- route `AutomationRunner` through the shared executor,
- route `NavigationSelectorValidator` through the same shared executor,
- add logging and validator-report metadata for fallback attempts.

Exit condition:

- automation and validation execute the same selector tap behavior.

### Phase F: Hardening and follow-on parser work

Implementation:

- add OCR emitters for additional selectors only when live evidence shows they need explicit fallback,
- keep each new OCR emitter mapped to the same canonical `UiElementId`,
- do not add task-local or screen-flow-local exceptions.

Exit condition:

- selectors that need OCR retry are supported by the shared OCR parser path, not by one-off fallbacks.

## 13. Test plan

### 13.1 Provenance tests

Update [test_capture_and_vision.py](/c:/Users/lebel/pnc/tests/test_capture_and_vision.py) so it asserts:

- geometry-materialized selectors have `source_kind == GEOMETRY`,
- OCR-synthesized selectors have `source_kind == OCR`,
- selector-engine template matches have `source_kind == TEMPLATE`.

Also add observation-cost coverage proving:

- a base observation does not call OCR when OCR-only facts are not requested,
- an OCR-targeted observation does call OCR when the request requires it.

### 13.2 Executor tests

Add focused automation-framework coverage proving:

- a geometry-backed navigation tap retries once through OCR and succeeds,
- the first post-tap follow-up uses the narrow observation scope rather than unconditional OCR,
- a transitional first post-tap state settles to success without any OCR retry,
- a transitional first post-tap state settles to popup and hands off without any OCR retry,
- a transitional first post-tap state settles to a stable same-screen miss and only then enables OCR retry,
- no immediate OCR retry is attempted while the post-tap state remains `PNC_LOADING`,
- no OCR retry is attempted when a blocking popup appears,
- no OCR retry is attempted when the initial source was already OCR-backed,
- no OCR retry is attempted when the selector cannot be re-resolved from OCR after the miss.

Recommended location:

- [test_automation_framework.py](/c:/Users/lebel/pnc/tests/test_automation_framework.py)

### 13.3 Validator tests

Update [test_navigation_selector_validator.py](/c:/Users/lebel/pnc/tests/test_navigation_selector_validator.py) so it proves:

- validator taps use the shared primary-to-OCR fallback path for geometry-backed selectors,
- the report records whether OCR fallback was used,
- artifact paths refer to the correct capture for the corresponding destination state.

### 13.4 Negative coverage

Negative coverage is required because this feature performs a second tap.

Mandatory negative cases:

- same selector still geometry-only after the miss,
- first post-tap screen is transitional,
- settle budget is exhausted while the state remains transitional or unknown,
- selector has no safe reviewed outcomes,
- selector is not navigation-scoped,
- selector source was not geometry.

## 14. Failure-handling rules

- One OCR retry maximum per eligible tap.
- No retry without a post-miss OCR-backed selector target.
- No retry during loading, popup, or unknown transitional states.
- Transitional states must be handled through the bounded settle loop before any OCR fallback decision is made.
- No retry for unsafe or monetized outcomes.
- If OCR fallback also fails, return control to the current task verification and normal runner retry policy.
- If a selector should support OCR fallback but does not re-resolve from OCR, fail fast in diagnostics and fix the parser, not the task.

## 15. DRY enforcement checklist

Before this work is considered correct, confirm:

- there is exactly one reviewed click-outcome matcher,
- there is exactly one settled primary-miss predicate,
- there is exactly one observed selector-tap fallback implementation,
- provenance is emitted once at the observation-construction boundary,
- no task or screen flow implements its own primary-to-OCR retry,
- no separate selector capability list was introduced,
- OCR fallback consumes the same `UiElementId` already owned by the canonical selector registry.

## 16. Definition of done

This sub-plan is complete only when:

- the runtime records selector provenance,
- geometry-backed navigation taps can explicitly promote to OCR once after a settled phase-1 primary miss,
- automation and validation share the same implementation,
- the validator reports fallback usage and correct artifact ownership,
- new and updated tests cover both positive and negative cases,
- no parallel selector-resolution path was introduced.

## 17. Recommended immediate next increment

The smallest coherent implementation slice is:

1. add a typed staged-observation request model and stop requiring full OCR by default,
2. add selector provenance to `SelectorMatch` and `VisibleElement`,
3. centralize reviewed navigation outcome matching,
4. add one shared observed-action executor for geometry-backed navigation taps,
5. validate with one `PNC_BOTTOM_NAV_MORE` primary-miss-to-OCR-recovery test, one base-pass-no-OCR test, and one negative transitional-state test.

That slice is large enough to establish the correct architecture, but still small enough to remain clean, testable, and DRY.

