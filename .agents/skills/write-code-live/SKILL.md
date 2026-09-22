---
name: write-code-live
description: Implement PNC changes whose necessary live validation may spend in-game resources. Use only when the request or an approved plan supplies the exact action, target, and budget; use write-code for non-spending work.
---

# Write Code Live

Follow [write-code](../write-code/SKILL.md). This skill adds permission handling for a necessary, bounded resource-spending proof.

## Authorization

Before spending, obtain from the current request or approved plan:

- exact account, target castle, and instance; naming the target castle in the current request or approved plan authorizes switching to it within that account and instance, while account or instance switching requires separate explicit authorization;
- exact action and why it is needed;
- resource type and maximum amount or attempts;
- observable precondition and success signal; and
- stop condition when identity, screen state, selector, or proof is uncertain.

When all items are already supplied, proceed without duplicate confirmation. Missing information blocks only the spending action; continue safe offline diagnosis.

This skill never authorizes real-money purchases, unrelated game actions, account changes, authored-config changes, or spending beyond the stated budget.

## Workflow

1. Implement the smallest slice and run focused offline tests.
2. Resolve the configured instance through the canonical runtime. Validate castle identity at initial instance takeover or after an authorized castle change or instance replacement; reuse that proof while instance continuity holds. Immediately before spending, confirm the current target, screen, and relevant resource state without repeating the full castle workflow.
3. Capture pre-action evidence, perform only the authorized action, and capture the post-action result.
4. On failure, inspect artifacts and fix offline first. Repeat spending only when the authorization includes a retry and the diagnosis changed; otherwise stop at the remaining blocker.
5. Return to a safe stable screen when the existing flow supports it, then run any proportionate final validation.

Do not add generalized retry, recovery, or authorization machinery for unlikely cases. The exact budget and fresh precondition are the safety boundary.

## Report

State the live command or entry point, target, authorized and actual spend, observed result, relevant artifact paths, offline validation, and any blocker. Never include credentials or secret values.
