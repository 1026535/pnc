---
name: implement-with-luna-global
description: Delegate substantial repository implementation to GPT-5.6 Luna workers while the root retains design, review, and acceptance. Use only when explicitly invoked after material intent is resolved.
---

# Implement With Luna Global

The root owns requirements, architecture, integration, formal review, acceptance, and user communication. Luna implements bounded, approved work.

## Configuration

- Use current collaboration tools, not a separate user-owned task.
- Spawn Luna with model `gpt-5.6-luna` and `xhigh` reasoning unless the user explicitly chooses another supported Luna effort.
- If the requested model or effort is unavailable, report it; do not substitute another model.
- Send focused packets without inherited history when possible.

## Dispatch

Before delegation, resolve material behavior, ownership, interfaces, migration, and acceptance criteria from an approved plan or the conversation. Do not create planning or tracking artifacts solely for this workflow.

Give the worker only decision-relevant context:

- objective, exact scope, worktree, and pre-existing changes to preserve;
- authoritative repository instructions and design;
- required behavior, non-goals, and migration;
- proportionate validation and any live boundary; and
- handoff requirements: changed files, tests/results, self-review corrections, and unresolved implementation issues.

Link authoritative files instead of copying them. Do not ask Luna to redesign settled architecture or repeat completed research.

## Coordination

Prefer one persistent implementer for coherent work and corrections. Do not delegate a small task when setup and review cost exceed the likely benefit.

Use multiple workers only for substantial, non-overlapping, independently testable slices. Give concurrent writers isolated worktrees and disjoint ownership. If hidden coupling appears, serialize the work or resolve the design before continuing.

Only one agent writes a worktree. The root may inspect read-only while Luna works and should not take over the same files mid-turn.

## Review And Completion

1. Luna implements, runs proportionate checks, self-reviews the consolidated result, fixes its findings, and reports the final state.
2. The root reviews the complete diff against the request and repository rules, using [review-code](../review-code/SKILL.md), and runs only validation needed to confirm the worker's evidence or cover integration risk.
3. Send concrete corrections back to the same worker when practical. Repeat only while actionable findings remain.
4. Finish when the root finds no actionable issue and required validation is satisfactory.

Use [write-code](../write-code/SKILL.md) for implementation guidance, [test-bluestacks-live](../test-bluestacks-live/SKILL.md) when a live boundary truly requires proof, and [write-code-live](../write-code-live/SKILL.md) only for authorized spending.

Do not push, publish, deploy, or perform another consequential action unless authorized. Do not add coordinators, ledgers, lock protocols, fixed phase counts, or checkpoint ceremonies without a concrete need.
