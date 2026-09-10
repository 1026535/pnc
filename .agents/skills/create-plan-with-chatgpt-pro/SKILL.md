---
name: create-plan-with-chatgpt-pro
description: Create a repository-grounded implementation plan by running the regular create-plan workflow, consulting ChatGPT Pro in Chat mode with GPT-6 Pro, and having the active Codex task review the consultation before finalizing. Use when the user requests a plan with a ChatGPT Pro second opinion.
---

# Create Plan With ChatGPT Pro

## Workflow

1. Read [create-plan](../create-plan/SKILL.md) completely and use it as the canonical owner of planning, live-evidence, output, and quality requirements. Insert the Pro consultation after context and evidence gathering and before finalizing the target design.
2. Gather repository context and complete the regular skill's live-evidence gate. State the provisional objective, scope, current-state facts, constraints, and decision questions, but do not finalize the target design yet.
3. Invoke [consult-chatgpt-pro](../consult-chatgpt-pro/SKILL.md) with that material, the verified repository baseline, and relevant paths or symbols. Keep the consultation in Chat mode with GPT-6 Pro; do not use ChatGPT Work, Work cloud, Codex mode, or a fallback model.
4. Treat the Pro response as advisory. The active Codex task reviews material recommendations against the repository, applicable `AGENTS.md` files, tests, authored plans, and live evidence, labeling agreements, corrections, unsupported claims, and unresolved unknowns.
5. Complete the regular skill's target design, implementation phases, risks, execution checklist, output contract, and quality gate, incorporating only conclusions that survive Codex review. If the exact baseline, Chat mode, GPT-6 Pro selection, or grounded consultation is unavailable, report the blocker instead of finalizing an unreviewed plan.

## Output

Return the regular create-plan output plus a concise Pro consultation summary, Codex audit, exact GitHub baseline/local overlay, and unresolved decisions.
