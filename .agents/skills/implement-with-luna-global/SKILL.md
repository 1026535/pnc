---
name: implement-with-luna-global
description: Orchestrate substantial repository implementation through GPT-5.6 Luna workers while the invoking root agent retains requirements, architecture, coordination, formal review, and final responsibility. Use only when explicitly invoked after material intent is resolved.
---

# Implement With Luna Global

Use Luna for substantial implementation while the invoking agent (the **root**) remains responsible for requirements, architecture, coordination, integration, formal review, acceptance, and user communication. The root is the sole architecture and formal acceptance authority. Each Luna implementer must self-review its complete implementation before handoff, but that self-review is an implementation quality gate, not independent or formal acceptance. Follow the active repository's instructions and established workflows; this skill does not replace them.

## Configure Delegation

- Use the current Codex subagent or collaboration tools, not a separate user-owned task or `create_thread`.
- Spawn implementers with model `gpt-5.6-luna` and `xhigh` reasoning by default, using the parameter names exposed by the current tool. If that model or effort is unavailable, report the limitation instead of substituting another model.
- If the user explicitly supplies a supported Luna reasoning effort, apply it to every worker unless scoped more narrowly.
- Send a focused implementation packet without inherited conversation history when the tool supports that choice. Include prior context only when it changes implementation decisions.

Natural language such as `use $implement-with-luna-global at high reasoning` is sufficient; do not create a separate configuration artifact.

## Preserve the role boundary

The root owns:

- unresolved requirements and user choices;
- design, architecture, canonical ownership, public contracts, and task decomposition;
- worker assignment, steering, integration decisions, formal review, acceptance, and the final answer.

Luna owns only substantial concrete implementation within approved intent, including the code changes and narrowly necessary test, documentation, or cleanup edits that are part of implementing that intent. Before handoff, Luna must inspect the whole consolidated diff against the task, repository rules, and approved design, run proportionate validation, fix the issues it finds, and report the final reviewed result. This self-review is an implementation quality gate; Luna must not own requirements interpretation, architecture changes, integration decisions, formal review, or acceptance. If self-review exposes a requirements or architecture blocker, Luna must escalate it instead of silently changing scope.

Do not edit the same worktree while a worker is writing. Return substantial implementation corrections to the same Luna implementer after the root resolves the intended design or formal-review finding.

## Establish readiness

Use an approved plan or execution record when the repository or user provides one. Otherwise, confirmed conversation intent is enough when it resolves material behavior, ownership, interfaces, migration, and acceptance criteria. Do not create planning or tracking artifacts solely for this workflow.

Before dispatching, read and honor applicable repository instructions such as `AGENTS.md`, contribution guidance, design documents, task-specific plans, and the PNC skills that govern the work. For ordinary implementation, use [write-code](../write-code/SKILL.md); for formal review, use [review-code](../review-code/SKILL.md); for live emulator validation, use [test-bluestacks-live](../test-bluestacks-live/SKILL.md); and for explicitly authorized resource-spending tests, use [write-code-live](../write-code-live/SKILL.md). If implementation evidence challenges an approved decision, pause the affected work, resolve the decision with the user when necessary, and then steer Luna with the result.

## Send an authoritative packet

Give each worker only information that changes implementation decisions:

- the objective and authoritative plan or concise confirmed intent;
- its exact scope, working directory or branch, and pre-existing changes to preserve;
- applicable repository instructions and canonical owners to inspect;
- required behavior, constraints, non-goals, migration, cleanup, and documentation impact;
- required evidence and proportionate validation commands;
- PNC-specific validation expectations: targeted `unittest` coverage followed by the full offline suite when the change is cross-cutting, plus the smallest relevant opt-in BlueStacks smoke path for live behavior;
- escalation conditions for changes to ownership, public API, invariant, architecture, scope, or validation intent;
- the completion contract: before handoff, Luna must self-review the complete consolidated result, correct its findings, and report changed files, implementation status, validation commands and results, self-review findings and corrections, commit or diff state, divergences, and unresolved implementation issues. Do not request a formal review or acceptance verdict from Luna.

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

## Self-review, review, and correct

1. Have Luna implement the approved intent, then inspect the whole final consolidated diff against the task and repository rules, run proportionate validation, and correct every implementation issue it finds before handoff. Luna must report the changed files, validation and results, self-review findings and corrections, divergences, and unresolved issues. Treat this self-review as implementation context and a quality gate, never as formal review or acceptance.
2. The root receives and reviews only Luna's final consolidated work, except for read-only progress inspection or a real requirements/architecture blocker that Luna escalates. The root verifies that one authoritative branch, commit, or diff contains the complete integrated result and runs the proportionate validation required by the governing repository instructions.
3. The root formally reviews that final result against the approved intent and repository rules using [review-code](../review-code/SKILL.md). The root remains the sole formal review and acceptance authority.
4. If the root's final review finds an issue, send precise, bounded correction instructions to the same persistent Luna implementer. Luna corrects only within the approved intent, then self-reviews the new complete consolidated result, reruns proportionate validation, and reports the updated findings, corrections, and status before handing it back.
5. The root re-reviews that corrected consolidated result and repeats the implementation/self-review/formal-review loop only while concrete findings remain.
6. Finish when the root's formal review has no actionable findings, required validation is satisfactory, and the result is on the intended branch or worktree.

Ask the user only for a material unresolved choice, new authority, or genuine external blocker. Never push, publish, deploy, or perform another externally consequential action unless the user or governing repository workflow explicitly authorizes it.

## Keep the workflow lean

Do not spawn an agent merely because a slot is free. Do not duplicate planning or repository instructions across workers. Add no coordinator agent, lock protocol, shared status ledger, fixed phase count, or checkpoint ceremony without a concrete task-specific need.
