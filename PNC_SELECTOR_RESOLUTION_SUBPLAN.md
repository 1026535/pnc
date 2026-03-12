# PNC Selector Resolution Sub-Plan

## 1. Purpose

This document defines the canonical runtime design for selector interaction resolution when a selector is available through fixed geometry first, but should explicitly fall back to the existing OCR workflow if that geometry-backed click does not succeed.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md), which owns selector discovery and registry maturity,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable navigation flows,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which owns bootstrap and castle targeting,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns bounded feature-task behavior.

This file owns only the missing selector-resolution behavior:

- geometry-first selector taps,
- explicit OCR promotion after a verified geometry miss,
- one canonical runtime path shared by automation and selector validation,
- provenance and diagnostics required to make that behavior reliable and reviewable.

## 2. Why this is needed

The current repository already has the required building blocks, but they are not yet connected into one explicit selector-resolution policy.

Current facts:

- the selector registry is canonical and stores the selector id, screen scope, interaction metadata, reviewed click outcomes, and optional `relative_bounds`,
- the observation pipeline already runs OCR on every screenshot through `PncObservationEnricher`,
- some selectors already have OCR-derived visible-element synthesis for the same `UiElementId`,
- geometry materialization already fills in stable click regions for selectors that were not otherwise detected,
- the low-level action executor only taps the current visible target and does not know whether that target came from geometry or OCR,
- the automation runner only retries whole task increments,
- the navigation validator only settles and evaluates final outcomes.

That means the system can incidentally benefit from OCR on a later observation, but it does not have explicit code that says:

1. this tap used geometry,
2. that geometry-backed click missed,
3. the selector is now available from an OCR-backed target,
4. retry the same selector once through OCR before escalating to normal task failure.

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
3. run OCR enrichment,
4. reclassify with additional evidence,
5. detect selectors scoped to the resolved screen,
6. materialize geometry-backed selectors that are still missing.

Important consequence:

- OCR already exists as a canonical observation workflow,
- geometry is already treated as a fallback source of visibility for missing selectors,
- but the observation model currently drops the provenance of the resulting visible element.

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

- use reviewed screen-relative geometry first when it exists,
- if that geometry-backed click misses, explicitly promote the same selector to the OCR workflow when OCR can provide a better target,
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

The target design is one canonical selector interaction loop:

1. Resolve one selector from the current observation.
2. If the resolved source is already OCR-backed or template-backed, use it directly.
3. If the resolved source is geometry-backed and the selector has a reviewed safe navigation contract, perform one geometry tap.
4. Capture a post-tap observation.
5. If the post-tap observation proves success, stop.
6. If the post-tap observation is still a settled miss on the same source screen, re-resolve the same selector from the OCR-backed observation.
7. Retry the tap once from the OCR-derived target.
8. Capture a second post-tap observation and evaluate the same reviewed contract.
9. If it still fails, return control to the existing task or validator failure path.

This keeps the behavior:

- explicit,
- deterministic,
- geometry-first,
- OCR-assisted,
- shared by both automation and validation.

## 6. Goals

- Geometry stays the primary click strategy for reviewed fixed UI.
- OCR fallback becomes an explicit selector-resolution step, not an accidental side effect of later retries.
- One shared implementation serves both `AutomationRunner` and `NavigationSelectorValidator`.
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

## 8. Architectural requirements

- Single canonical implementation per concept.
- No duplicated click-outcome matching logic.
- No duplicated geometry-versus-OCR capability tables.
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
- `is_settled_geometry_navigation_miss(selector: SelectorDefinition, before: Observation, after: Observation, source_element: VisibleElement) -> bool`

This keeps one canonical definition of selector success.

### 9.3 OCR fallback must live in a shared observed-action layer

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
- intercept selector-backed taps that are eligible for explicit OCR fallback,
- reuse one observation callback to capture post-action states,
- return the final observation exactly once to the caller.

This preserves one low-level action abstraction and one high-level observed selector interaction abstraction.

### 9.4 Initial fallback scope must be intentionally narrow

Phase 1 fallback scope should be:

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
- this avoids unsafe or heuristic double taps.

Future extension is allowed, but only after a shared success contract exists for non-navigation selectors.

### 9.5 Canonical fallback algorithm

The fallback algorithm must be geometry-first and conservative.

Recommended flow for one eligible `TapAction`:

