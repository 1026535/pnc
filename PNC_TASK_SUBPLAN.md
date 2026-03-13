# Step 6: Puzzles & Conquest Feature Task Sub-Plan

## 1. Purpose

This document is the dependency-ordered sixth plan and now governs post-account-navigation feature planning through bounded tracer bullets.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains focused on the primary platform architecture,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which continues to own bootstrap, login, popup recovery, and castle targeting,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns canonical reusable navigation,
- [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md), which owns selector maturity.

This file is no longer the place to fully design every future task in one horizontal backlog. It now defines the planning model, migration rules, and active backlog shape for feature-scoped post-navigation work.

## 2. Why this changed

Post-navigation work is better driven by bounded feature slices than by one document trying to fully pre-design building, research, gathering, campaign, chat, and future work all at once.

This shift keeps planning aligned with the current architecture:

- reusable navigation remains centralized,
- selector growth remains incremental,
- feature work can refine only the next required slice,
- duplication across task designs is removed instead of growing over time.

## 3. Scope

This sub-plan should define:

- how active post-navigation work is broken into dedicated feature plans,
- how a tracer bullet consumes the current framework without waiting for global completeness,
- how feature-local knowledge is promoted into shared selectors or flows when reuse becomes clear,
- how validation and closure are tracked for each bounded feature slice.

This sub-plan does not own:

- login or castle-selection behavior,
- the selector registry,
- reusable flow definitions,
- script-runner policy,
- a second parallel task contract.

## 4. Canonical planning model

Each active post-navigation feature should have its own dedicated plan file once work begins. Examples:

- `PNC_FEATURE_CHAT_TRACER_BULLET.md`
- `PNC_FEATURE_BUILDING_UPGRADE.md`
- `PNC_FEATURE_RESEARCH.md`
- `PNC_FEATURE_GATHERING.md`
- `PNC_FEATURE_CAMPAIGN.md`

This file owns the planning contract and migration rules for those feature plans. It should retain only index-level backlog status and shared planning guidance, not the full detailed design of every feature.

## 5. Feature intake checklist

No new post-navigation feature should start implementation work until it has passed this intake checklist in one dedicated feature plan.

Required intake items:

- the feature has one dedicated plan file,
- the plan names one bounded tracer-bullet outcome,
- the plan states whether it refines an existing runtime task or proposes a new one,
- the plan lists the exact entry screen assumptions and account-navigation prerequisites,
- the plan classifies every navigation step as `existing canonical flow`, `feature-local path`, or `promotion candidate`,
- the plan lists the exact selector increment required for the current slice,
- the plan defines explicit verification evidence,
- the plan defines the smallest required validation gate,
- the plan names which duplicated planning text will be removed or replaced once the feature is integrated.

If any intake item is missing, the feature is not ready to begin implementation refinement.

## 6. Tracer-bullet rules

Each feature plan should follow these rules:

- choose one bounded outcome with clear entry and exit states,
- refine only the selectors required for that feature's current slice,
- consume existing canonical flows before inventing new navigation,
- promote genuinely reusable navigation into [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md),
- keep provisional or one-off click paths inside the active feature plan until reuse is proven,
- fail fast on unsupported screens, selectors, or observations,
- define the smallest required validation gate before considering the slice complete,
- delete or close superseded feature-planning text instead of keeping parallel backlog descriptions.

## 7. Per-feature template

Each feature plan should follow one canonical template:

### Feature purpose

- what end-to-end outcome the feature owns,
- what remains out of scope for the current slice.

### Tracer-bullet outcome

- the narrowest valuable increment to validate end to end,
- the exact success state that proves the slice works.

### Entry conditions and prerequisites

- required `ScreenType`,
- required account-navigation guarantees,
- required selectors and screenshots,
- invalid preconditions that must fail fast.

### Observations required

- visual facts needed from `vision`,
- game meaning derived by `pnc`,
- OCR fields or dynamic-list extraction required.

### Shared flows consumed

- canonical flows required from [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md),
- any candidate navigation that may need promotion later.

