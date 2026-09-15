# Planning Live Validation

Use this reference only when a plan changes selectors, screen classification, navigation, ADB/emulator integration, authored live workflows, scheduling, or resource-changing behavior.

## Batch Contract

For each live-dependent behavioral batch, state:

- the behavior and canonical owner being changed;
- its feature boundary and distinct use cases;
- the focused offline test or fixture;
- the live entry point that reaches the production boundary;
- observable precondition and success condition;
- the checkpoint triggers and final acceptance cases;
- exploration or strict mutation mode, when applicable;
- artifact needed to diagnose failure; and
- a bounded stop condition.

Run focused offline tests before checkpoints on modified code. Use the full portable suite only for broad shared behavior or final integration. A process exit does not replace an observed UI postcondition.

## Targets

Use one representative target by default. Add targets only when the contract names them, configuration differs materially, or evidence shows target-dependent behavior. Record `passed`, `applicability_skip`, or `blocked` only for targets actually required by that rationale.

Do not create a matrix for interchangeable targets or require a permanent live test for a rare state that is already covered deterministically offline.

## Mutation

Separate upstream navigation from the feature action when ownership permits. Re-observe identity, screen, selector, and applicable resource limits immediately before a strict mutation. Stop on an unknown consequential result; do not repeat spending merely to gain confidence.

Name prohibited adjacent actions only when they are plausible consequences of the chosen workflow, not as an exhaustive catalog.

## Promotion

Accept a feature when focused checks and every distinct feature-owned live use case pass. A development checkpoint may be reused only when it already met acceptance conditions and later changes did not invalidate it. A blocked live case prevents only the claims that depend on that boundary and should not trigger unrelated tests or exploration.

An unrelated navigation/preflight failure may use a manually established equivalent precondition. Report feature-action acceptance separately from the failed upstream route and unattended readiness. Manual setup cannot complete a route owned by the feature contract.

For scheduler changes, validate task-registration settings only when scheduling is in scope. For ordinary workflow changes, do not add scheduler checks.