1. Resolve `selector = selector_registry.require(action.selector_id)`.
2. Resolve `source_element = before.require(action.selector_id)`.
3. Confirm `source_element.source_kind == GEOMETRY`.
4. Execute the original tap through the low-level executor.
5. Capture `first_after`.
6. Evaluate the reviewed safe outcomes with the shared matcher.
7. If a reviewed outcome matched, stop.
8. If `first_after` is clearly in transition, stop and let existing settle or task verification logic continue.
9. If `first_after` is still a settled miss on the same source screen, look for the same selector id in `first_after`.
10. Require that the replacement visible element exists and has `source_kind == OCR`.
11. Execute one second tap using that OCR-derived target.
12. Capture `second_after`.
13. Evaluate the same reviewed safe outcomes again.
14. Return `second_after` to the caller regardless of success or failure.

The implementation must cap this at one OCR retry. No loops.

### 9.6 What counts as a geometry miss

A geometry-backed click should be considered eligible for OCR promotion only when all of the following are true:

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
- the current settle and popup-recovery mechanisms should remain authoritative for those transitions.

### 9.7 OCR retry target selection

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

### 9.8 No selector-catalog schema change in phase 1

The current registry already contains enough information to support the first implementation slice:

- selector identity,
- interaction kind,
- reviewed click outcomes,
- relative geometry,
- screen scope.

The fallback policy can therefore be generic:

- geometry-backed source,
- safe reviewed navigation selector,
- settled same-screen miss,
- OCR-backed retry target exists.

Do not add a new catalog field yet.

Add schema only later if live evidence proves the generic policy is too broad or too narrow for a subset of selectors.

### 9.9 Shared implementation must cover both automation and validation

The live selector validator must use the same fallback path as automation.

Required direction:

- `AutomationRunner` uses the new shared observed-action executor,
- `NavigationSelectorValidator` also uses that same executor or the same shared selector-tap helper,
- both consume the same reviewed-outcome matcher.

This is mandatory. If validation and automation tap selectors differently, the validator stops being authoritative.

### 9.10 Diagnostics must make fallback visible

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

### 10.1 `pnc_automation/pnc/observation.py`

Add:

- `VisibleElementSourceKind`
- `VisibleElement.source_kind`

Update helper constructors and test helpers to require or default that field explicitly.

### 10.2 `pnc_automation/vision/image_models.py`

Add:

- `SelectorMatch.source_kind`

This prevents provenance from being lost before matches are converted into visible elements.

### 10.3 `pnc_automation/vision/observation_builder.py`

Update:

- template and OCR-region matches to emit `SelectorMatch.source_kind`,
- `_matches_to_visible_elements(...)` to carry that source into `VisibleElement`,
- geometry materialization to emit `VisibleElement(source_kind=GEOMETRY)`.

### 10.4 `pnc_automation/vision/pnc_observation_enricher.py`

Update all `_make_visible*` helpers to emit `source_kind=OCR`.

This must happen centrally inside helper functions so the provenance does not get duplicated across each parser.

### 10.5 New shared selector-interaction helper module

Create a new module, for example:

- [selector_interactions.py](/c:/Users/lebel/pnc/pnc_automation/vision/selector_interactions.py)

Move or add:

- shared reviewed-navigation matching,
- safe outcome filtering,
- settled geometry-miss evaluation.

This module becomes the canonical owner of selector interaction success rules.

### 10.6 New observed-action executor

Create a shared high-level executor, for example:

- [observed_action_executor.py](/c:/Users/lebel/pnc/pnc_automation/automation/observed_action_executor.py)

Responsibilities:

- mirror the existing `execute_actions(...)` contract,
- delegate low-level mechanics to `ActionExecutor`,
- intercept eligible geometry-backed `TapAction`s,
- perform one OCR retry when the shared geometry-miss predicate says it is justified.

### 10.7 `pnc_automation/automation/runner.py`

Wire the runner to use the shared observed-action executor instead of directly using only the low-level executor for observed selector taps.

Important rule:

- the runner keeps owning task retry and replan policy,
- the new executor owns selector-level geometry-to-OCR promotion,
- those two retry layers must not be merged.

### 10.8 `pnc_automation/vision/navigation_selector_validator.py`

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

### Phase A: Add selector provenance

Implementation:

