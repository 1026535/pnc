---
name: implement-with-luna-global
description: Orchestrate substantial repository implementation through GPT-5.6 Luna workers while the invoking root agent retains requirements, architecture, coordination, formal review, and final responsibility. Use only when explicitly invoked after material intent is resolved.
---

# Implement With Luna Global

Use Luna for substantial implementation while the invoking agent (the **root**) remains responsible for intent, architecture, coordination, review, and the user conversation. Follow the active repository's instructions and established workflows; this skill does not replace them.

## Configure the invocation

- Spawn implementers with `model: gpt-5.6-luna` and `reasoning_effort: xhigh` by default.
- If the user explicitly supplies a supported Luna reasoning effort, use it for every worker unless scoped more narrowly. Ask about an unsupported value instead of silently changing it.
- Use `fork_context: false` with a focused implementation packet by default. Enable a small amount of prior context only when it materially reduces restatement without importing irrelevant context.

Natural language such as `use $implement-with-luna-global at high reasoning` is sufficient; do not create a separate configuration artifact.

## Preserve the role boundary

The root owns:

- unresolved requirements and user choices;
- design, architecture, canonical ownership, public contracts, and task decomposition;
- worker assignment, steering, integration decisions, formal review, and the final answer.

Luna owns substantial concrete coding, tests, documentation, cleanup, validation, and review corrections within approved intent. Luna may make ordinary low-level choices that preserve that intent and the repository's rules.

The root may make a small mechanical integration or contained correction when another handoff would cost more than the work. Do not edit the same worktree while a worker is writing. Return substantial work or architectural decisions to Luna only after the root resolves the intended design.

## Establish readiness

Use an approved plan or execution record when the repository or user provides one. Otherwise, confirmed conversation intent is enough when it resolves material behavior, ownership, interfaces, migration, and acceptance criteria. Do not create planning or tracking artifacts solely for this workflow.

Before dispatching, read and honor applicable repository instructions such as `AGENTS.md`, contribution guidance, design documents, task-specific plans, and the PNC skills that govern the work. For ordinary implementation, use `skills/write-code`; for formal review, use `skills/review-code`; for live emulator validation, use `skills/test-bluestacks-live`; and for any explicitly authorized resource-spending test, use `skills/write-code-live`. If implementation evidence challenges an approved decision, pause the affected work, resolve the decision with the user when necessary, and then steer Luna with the result.

## Send an authoritative packet

Give each worker only information that changes implementation decisions:

- the objective and authoritative plan or concise confirmed intent;
- its exact scope, working directory or branch, and pre-existing changes to preserve;
- applicable repository instructions and canonical owners to inspect;
- required behavior, constraints, non-goals, migration, cleanup, and documentation impact;
- acceptance evidence and proportionate validation commands;
- PNC-specific validation expectations: targeted `unittest` coverage followed by the full offline suite when the change is cross-cutting, plus the smallest relevant opt-in BlueStacks smoke path for live behavior;
- escalation conditions for changes to ownership, public API, invariant, architecture, scope, or validation intent;
- the completion contract: self-review, validation results, changed files, commit or diff state, divergences, and unresolved issues.

Link authoritative local material instead of copying it. Do not ask Luna to redesign settled architecture or repeat research already completed by the root.

## Prefer one persistent implementer

Start with one lead Luna and reuse it for the coherent implementation, validation, documentation, cleanup, and corrections while its context remains useful.

- Steer an active worker at meaningful boundaries.
- Resume the same idle worker with new evidence or review findings.
- Interrupt only when continued work would materially waste effort, violate approved intent, or cross a design boundary.
- Replace the worker only when its accumulated context is no longer useful or it cannot continue reliably.
- Wait in long intervals; avoid status ceremonies and repeated polling.

Only one agent may write a given worktree at a time. The root may inspect it read-only while Luna works.

## Parallelize only independent work

Use additional Luna workers only when slices are substantial, stable, non-overlapping, independently testable, and likely to save more time than setup and integration cost.

Concurrent writers require isolated branches and worktrees. Use the repository's prescribed worktree tooling when one exists; otherwise use the environment's safe standard workflow. Assign exact paths and non-overlapping files or ownership. Do not share writable worktrees, indexes, editors, build outputs, services, ports, databases, or generated-output locations concurrently.

The root assigns slices centrally and converges them on one authoritative implementation branch. If integration reveals hidden architectural coupling, stop and resolve the design before continuing. Run whole-scope validation after integration.

## Steer by evidence

When a worker struggles or diverges, identify whether the cause is:

- a local implementation defect or missed repository fact: provide focused evidence and let Luna correct it;
- incomplete or contradictory instructions: clarify the packet and resume;
- an architectural or product decision: stop implementation, resolve it in the main conversation, then continue;
- unsafe coupling between slices: serialize or repartition the remaining work.

Do not take over substantial implementation merely because the first attempt failed, and do not preserve a flawed direction merely to keep a worker running.

## Complete, review, and correct

1. Have the implementer self-review the complete diff, run proportionate validation, update required documentation, and follow the repository's commit policy.
2. Verify that one authoritative branch, commit, or diff contains the complete integrated result.
3. The root formally reviews that result against the approved intent and repository rules using `skills/review-code`.
4. Send substantive findings back to the persistent Luna implementer. The root may fix a truly small contained item when that is cheaper and clearer.
5. Re-review the corrected authoritative result and continue only while concrete findings remain.
6. Finish when review has no actionable findings, required validation is satisfactory, and the result is on the intended branch or worktree.

Ask the user only for a material unresolved choice, new authority, or genuine external blocker. Never push, publish, deploy, or perform another externally consequential action unless the user or governing repository workflow explicitly authorizes it.

## Keep the workflow lean

Do not spawn an agent merely because a slot is free. Do not duplicate planning or repository instructions across workers. Add no coordinator agent, lock protocol, shared status ledger, fixed phase count, or checkpoint ceremony without a concrete task-specific need.
