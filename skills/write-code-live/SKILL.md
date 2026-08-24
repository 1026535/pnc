---
name: write-code-live
description: Implement PNC code changes with bounded live validation that may spend explicitly authorized in-game resources. Use only when the user or approved plan authorizes the exact live resource-spending action, target, and budget; use write-code for ordinary implementation or read-only live testing.
---

# Write Code Live

Use [../write-code/SKILL.md](../write-code/SKILL.md) as the canonical coding workflow. Read it completely before acting and apply all of its architecture, testing, incremental implementation, and live-validation rules. This skill changes only the authorization boundary for a narrowly scoped live test: an explicitly authorized test may spend in-game resources.

## Authorization Gate

Before any resource-spending action, record all of the following from the user's request or approved plan:

- the account and currently active castle; do not switch accounts or castles unless the user explicitly names and authorizes that navigation;
- the exact live action and why the code change requires it;
- the resource type and maximum amount, count, or number of attempts that may be spent;
- the expected precondition, observable success signal, and post-action artifact needed to prove the result; and
- the stop condition if the precondition, screen classification, selector, or post-action proof is missing.

If any item is missing, stop before spending and request the missing authorization. Invocation of this skill alone is not permission to choose a target, invent a budget, or spend resources.

## Live Iteration

1. Run the narrowest relevant offline tests first.
2. Let the canonical runtime resolve and launch the configured BlueStacks instance when needed, connect through configured ADB settings, and verify the active account, castle, app, and current screen using typed observations.
3. Capture a labeled pre-action screenshot and observation, including the relevant resource balance or state when the existing observation pipeline exposes it.
4. Implement one small runnable slice and execute only the authorized live action for that slice. Use existing tasks, navigation, selectors, observation waits, and artifact storage; do not add raw coordinate or ad hoc ADB control paths.
5. Capture and inspect the post-action screenshot, OCR/observation data, logs, and any domain-specific proof. Confirm that the observed change matches the expected result and remains within the authorized budget.
6. Stop after the smallest successful proof. If the action fails, the result is ambiguous, or the budget is exhausted, preserve artifacts and investigate without spending again unless the user explicitly authorized a bounded retry count.
7. Return the runtime to a safe stable screen when the existing navigation flow can do so, then run the final offline validation required by `write-code`.

## Scope Boundary

This skill permits only the explicitly authorized in-game resource expenditure required by the test. It does not authorize purchases with real money, account or castle switching, login or logout, sending mail or chat, marching, gathering, attacking, deleting data, changing authored configuration, or unrelated game actions. Treat each resource-spending action as irreversible: verify first, spend once, observe immediately, and stop on uncertainty.

## Final Report

Report the exact live command or smoke target, account, active castle, authorized resource budget, amount actually spent, pre-action and post-action artifact paths, observed result, offline tests, and any remaining risk. Never include credentials or secrets. If live validation was blocked, state the exact blocker and remaining command instead of claiming completion.
