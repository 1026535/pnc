---
name: write-code-live
description: Implement PNC changes with resource-consuming live work, distinguishing authorized exploration from strictly limited canaries, unattended execution, protected actions, and uncertain retries.
---

# Write Code Live

Follow [write-code](../write-code/SKILL.md) and the phase rules in [test-bluestacks-live](../test-bluestacks-live/SKILL.md). This skill owns resource authorization for live implementation work.

## Authorization

The `live_testing` role is the exploration profile and supplies standing authority for bounded agent-led exploration on its configured target; do not add a parallel role for the same purpose. Exploration spending follows this precedence: an explicit instruction in the current user prompt, then an applicable agent or execution profile, then the repository default of all non-premium, non-protected in-game resources without a numeric per-action budget. Diamonds are non-premium for this policy. A higher-priority instruction may narrow or replace the default for its named scope. State the exploration purpose and scope.

No exploration profile or prompt authorizes real-money purchases, automatic paid refills, protected items, account/castle switching, unrelated or consequential actions, or replay of an uncertain mutation unless the applicable strict authorization below is supplied; real-money purchases remain prohibited.

Before an acceptance canary, unattended/daily execution, protected or irreversible action, or uncertain retry, obtain from the user or applicable standing authorization:

- exact account and active castle, including any authorized switching;
- exact action and why it is needed;
- resource type and cumulative maximum amount or attempts;
- observable precondition and success signal; and
- stop condition when identity, screen state, selector, or proof is uncertain.

When all items are supplied, proceed without duplicate confirmation. Missing information blocks only the strict action; continue safe exploration or offline work within its existing authority.

Canary and unattended limits apply to diamonds because of the execution mode. This skill never authorizes real-money purchases, unrelated game actions, account changes, authored-config changes, or strict-mode spending beyond cumulative limits.

## Workflow

1. Declare exploration or strict mode before the live phase.
2. For modified code, finish the coherent batch and run focused offline tests first; exploration of unknown behavior may precede implementation.
3. Resolve the configured instance and freshly verify account, castle, screen, and relevant resource state.
4. Capture pre-action evidence, perform only in-scope actions, and capture observable results.
5. On failure, follow the live skill's classification and retry rules. Strict spending repeats only with retry authority and a changed diagnosis or state.
6. Return to a stable screen when supported and complete proportionate acceptance.

Do not add generalized retry, recovery, or authorization machinery for unlikely cases. Fresh preconditions, exploration scope, and strict-mode limits are the safety boundaries.

## Report

State the mode, entry point, target, authorized scope or limits, observed consumption when known, result, artifacts, offline validation, and material limitations. Never include credentials or secret values.
