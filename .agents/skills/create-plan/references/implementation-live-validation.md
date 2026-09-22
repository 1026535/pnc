# Planning Live Validation

Use this reference only when a plan changes selectors, screen classification, navigation, ADB/emulator integration, authored live workflows, scheduling, or resource-changing behavior.

## Slice Contract

For each live-dependent slice, state:

- the behavior and canonical owner being changed;
- the focused offline test or fixture;
- the smallest live entry point that reaches the same production boundary;
- observable precondition and success condition;
- mutation and authorization boundary, when applicable;
- artifact needed to diagnose failure; and
- a bounded stop condition.

Run focused offline tests before live proof. Use the full portable suite only for broad shared behavior or final integration. A process exit does not replace an observed UI postcondition.

## Targets

Use one representative target by default. Add targets only when the contract names them, configuration differs materially, or evidence shows target-dependent behavior. Record `passed`, `applicability_skip`, or `blocked` only for targets actually required by that rationale.

Do not create a matrix for interchangeable targets or require a permanent live test for a rare state that is already covered deterministically offline.

## Mutation

Separate read-only navigation from the state-changing action. Re-observe identity, screen, selector, and budget immediately before mutation. Perform the minimum authorized action and stop on an unknown result; do not repeat spending merely to gain confidence.

For any proof that may spend in-game resources, include a batch-level authorization envelope in the plan: exact account and instance, target castle, permitted action(s) and purpose, resource type and aggregate maximum amount or attempts across the listed cases, observable precondition and success signal, and retry/stop conditions. Naming a specific target castle in the request or plan authorizes switching to that castle within the selected account and instance; it does not authorize switching accounts or instances. Group compatible cases under one envelope. A fully specified, approved plan authorizes its listed spend despite the default to non-spending proof; execute within that envelope without duplicate approval. This exception does not bypass the instance lease, target and identity checks, fresh action preconditions, maximum, or stop conditions, and never authorizes real-money purchases or unrelated account/game actions. If the plan is still a draft or an authorization detail is missing, mark only the affected spending proof as awaiting authorization and continue independent offline or non-spending work. Execution must follow [write-code-live](../../write-code-live/SKILL.md).

Name prohibited adjacent actions only when they are plausible consequences of the chosen workflow, not as an exhaustive catalog.

## Promotion

Promote a slice when focused checks and the necessary live proof pass. A blocked live check prevents promotion only when that boundary is material to the deployed behavior. It should not trigger unrelated tests or broader live exploration.

For scheduler changes, validate task-registration settings only when scheduling is in scope. For ordinary workflow changes, do not add scheduler checks.