- add `VisibleElementSourceKind`,
- add `source_kind` to `VisibleElement` and `SelectorMatch`,
- populate provenance in template matching, OCR-region matching, OCR syntheses, and geometry materialization,
- update all supporting test helpers.

Exit condition:

- every selector-backed visible element tells the runtime whether it is `TEMPLATE`, `OCR`, or `GEOMETRY`.

### Phase B: Centralize reviewed selector outcome matching

Implementation:

- move reviewed navigation outcome matching into one shared helper module,
- add one shared settled geometry-miss predicate,
- update the validator to consume the shared helper instead of its private copy.

Exit condition:

- there is one canonical reviewed-outcome matcher and one canonical geometry-miss predicate.

### Phase C: Implement shared geometry-to-OCR promotion

Implementation:

- add the shared observed-action executor,
- wire one OCR retry for eligible geometry-backed `TapAction`s,
- ensure the OCR retry only runs after a settled same-screen miss,
- preserve existing low-level pacing and observation timing.

Exit condition:

- one geometry-backed navigation tap can explicitly promote to OCR exactly once when the shared predicate says the first tap missed.

### Phase D: Wire automation and validation to the shared path

Implementation:

- route `AutomationRunner` through the shared executor,
- route `NavigationSelectorValidator` through the same shared executor,
- add logging and validator-report metadata for fallback attempts.

Exit condition:

- automation and validation execute the same selector tap behavior.

### Phase E: Hardening and follow-on parser work

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

### 13.2 Executor tests

Add focused automation-framework coverage proving:

- a geometry-backed navigation tap retries once through OCR and succeeds,
- no OCR retry is attempted when the first post-tap observation enters `PNC_LOADING`,
- no OCR retry is attempted when a blocking popup appears,
- no OCR retry is attempted when the initial source was already OCR-backed,
- no OCR retry is attempted when the selector cannot be re-resolved from OCR after the miss.

Recommended location:

- [test_automation_framework.py](/c:/Users/lebel/pnc/tests/test_automation_framework.py)

### 13.3 Validator tests

Update [test_navigation_selector_validator.py](/c:/Users/lebel/pnc/tests/test_navigation_selector_validator.py) so it proves:

- validator taps use the shared geometry-to-OCR fallback path,
- the report records whether OCR fallback was used,
- artifact paths refer to the correct capture for the corresponding destination state.

### 13.4 Negative coverage

Negative coverage is required because this feature performs a second tap.

Mandatory negative cases:

- same selector still geometry-only after the miss,
- first post-tap screen is transitional,
- selector has no safe reviewed outcomes,
- selector is not navigation-scoped,
- selector source was not geometry.

## 14. Failure-handling rules

- One OCR retry maximum per eligible tap.
- No retry without a post-miss OCR-backed selector target.
- No retry during loading, popup, or unknown transitional states.
- No retry for unsafe or monetized outcomes.
- If OCR fallback also fails, return control to the current task verification and normal runner retry policy.
- If a selector should support OCR fallback but does not re-resolve from OCR, fail fast in diagnostics and fix the parser, not the task.

## 15. DRY enforcement checklist

Before this work is considered correct, confirm:

- there is exactly one reviewed click-outcome matcher,
- there is exactly one settled geometry-miss predicate,
- there is exactly one observed selector-tap fallback implementation,
- provenance is emitted once at the observation-construction boundary,
- no task or screen flow implements its own geometry-to-OCR retry,
- no separate selector capability list was introduced,
- OCR fallback consumes the same `UiElementId` already owned by the canonical selector registry.

## 16. Definition of done

This sub-plan is complete only when:

- the runtime records selector provenance,
- geometry-backed navigation taps can explicitly promote to OCR once after a settled miss,
- automation and validation share the same implementation,
- the validator reports fallback usage and correct artifact ownership,
- new and updated tests cover both positive and negative cases,
- no parallel selector-resolution path was introduced.

## 17. Recommended immediate next increment

The smallest coherent implementation slice is:

1. add selector provenance to `SelectorMatch` and `VisibleElement`,
2. centralize reviewed navigation outcome matching,
3. add one shared observed-action executor for geometry-backed navigation taps,
4. use it first for `AutomationRunner` and `NavigationSelectorValidator`,
5. validate with one `PNC_BOTTOM_NAV_MORE` geometry-miss-to-OCR-recovery test and one negative transitional-state test.

That slice is large enough to establish the correct architecture, but still small enough to remain clean, testable, and DRY.