### Feature-local actions and decisions

- feature-specific taps, input, selection, or verification logic,
- any policy or parameter decisions that are unique to the feature.

### Verification

- expected destination screen or state,
- selector, OCR, or dynamic-list evidence required,
- negative conditions that indicate failure.

### Failure handling

- allowed retries,
- popup recovery interaction,
- when to stop the run and capture artifacts.

### Validation gate

- required unit tests for any extracted pure logic,
- required screenshot integration tests for selectors, OCR, or observation assumptions,
- required live smoke validation for the end-to-end feature path.

### Promotion candidates

- selectors that should move into the canonical registry,
- navigation that should become a canonical flow,
- feature-local logic that should stay local because it is not reusable.

## 8. Integration checklist

Before a feature is considered integrated into the framework, confirm all of the following:

- the feature still has exactly one owning plan file,
- the feature plan references selectors canonically instead of defining its own selector list format,
- reusable navigation has been promoted into [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md),
- any remaining feature-local navigation is explicitly marked non-reusable or still under evaluation,
- the runtime task ownership is clear and non-duplicated,
- validation evidence is recorded at the feature-plan level,
- superseded planning text has been removed from older backlog sections instead of being left in parallel.

This checklist is the closure gate that ties a feature plan back into the shared framework documents.

## 9. Current feature backlog

The current post-navigation backlog should now be treated as feature candidates rather than as one shared design document:

- `Chat tracer bullet`
- `Building upgrade`
- `Research`
- `Gathering`
- `Campaign`

Recommended first feature when the goal is framework refinement through a real vertical slice:

- `Chat tracer bullet`: start from a verified in-game state, open one fixed chat channel, send one canned message, and verify that exact message appears in the visible chat history.

That slice is narrow enough to stay bounded, but broad enough to exercise navigation, OCR or list interpretation, input, verification, and artifact capture.

## 10. Relationship to the runtime task model

The runtime task contract remains canonical in code. Existing task identifiers such as building upgrade, research, gathering, and campaign are still the authoritative runtime extension points.

This planning shift changes how work is sequenced and documented, not how the runtime task abstraction is owned.

Rules:

- feature plans may implement or refine one runtime task at a time,
- a tracer bullet may initially stay narrower than the eventual full task scope,
- if a new stable feature such as chat graduates from tracer bullet to supported automation behavior, it should gain one canonical runtime task shape rather than a parallel ad hoc path.

## 11. Relationship to selector refinement

This sub-plan must consume the selector registry as input. It must not create a parallel selector-definition system.

If a feature needs a new selector:

- add or refine it through [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md),
- request only the selector increment needed for the active feature slice,
- avoid treating full-registry completion as a prerequisite for bounded feature work.

## 12. Relationship to screen flows

This sub-plan should consume shared navigation from [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md). It must not duplicate reusable navigation logic across feature plans.

If a feature needs a new reusable path:

- document it first as a feature-local candidate,
- promote it into the screen-flow sub-plan once reuse is clear,
- then replace the duplicated feature description with a reference to the canonical flow.

## 13. Relationship to automation orchestration

This sub-plan should consume generic task orchestration rules from [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md). It must not redefine the global task contract, script-runner behavior, or run-level retry policy.

This sub-plan also assumes that account navigation behavior, including login bootstrap and any explicit castle alignment requested by earlier steps, has already been handled by [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md).

## 14. Validation requirement

Each feature plan must define its own validation gate. No post-navigation feature should be marked complete without:

- the smallest relevant automated tests,
- screenshot coverage for any screen or selector assumptions,
- a targeted live smoke run for the bounded end-to-end slice,
- explicit artifact capture on mismatch or failure.

## 15. Closure rule for the old horizontal backlog

The previous one-document task backlog is now superseded as the primary planning model.

Going forward:

- this file should stay as the feature-planning contract and index,
- detailed design should move into dedicated feature plans as features become active,
- old duplicated task-planning text should be removed once its owning feature plan exists.
