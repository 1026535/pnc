---
name: devin-implement
description: Delegate concrete implementation and evidence-gathering packages to persistent local Devin SWE-2 Max workers while the Codex lead owns complex reasoning, design, and acceptance. Use when the user invokes this skill or requests implementation through Devin.
---

# Devin Implement

The current Codex lead owns architecture, uncertain problem-solving, integration decisions, and acceptance. SWE-2 Max handles grunt work such as concrete implementation, routine repairs, documentation, tests, and bounded evidence gathering. Delegate work that is inexpensive to specify and verify; the lead also implements when diagnosis and edits are tightly coupled or another handoff would cost more. Default to one persistent worker, with up to three for independent packages. Do not add another frontier agent for supervision or review.

**Worker role guard:** If `DEVIN_IMPLEMENT_ROLE` is set or you are assigned as a worker, complete your brief without launching agents or applying this skill's orchestration steps.

## Establish the work package

Use focused file ranges, searches, and summaries of test results. Keep raw artifacts and large transcripts on disk; return their exact paths with the decisions and results. The shared launcher enables earlier native compaction on fresh and resumed implementation/live turns. Reuse cohesive sessions and send delta briefs; a high token count alone does not justify restarting or splitting a package. Follow the bounded context-failure diagnosis in [runtime.md](references/runtime.md), without unchanged retries.

Invocation or a user request to delegate to Devin authorizes this workflow; discovery alone does not.

Read `.agents/instructions/subagent-coordination.md` when present and not already in context. The target repository is the assigned working directory, **not the repository holding this skill**.

Assess expected lead effort across specification, monitoring, integration, review, and likely corrections, not just who writes the code. Delegate substantial resolved changes, caller migrations, documentation, and specified validation together when they form a coherent package. Resolve material uncertainty about behavior, ownership, interfaces, and algorithms before assigning dependent implementation. A missing fact may justify a bounded reproduction or measurement; the lead interprets ambiguous evidence. SWE-2 may make ordinary implementation choices within those decisions.

Use [handoff.md](references/handoff.md) for a compact package with named owners, resolved decisions, acceptance evidence, and escalation conditions. Link authoritative material instead of copying it or repeating the conversation. Choose useful handback boundaries; an entire plan is appropriate only when its remaining work is sufficiently concrete. Prove a consequential uncertain assumption before broad dependent implementation, without imposing fixed phases or splitting trivial edits into separate assignments. Give each validation scope one owner and identify lead-only tools. Follow an existing ledger's ownership when applicable.

For a multi-plan, multi-worker, or resumable epic, keep one durable coordinator ledger at `.local-data/<epic-id>/coordinator-ledger.md` in the primary checkout. Reuse an existing status or coordination file when it can serve as that one ledger; link detailed plans, batches, and evidence instead of maintaining duplicate status records. Use [epic-ledger.md](references/epic-ledger.md) for the required fields and transition rules. Create or reconcile the ledger before dispatch or resumption. At minimum it records the authorized scope and authority source, acceptance revision and append-only amendments, current owner, next action and trigger, candidate identity, and worker/run/turn plus live-batch/evidence references. For dependent queues, identify the critical-path blocker and the plan or case IDs it holds up. On resumption, reconcile ledger state against terminal worker handoffs, local processes, the live batch, candidate tree, monitor, and lease or reservation state before dispatching. A late callback may add evidence to a paused or closed record, but it cannot resume the scope or dispatch work. Update ownership and next action at every dispatch, handback, pause, resume, transfer, and acceptance.

The worker returns when its package is complete or needs lead reasoning; it need not finish the whole feature first. Returning `NEEDS_LEAD` is appropriate when evidence challenges the chosen approach, a material decision arises, or repeated attempts produce no useful new evidence. Include the exact failure, relevant changes, attempted remedies and results, and the decision needed. Routine defects remain with SWE-2. Do not require the worker to exhaust possible experiments or declare an external blocker before involving the lead.

## Launch and wait efficiently

Use the bundled Windows launcher; [runtime.md](references/runtime.md) contains the commands and recovery procedure. It pins `swe-2-max` on fresh and resumed turns, disables nested subagents, suppresses Devin commit/PR attribution, and supervises the child process tree. Do not substitute another model or effort.

Full local access is already authorized for this workflow. Always show Devin's live-output console unless the user explicitly requests no console; do not select `--no-console` autonomously. Narrow access only when the user requests it or the execution environment requires it.

Keep a distinct run directory and verified session per worker; reuse them for its related packages and corrections. Resume with the changed decisions, requested work, and affected checks; do not replay the original brief. Never use `--continue` or select the most recent session.

Launch the supervisor independently using the runtime command. It has no task-duration deadline. Completion, returned blockers, and failures use native task messaging. Create or reuse one native heartbeat for this lead, with a 27-minute interval and exactly this prompt: `Cache keepalive only. Do not call tools, inspect worker progress, or produce commentary. Return an empty final response.` Start the bundled Python monitor against that heartbeat and register every worker run directory. Confirm its initial active acknowledgement before waiting; the runtime reference owns setup and recovery commands.

After launch, yield; rely on the monitor for routine progress, and check Devin manually only when needed.

**Keepalive wake fast path:** Immediately return an empty final response, without tools, worker status, `/btw`, progress analysis, or a manual timer update. Python observes completed lead turns and rearms the same heartbeat afterward, including after callback handling. This moves rearming out of the lead and avoids the extra model request needed to consume a tool result. Reset occurs after completion, within polling/bridge latency, rather than in a lead tool call before returning. This is an unmeasured cache-reuse experiment: do not claim guaranteed cache hits, a token ceiling, or percentage savings.

