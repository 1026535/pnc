---
name: devin-game-knowledge
description: Consult Devin on repository-grounded game behavior, UI state, and workflow mechanics, returning evidence, confidence, and automation implications without implementing changes. Use for bounded game-knowledge research or read-only observation through Devin.
---

# Devin Game Knowledge

Use Devin as a read-only game-knowledge consultant when the lead needs a precise answer about Puzzles & Conquest behavior, screen state, workflow transitions, resource rules, or the evidence needed before automation. This skill does not replace the lead's reasoning, live-test authorization, or acceptance.

## Ownership and boundaries

- The Codex lead owns the question, authorization, interpretation of evidence, repository integration, and final acceptance.
- Devin owns only the bounded consultation. It may inspect the assigned repository, documented workflows, fixtures, saved artifacts, logs, and deterministic tests, and may run read-only commands that help answer the question.
- The consultation must not edit source, tests, configuration, fixtures, plans, or documentation; create commits or pull requests; change Git state; or install project dependencies. Preserve any pre-existing dirty worktree exactly.
- Do not expose or transmit credentials, tokens, ignored local configuration, account data, or unrelated files. Prompt with the minimum repository context needed for the question.
- A consultation does not authorize emulator, ADB, account, or live-game access. If live observation is necessary, require an explicit user request or approved plan naming the exact observation and target. Default to non-spending proof; never use premium currency, speedups, items, or other resources.

## Frame the question

Before launching Devin, make the question concrete enough to verify:

1. State the game behavior or uncertainty, the relevant screen/workflow, and the desired postcondition.
2. Name the account, castle, build/version, or other target only when it is already authorized and necessary. Do not invent a target.
3. Include known evidence paths or facts, and identify what must be distinguished (observed fact, inference, or unknown).
4. Define non-goals, especially implementation, mutation, spending, and broad live exploration.

Prefer one focused question per consultation. If the answer depends on a missing observation or a material design decision, ask Devin to return `NEEDS_LEAD` with the exact missing evidence or decision instead of guessing.

## Run the consultation

Use the bundled launcher from the exact Git repository root:

```powershell
py .agents/skills/devin-game-knowledge/scripts/consult_game_knowledge.py `
  --repo (Get-Location).Path `
  --question "Determine what happens after the Daily quest claim control is tapped. Use saved evidence first; do not connect to the emulator or mutate game state."
```

The launcher pins `swe-2-max`, uses Devin's read-only automatic permission mode, validates the exact Git root, records the pre/post worktree state, and stores the prompt, response, stderr, and result metadata under `.local-data/devin-game-knowledge/`. It must not be changed to dangerous or edit-accepting permissions for a knowledge consultation.

For a longer question, use `--question-file` rather than putting sensitive or complex content in shell history. Do not use a second worker to duplicate the same unresolved investigation.

## Required handback

Ask Devin to return a compact memo with these sections:

- `Answer`: the best-supported answer in plain language.
- `Findings`: each claim labeled `user-confirmed`, `repository-proven`, `artifact-observed`, `live-observed`, `inferred`, or `unknown`, with high/medium/low confidence.
- `Automation implications`: selectors, navigation/postcondition implications, reconciliation needs, mutation risk, and what must remain lead-owned.
- `Next smallest observation`: only if the evidence is insufficient; specify the exact read-only observation and why it resolves the uncertainty.
- `Handback`: `READY_FOR_REVIEW`, `NEEDS_LEAD`, `BLOCKED`, or `FAILED`, followed by limitations and any untouched worktree warning.

Treat the memo as a research input, not acceptance. The lead independently verifies findings and reconciles conflicts using the repository's evidence hierarchy. Do not convert an inferred game rule into an automation contract until the required observation or deterministic regression evidence exists.

Devin has its own CLI and skill system. This Codex skill supplies the consultation contract and question; it does not assume Devin has loaded Codex skills or Codex-only tools.

## Domain and expertise growth

This skill owns the *consultation transport and contract*, not the knowledge itself. Whatever Devin-side expertise skills exist in the target repository (for example `pnc-game-knowledge`, which answers from the reverse-engineered APK evidence) are discovered automatically by the launched session — keep questions domain-specific so the matching expertise triggers, and never enumerate Devin's skill inventory here.

To consult Devin on a new bounded domain, copy this skill under a new name, adjust the prompt preamble, run-directory namespace, and boundaries to that domain, and keep the memo contract verbatim so handbacks stay uniform across consultations.
