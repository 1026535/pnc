# Step 3.5: Puzzles & Conquest Selector Resolution Sub-Plan

## 1. Purpose

This document defines the canonical runtime design for selector resolution, including non-geometry fallback when a selector cannot be trusted through screen-relative coordinates alone.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](PNC_SELECTOR_REFINEMENT_SUBPLAN.md), which owns selector discovery, registry growth, and selector maturity,
- [PNC_SCREEN_FLOW_SUBPLAN.md](PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable navigation flows,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which owns bootstrap and castle-targeting behavior,
- [PNC_SPATIAL_SURFACE_SUBPLAN.md](PNC_SPATIAL_SURFACE_SUBPLAN.md), which owns world-map and home-city spatial-surface modeling,
- [PNC_TASK_SUBPLAN.md](PNC_TASK_SUBPLAN.md), which owns bounded task-feature plans.

This file owns the missing architectural layer between:

- the static selector catalog,
- OCR- and parser-derived screen interpretation,
- geometry-backed selector materialization,
- and the final `Observation.visible_elements` map consumed by flows and tasks.

## 2. Why this is needed

The current runtime already proves that a non-coordinate workflow is reachable:

- template detection can populate selectors directly,
- OCR-backed screen parsers can classify screens and synthesize selectors such as home-city bottom navigation, More-menu actions, bag controls, popup close buttons, login fields, and castle-selection entries,
- geometry-backed `relative_bounds` can still provide stable screen-relative click regions when no stronger detection exists.

That baseline is useful, but the ownership is split across multiple places:

- `PillowSelectorEngine` detects template and OCR-region selectors,
- `PncObservationEnricher` classifies screens and injects OCR-derived selectors,
- `SelectorRegistry.materialize_for_screen()` creates geometry-backed selectors after classification.

The result is that selector resolution is currently a concept with multiple implementations.

That creates several architectural problems:

- one selector can be resolved through different disconnected mechanisms with no single canonical policy,
- `detection_kind` claims one primary mode even when the runtime effectively uses several,
- geometry-backed selectors can appear as visible even when no live detection confirmed them,
- `ActionExecutor` cannot distinguish a high-confidence detected selector from a last-resort geometry fallback,
- if a geometry-backed tap misses, the runtime has no canonical fallback contract for trying OCR or template resolution for the same selector,
- screen parsers currently both interpret the screen and sometimes bypass selector-resolution ownership by directly injecting clickable selectors.

This is exactly the kind of drift that will make the automation fragile over time if it is not corrected now.

## 3. Current confirmed baseline

The current repo already contains the most important proof points that this plan should preserve:

- the observation pipeline can classify home city from OCR bottom-navigation evidence when templates are unavailable,
- the observation pipeline can classify the bag screen from OCR evidence when templates are unavailable,
- the More-menu flow can expose `PNC_MORE_SETTINGS` and `PNC_MORE_MANAGE_CHAR` without relying purely on auto-materialized geometry,
- reviewed navigation outcomes already exist and can be used to tell whether a selector-driven tap actually reached the intended destination.

Those behaviors are correct in principle and should not be discarded.

The problem is not that OCR/template fallback is impossible.

The problem is that the fallback is not yet represented as one canonical selector-resolution model.

## 4. Scope

This sub-plan defines:

- the canonical selector-resolution model,
- the runtime ownership boundary between screen parsing and selector resolution,
- the catalog shape required to describe ordered resolution strategies for one selector,
- selector-resolution provenance and confidence handling,
- the integration point for guarded fallback after a failed geometry-based navigation tap,
- the migration plan from the current split implementation,
- the validation requirements for the new architecture.

This sub-plan does not:

- redesign the screen-classification rules themselves,
- replace dynamic list-entry parsing with fixed selectors,
- replace the spatial-surface architecture for world-map or home-city scene objects,
- add task-local selector heuristics,
- justify generic blind tap retries for every failed action.

## 5. Goals

- Single canonical implementation per concept.
- No duplicated selector-resolution logic.
- Fail-fast validation for invalid or unsupported selector configuration.
- Minimal boilerplate in both catalog and runtime code.
- Preserve the current OCR/template reachability that already works.
- Make geometry a deliberate fallback strategy, not an implicit side channel.
- Keep tasks and flows consuming the same canonical `UiElementId` values.
- Make selector provenance visible enough that higher layers can tell whether a tap came from exact detection, parser evidence, or geometry fallback.

## 6. Non-goals

- Do not add a second selector registry or a second selector-definition format.
- Do not let tasks or flows choose between `template selector ids` and `OCR selector ids` for the same control.
- Do not move raw OCR matching into tasks, flows, or the action executor.
- Do not keep both the old `detection_kind`-plus-special-cases model and a new resolution model long term.
- Do not treat world-map objects or home-city buildings as fixed selectors just to fit this plan.

## 7. Core architectural decision

The canonical selector id remains singular.

What changes is how one selector is resolved at runtime.

The runtime should no longer treat selector resolution as:

- one catalog `detection_kind`,
- plus optional parser injection,
- plus optional geometry materialization.

Instead, every fixed selector should define one ordered resolution policy.

That policy should say, for this selector and this screen:

1. which exact strategies are preferred first,
2. which parser-derived candidate can supply the selector if exact detection is unavailable,
3. whether geometry may be used as a last-resort fallback,
4. and which strategy actually produced the visible element on this observation.

The observation layer, not the action executor, must own that fallback decision.

This is the smallest clean design because:

- tasks keep using the same selector ids,
- screen parsers keep owning screen interpretation,
- the registry stays canonical,
- and the action layer remains simple.

## 8. Canonical ownership model

### 8.1 Screen parsers own interpretation, not final selector policy

Screen parsers should continue owning:

- OCR normalization through shared text anchors,
- screen evidence,
- dynamic collection parsing,
- typed screen-specific facts,
- parser-derived selector candidates that are only valid when that screen interpretation is trusted.

Screen parsers should not remain the final authority that decides whether a selector is considered visible.

Instead, they should emit parser candidates keyed by canonical selector id, and the selector-resolution layer should decide whether and when that candidate wins over template detection, OCR-region detection, or geometry fallback.

### 8.2 Selector resolution owns final selector visibility

Selector resolution should be the single layer that decides whether a selector is present in `Observation.visible_elements`.

That layer should:

- consume the resolved screen type,
- consume exact detection results,
- consume parser candidates from the trusted screen parser,
- consume geometry fallback metadata,
- choose the first successful resolution step from the selector's ordered strategy list,
- attach provenance to the resolved visible element.

### 8.3 Action execution stays simple

`ActionExecutor` should continue to:

- require the selector from the current observation,
- tap its `action_point` or bounds center,
- remain unaware of OCR, template matching, or parser logic.

That is the correct boundary.

A fallback-aware retry should exist only above the executor, where destination validation is available.

## 9. Target runtime model

### 9.1 New selector-resolution concepts

The runtime should introduce explicit typed models for selector resolution.

Recommended types:

- `SelectorResolutionKind`
- `SelectorResolutionStep`
- `SelectorResolutionPolicy`
- `ResolvedSelectorSource`
- `SelectorResolutionContext`
- `ScreenInterpretation`

Recommended strategy kinds:

- `template`
- `ocr_region`
- `parser_candidate`
- `relative_bounds`

This is intentionally small.

It covers the resolution behaviors already present in the repo without inventing unnecessary abstraction.

### 9.2 `ScreenInterpretation`

The current `PncObservationEnricher` should be refactored toward a screen-interpretation model.

Recommended responsibility:

- build OCR result once,
- build text anchors once,
- produce screen evidence,
- produce parser candidates keyed by `UiElementId`,
- produce dynamic list entries,
- produce other typed observation additions such as current castle or visible account id.

This can reuse the current logic, but the ownership should become explicit.

The important change is that parser-produced selector candidates become input to selector resolution instead of bypassing it.

### 9.3 `SelectorResolutionContext`

One resolution context should be built per screenshot and shared across resolution steps.

It should include:

- the screenshot image,
- screen type,
- image size,
- OCR result,
- text anchors,
- exact selector matches already computed,
- parser candidates,
- cached template or OCR-region step results,
- any other shared per-screenshot data needed by multiple strategies.

This keeps OCR and template work DRY.

### 9.4 `ResolvedSelectorSource`

Every resolved `VisibleElement` should carry provenance.

Recommended fields:

- `resolution_kind`
- `strategy_index`
- `strategy_label` or equivalent typed metadata
- `is_fallback`

This should not become a large debug-only structure.

It exists for real runtime behavior:

- diagnostics,
- artifact review,
- guarded retry decisions,
- and confidence-aware validation.

### 9.5 `VisibleElement`

`VisibleElement` should remain the canonical selector instance exposed to flows and tasks.

It should gain only the minimal new metadata required to preserve provenance.

The rest of the system should not receive a second parallel selector-instance model.

## 10. Canonical catalog design

### 10.1 Replace singular detection with ordered resolution

The current selector schema overloads the following fields:

- `detection_kind`
- `relative_bounds`
- `materialize_relative_bounds`

That is no longer sufficient once one selector may legitimately use:

- exact template detection when available,
- parser-derived OCR fallback when exact detection is unavailable,
- geometry only as a last resort.

The long-term canonical schema should replace that split with an ordered `resolution:` section.

Recommended shape:

```yaml
selectors:
  - id: PNC_HOME_WORLD_SWITCH
    screens:
      - PNC_HOME_CITY
    status: click_mapped
    interaction_kind: navigation
    click:
      anchor: center
      outcomes:
        - safe_to_click: true
          monetized: false
          target_screen: PNC_WORLD_MAP
          verification_selectors:
            - PNC_WORLD_HOME_NAV
            - PNC_WORLD_SEARCH_BUTTON
    resolution:
      - kind: template
        template_path: pnc_home_world_switch.png
        threshold: 0.98
      - kind: parser_candidate
      - kind: relative_bounds
        x_ratio: 0.0
        y_ratio: 0.905
        width_ratio: 0.19
        height_ratio: 0.095
        action_x_ratio: 0.065555555556
        action_y_ratio: 0.95
```

This makes the selector contract explicit:

- try exact visual detection first,
- accept the trusted parser candidate second,
- only then fall back to geometry.

### 10.2 Parser-candidate resolution semantics

`parser_candidate` should mean:

- the active trusted screen interpreter may emit a candidate for this exact selector id,
- if it does, that candidate is eligible as a resolution step at this point in the selector's ordered policy,
- if it does not, resolution continues to the next step.

No extra selector id should be introduced.

No parser-local hidden selector namespace should exist.

### 10.3 Relative-bounds semantics

`relative_bounds` should stop meaning "auto-materialize this selector for the whole screen slice."

It should mean only:

- this selector has a reviewed geometry fallback step,
- it may be used only if all earlier steps in the same selector policy fail,
- and the resolved visible element must record that it came from geometry fallback.

This removes the need for `materialize_relative_bounds`.

### 10.4 Template asset path ownership

The current implicit `selector_id.value.lower()` template-path convention should not remain the long-term canonical storage format.

The resolution schema should allow explicit template asset paths.

If the repo keeps temporary implicit defaults during migration, they should be treated as a compatibility bridge only and then removed.

### 10.5 Planned selectors

`planned` selectors may still exist as known future work.

Rules:

- a `planned` selector may omit `resolution`,
- any selector above `planned` must have a valid resolution policy,
- tasks and flows must not rely on selectors that remain unresolved in the registry.

## 11. Required catalog validation rules

The catalog loader and updater must fail fast when:

- one selector declares duplicate resolution steps that would make ordering ambiguous,
- a selector uses `relative_bounds` before a stronger exact or parser-derived strategy when that ordering is not intentional,
- a selector above `planned` has no resolution steps,
- a `relative_bounds` step is missing valid ratios,
- a `template` step has no asset path once implicit defaults are removed,
- a `parser_candidate` step is used for a selector that no trusted screen parser can ever produce,
- a label-only selector declares geometry fallback or click metadata that contradicts its interaction kind,
- a navigation selector declares geometry fallback but has no reviewed destination verification contract.

The offline registry updater must enforce the same rules, not a weaker duplicate parser.

## 12. Target runtime pipeline

The runtime build of one observation should become:

1. Build a shared per-screenshot vision snapshot.
2. Run exact probe detection for the classifier probe slice using probe-eligible exact strategies.
3. Run the screen interpreter once to obtain:
   - screen evidence,
   - parser candidates,
   - list entries,
   - typed screen facts.
4. Classify the screen from exact selector evidence plus screen-interpreter evidence.
5. Resolve every selector relevant to the final screen through its ordered resolution policy.
6. Build the final `Observation` from resolved selectors plus screen-interpreter additions.

This keeps the current high-level shape of `ObservationBuilder`, but removes the split-brain selector ownership.

## 13. Resolution algorithm

For one selector on one resolved screen:

1. Load the selector's ordered resolution steps.
2. Evaluate each step in order.
3. On the first successful step:
   - create one `VisibleElement`,
   - attach resolution provenance,
   - stop evaluating later steps.
4. If no step succeeds:
   - the selector is not visible.

Important rules:

- resolution is per selector, not a global fallback toggle,
- parser candidates are only eligible after the screen is trusted,
- geometry does not auto-win just because it exists,
- one selector id yields at most one resolved visible element.

## 14. Why fallback belongs before action execution

The current executor does the correct thing for its layer:

- it asks the observation for a selector,
- it taps the resolved target,
- it does not know whether that target came from template, OCR, or geometry.

That should remain true.

If selector fallback is implemented inside the executor, the system will immediately duplicate:

- selector lookup rules,
- image-state assumptions,
- and screen-specific heuristics.

The observation layer already owns the screenshot and the interpretation context.

That is where selector fallback belongs.

## 15. Guarded retry after a failed geometry-based navigation tap

The user requirement also raises a second problem:

- what if the selector was resolved through geometry,
- the tap happened,
- but the tap landed incorrectly because the geometry fallback was wrong for the live resolution or UI variant?

That should not be handled as a generic executor retry.

It should be handled only when there is semantic validation available.

### 15.1 Allowed retry case

A post-click retry is allowed only when all of the following are true:

- the selector is a reviewed navigation selector,
- the selector has reviewed `click_outcomes`,
- the tap used a geometry-backed resolution source,
- the observed destination does not match any reviewed outcome,
- a stronger alternate strategy for the same selector exists and can be re-resolved on a fresh observation.

### 15.2 Retry owner

This behavior belongs in validation- or flow-level logic that can compare:

- source screen,
- tapped selector,
- resolved selector provenance,
- destination observation,
- reviewed click outcomes.

The most natural first owner is the navigation-validation path, because it already:

- taps one selector,
- observes the destination,
- and matches it against reviewed outcomes.

Later, if reusable screen flows need the same guarded behavior, that logic should be extracted once into a shared navigation-action helper. It should still remain above the bare executor.

### 15.3 Retry limits

Rules:

- only one fallback retry per tap attempt,
- only promote from weaker to stronger strategy, never loop sideways,
- if the stronger alternate strategy still fails, surface `SelectorResolutionError` or a navigation-validation failure,
- always record artifacts for both the original miss and the retry attempt.

## 16. Migration strategy

### Phase A: Introduce typed resolution models

Implement:

- typed resolution-step models,
- typed provenance model,
- typed screen-interpretation result model,
- catalog loader support for `resolution:`.

Keep old fields only as a temporary migration bridge while the runtime is ported.

Exit condition:

- the runtime can load the new schema and validate it.

### Phase B: Refactor screen interpretation ownership

Refactor the current `PncObservationEnricher` into a screen-interpreter model that returns:

- screen evidence,
- parser candidates,
- list entries,
- typed screen facts.

Do not leave parser-produced selectors as a bypass around selector resolution.

Exit condition:

- parser candidates are produced canonically and no longer treated as ad hoc observation injections.

### Phase C: Add `SelectorResolver`

Implement the shared per-selector resolution engine and wire it into `ObservationBuilder`.

The builder should stop:

- merging parser-injected selectors directly into `visible_elements`,
- and auto-materializing all geometry-backed selectors for the screen slice.

Instead, it should resolve selectors through ordered steps.

Exit condition:

- `Observation.visible_elements` is produced only through the selector resolver.

### Phase D: Port existing selectors to the new schema

Migrate the highest-value selectors first:

- `PNC_HOME_WORLD_SWITCH`
- `PNC_BOTTOM_NAV_MORE`
- `PNC_MORE_SETTINGS`
- `PNC_MORE_MANAGE_CHAR`
- `PNC_HOME_LORD_INFO_SHORTCUT`
- `PNC_WORLD_HOME_NAV`
- `PNC_WORLD_SEARCH_BUTTON`
- `PNC_WORLD_COORDINATE_BAR`

This slice proves the architecture on:

- home-city navigation,
- More-menu branching,
- world-map entry and return,
- fixed overlay UI that currently mixes exact detection and geometry fallback.

Exit condition:

- those selectors resolve through the new model without regressions.

### Phase E: Add guarded navigation retry

Use selector provenance plus reviewed outcomes to support one fallback-aware retry after a geometry-based miss.

Start with the navigation validator.

Only extract shared runtime logic after the behavior is proven and the duplication boundary is clear.

Exit condition:

- navigation validation can distinguish a wrong geometry tap from a true selector mismatch and can attempt one stronger retry when configured.

### Phase F: Delete obsolete model paths

After the migrated selector slice is stable:

- remove `materialize_relative_bounds`,
- remove the old direct auto-materialization path,
- remove any now-dead `detection_kind` behavior that exists only to preserve the old split architecture,
- remove or repurpose unused enum values such as `ANCHORED_REGION` rather than leaving half-implemented semantics in the registry model.

Exit condition:

- one canonical selector-resolution implementation remains.

## 17. Testing requirements

### 17.1 Catalog and loader tests

Add tests that fail fast for:

- invalid resolution ordering,
- duplicate resolution steps,
- invalid geometry fallback declarations,
- selectors above `planned` with no resolution policy,
- invalid parser-candidate references,
- invalid template-step configuration.

### 17.2 Observation-building tests

Add screenshot-style tests proving:

- template detection wins over parser candidate when both are available and ordered that way,
- parser candidate wins over geometry when exact detection is unavailable,
- geometry is used only when stronger earlier steps fail,
- the resolved selector records the correct provenance,
- home-city OCR fallback and bag OCR fallback still work,
- More-menu selectors still resolve correctly through OCR-driven parser candidates.

### 17.3 Negative tests

These are mandatory.

Add tests proving:

- ambiguous parser evidence keeps the screen `UNKNOWN`,
- geometry fallback does not fabricate selector visibility on the wrong screen,
- a selector without any successful resolution step remains absent,
- the runtime does not duplicate one selector from both parser and geometry.

### 17.4 Navigation-validation tests

Add tests proving:

- a geometry-backed navigation miss can trigger one stronger fallback retry when configured,
- a template- or parser-resolved selector does not blindly retry,
- missing reviewed outcomes still fail fast,
- retry stops after one alternate attempt.

### 17.5 Live validation

When the migrated slice is ready, rerun targeted live checks for:

- `home -> more -> settings -> manage char`,
- `home -> world map`,
- `world map -> home`,
- at least one live case where geometry would previously have been the only available path.

## 18. Relationship to other plans

### 18.1 Selector refinement

[PNC_SELECTOR_REFINEMENT_SUBPLAN.md](PNC_SELECTOR_REFINEMENT_SUBPLAN.md) still owns:

- which selectors exist,
- how selectors mature,
- offline catalog updates,
- reviewed click outcomes.

This plan does not replace that ownership.

It defines the runtime model that consumes the refined selector registry cleanly.

### 18.2 Screen flows

[PNC_SCREEN_FLOW_SUBPLAN.md](PNC_SCREEN_FLOW_SUBPLAN.md) should continue consuming resolved selectors from observations.

It should not add its own fallback-resolution rules.

Any guarded retry reused by flows must be extracted from the same canonical navigation-resolution helper, not copied per flow.

### 18.3 Spatial surfaces

[PNC_SPATIAL_SURFACE_SUBPLAN.md](PNC_SPATIAL_SURFACE_SUBPLAN.md) remains correct:

- fixed world-map overlay controls such as `PNC_WORLD_HOME_NAV`, `PNC_WORLD_SEARCH_BUTTON`, and the coordinate bar remain selectors,
- map objects remain spatial objects, not selectors.

This plan improves how fixed overlay selectors are resolved.

It does not change the spatial-object model.

## 19. Final architecture checklist

Before this work is considered complete, confirm all of the following:

- there is exactly one canonical selector-resolution system,
- the selector catalog expresses ordered resolution policy directly,
- parser-derived selector candidates do not bypass selector resolution,
- geometry fallback is explicit and provenance-aware,
- action execution still does not contain OCR or selector-resolution logic,
- blind tap retries do not exist,
- guarded retries only occur when reviewed outcome validation exists,
- obsolete selector-resolution fields and code paths were removed,
- no task or flow defines its own selector fallback heuristic,
- invalid selector configuration fails fast.

## 20. Recommended next implementation slice

The smallest coherent first slice is:

1. add the new typed `resolution:` schema and loader support,
2. refactor screen interpretation to return parser candidates,
3. migrate `PNC_BOTTOM_NAV_MORE`, `PNC_MORE_SETTINGS`, and `PNC_MORE_MANAGE_CHAR`,
4. migrate `PNC_HOME_WORLD_SWITCH`,
5. add observation tests and navigation-validator tests for the migrated selectors.

That slice is enough to prove the architecture on both:

- the More-menu OCR-backed fallback path,
- and the home-to-world geometry-sensitive navigation path.

It is also small enough to complete without redesigning unrelated task or spatial-surface work.