Python samples local worker metadata every 15 minutes, notifying only on an actionable anomaly or a conclusively failed completion delivery. It does not ask Devin questions or interpret progress. Activity establishes neither correctness nor convergence. Long-running tools may legitimately be quiet; silence never authorizes cancellation. Keep one monitor per lead, covering all workers. Stop it and confirm the heartbeat is paused at acceptance or explicit stop; package handbacks and corrections do not end monitoring. If setup or monitoring fails, report the concrete limitation and repair it; do not silently restore recurring lead progress checks.

Use plain `status` and the native `/btw` method in the runtime reference **on demand**, when the user requests progress or an anomaly needs diagnosis. Retrieve a pending question by request ID instead of submitting another. Compare the short answer with known results, treating it as self-report. If it is vague, repetitive, contradictory, or missing, inspect one bounded relevant output sample or test/diff excerpt. Do not routinely read both. Verify completion independently; use the lead-reasoning boundary when evidence reveals uncertainty or poor convergence.

On notification or interruption, read the short result and handoff, then inspect evidence needed for review or recovery. Never load Devin's full conversation, context, or export into the lead context. Identify handled results by run directory and turn so callbacks do not repeat review or dispatch. Before another writer starts, confirm local processes and any external tests have released their resources. After completing the follow-up, use the monitor's `resolve` command in [keepalive.md](references/keepalive.md) to record the concrete continuation, completion, or wait/blocker. Receipt or beginning a review is not resolution. The monitor can remind an idle lead about delivered results without that record; it never restarts Devin or accepts work itself.

## Resolve uncertainty and steer

On a reasoning handback or evidence of poor convergence, investigate the specific unresolved issue and choose who should finish that portion. Resume SWE-2 when the remaining work is resolved and still inexpensive to specify and verify. When diagnosis requires tightly coupled edits, findings recur, or each proposed fix leads to another uncertain handoff, the lead takes that portion through implementation and targeted validation directly. Do not turn successive hypotheses into serial worker assignments. Unaffected independent packages can continue. Lead intervention does not require user approval unless it exposes a genuine user decision or new authority requirement.

Use `steer` for a concise, resolved correction while the worker can continue: state the changed direction and affected checks without replaying the brief. It updates the main conversation through the existing connection. Its small machine receipt adds no acknowledgement prompt, transcript read, or automatic retry; assess compliance through normal evidence/review. `ask` remains a side question and cannot redirect work. Commands and delivery semantics belong to [runtime.md](references/runtime.md).

Prefer natural package handbacks when intervention can wait. Use `cancel` when active work must stop, continuing would waste material work, or an unresolved design boundary requires lead intervention. Cancellation requests a graceful native stop first, with process termination as fallback. Preserve partial work and release the affected writer and external resources before lead edits or a worker resume. Do not launch a competing writer. No arbitrary task-duration limit or retry quota applies.

Use existing handoffs, task context, and test artifacts for continuity. Direct intervention is scoped to the difficult portion; delegate other resolved work when it still saves effort. Neither substantial coding nor a reasoning handback automatically determines who must implement the next change.

## Parallel work and integration

Use two or three workers only for substantial independent packages with settled interfaces and expected savings after context transfer, setup, integration, and review. Different files alone do not establish independence. Do not parallelize competing diagnoses of the same unresolved design or duplicate investigation and validation. More workers shorten independent work; they do not resolve a serial correction loop. Follow an explicit user concurrency limit.

Give concurrent writers separate branches/worktrees through the repository's worktree tooling. Assign exact paths, stable interfaces, and ownership of mutable resources. Transfer required uncommitted changes explicitly; a new worktree does not include them automatically. Serialize editor validation and other shared build resources.

Integrate on one authoritative ref before final review. The lead resolves conflicts that expose design uncertainty and applies the same delegation decision to integration edits. Add checks for combined behavior or evidence invalidated by integration; reuse passing evidence for unchanged contracts.

## Review once, then converge

The lead reviews the complete stable result after implementation, local validation, and integration, using the actual changes and relevant evidence. Use the project's dedicated implementation-review guidance when available; it owns the rubric and review format. A worker's completion claim or successful CLI exit does not establish acceptance.

1. Collect acceptance-blocking findings in one pass, with stable IDs, evidence, recommended fixes, and validation expectations. Consolidate routine corrections for each responsible worker; apply the direct-intervention rule to uncertain or recurring issues.
2. Have the worker address each finding and affected checks, or explain disagreement with evidence. The lead adjudicates disagreements and reviews the correction diff and newly affected contracts, reusing valid review and test evidence.
3. When a finding recurs or progress stalls, apply the lead-reasoning boundary above before dispatching more work. Preserve finding history across any worker replacement.

Package handbacks do not require a fresh full review each time. Start with the compact result, changed behavior, and exact evidence paths; inspect relevant diffs and machine-readable test results without reconstructing the worker's investigation. Review the integrated change once, then only corrections and newly affected contracts. Give each validation scope one owner: a passing worker run on the exact unchanged candidate can satisfy acceptance without a lead rerun. Rerun only for a changed candidate, missing evidence, or a specific uncovered risk. Independent verification means checking the evidence, not repeating the command by default.

## Accept and report

Accept when the complete outcome meets its criteria, findings are resolved, and required checks have valid evidence. Report the accepted ref, outcome, validation, material limitations, worker count, and correction batches, including required repository notices. If reporting native usage metrics, label resumed totals cumulative; do not add paid turns for telemetry or infer cost savings from token counts.
