---
name: create-plan-with-chatgpt-pro
description: Create a repository-grounded implementation plan by running the regular create-plan workflow, consulting ChatGPT Pro in Chat mode with GPT-6 Pro, and having the active Codex task review the consultation before finalizing. Use when the user requests a plan with a ChatGPT Pro second opinion.
---

# Create Plan With ChatGPT Pro

## Workflow

1. Read [create-plan](../create-plan/SKILL.md) completely and use it as the canonical owner of planning, live-evidence, output, and quality requirements. Insert the Pro consultation after context and evidence gathering and before finalizing the target design.
2. Gather repository context and complete the regular skill's live-evidence gate. State the provisional objective, scope, current-state facts, constraints, and decision questions, but do not finalize the target design yet.
3. Invoke [consult-chatgpt-pro](../consult-chatgpt-pro/SKILL.md) with that material, the verified repository baseline, and relevant paths or symbols. Keep the consultation in Chat mode with GPT-6 Pro; do not use ChatGPT Work, Work cloud, Codex mode, or a fallback model.
4. Treat every Pro result as advisory. Record the consultation status as `complete`, `partial`, or `failed`, then have the active Codex task review any usable recommendation against the repository, applicable `AGENTS.md` files, tests, authored plans, and live evidence. Label agreements, corrections, unsupported claims, and unresolved unknowns.
5. Complete the regular skill's target design, implementation phases, risks, execution checklist, output contract, and quality gate, incorporating only conclusions that survive Codex review. A missing, partial, interrupted, quota-limited, or provider-failed Pro response does not block the plan by itself: continue from verified local evidence, disclose the degraded consultation status, and omit unsupported Pro claims. Stop only when information independently required to produce a responsible plan is unavailable.

## Output

Return the regular create-plan output plus the consultation status, a concise summary of any usable Pro findings, the Codex audit, the exact GitHub baseline/local overlay attempted, and unresolved decisions. For a partial or failed consultation, include the failure stage and explain which parts of the plan rely solely on Codex's repository review.
