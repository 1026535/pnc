---
name: write-code-live
description: Implement PNC changes whose live validation uses in-game resources. Apply the standing non-Main full-balance testing authority; Main or explicitly restricted runs require their specific action and budget. Use write-code for implementation that needs no spending proof.
---

# Write Code Live

Follow [write-code](../write-code/SKILL.md). This skill binds resource use to the assigned proof under the canonical [standing game-resource authority](../test-bluestacks-live/SKILL.md#standing-game-resource-authority).

## Authorization

Spending-enabled testing is the default on all configured non-Main instances. The user's standing allowance is any/all available in-game resources needed for the assigned feature, including existing currency, items, speedups and energy. Incidental resource, troop and trap collection is authorized and is not spending. Do not request a new numeric budget or collection permission when this allowance applies.

Before execution, the coordinator records from the assignment, configuration and current state:

- exact account, target castle, and instance; naming the target castle in the current request or approved plan authorizes switching to it within that account and instance, while account or instance switching requires separate explicit authorization;
- exact action and why it is needed;
- resource types and the inherited full-available-balance allowance, or a narrower explicit user/test limit;
- observable precondition and success signal; and
- stop condition when identity, screen state, selector, or proof is uncertain.

The coordinator chooses the concrete feature-owned actions and useful attempt limits; these are execution decisions under existing authority. Missing brief details should be completed from that authority, not escalated as a new permission blocker. An explicit read-only/state-preservation test remains an exception. For Main, obtain the user's exact action and budget unless already supplied. Unknown target identity stops input until resolved.

This skill never authorizes real-money purchases, unrelated game actions, account changes, authored-config changes, or spending beyond an applicable explicit limit. Use existing effect-aware runtime interfaces; do not label collection READ_ONLY or bypass a rejected runtime capability.

## Workflow

1. Implement the smallest slice and run focused offline tests.
2. Follow [test-bluestacks-live](../test-bluestacks-live/SKILL.md), including its shared incident-reporting contract, before target preflight. Resolve the configured instance through the canonical runtime. Validate castle identity at initial instance takeover or after an authorized castle change or instance replacement; reuse that proof while instance continuity holds. Immediately before spending, confirm the current target, screen, and relevant resource state without repeating the full castle workflow.
3. Capture pre-action evidence, perform only the authorized action, and capture the post-action result.
4. On failure, inspect artifacts and fix offline first. Repeat a resource-using action only after a relevant implementation/state change and within the standing allowance or explicit limit. A non-Main retry needs no separate permission; repeating an unchanged failure is not useful proof.
5. Return to a safe stable screen when the existing flow supports it, then run any proportionate final validation.

Do not add generalized retry, recovery, or authorization machinery for unlikely cases. The exact budget and fresh precondition are the safety boundary.

## Report

State the live command or entry point, target, authorized and actual spend, observed result, relevant artifact paths, offline validation, and any blocker. Never include credentials or secret values.
