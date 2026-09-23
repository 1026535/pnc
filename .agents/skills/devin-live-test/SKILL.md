---
name: devin-live-test
description: Delegate a bounded PNC BlueStacks live-test assignment to a local Devin SWE-2 Max worker that executes the authorized checks and returns one curated evidence package. Use only when the user explicitly requests live testing through Devin or an approved plan assigns that live validation to Devin.
---

# Devin Live Test

Hand Devin one complete live-testing assignment, then collect one packaged result after its authorized checks finish. The Codex lead defines what must be proven, the live authority, and the acceptance boundary; Devin owns test selection, execution, routine diagnosis, evidence curation, and the compact handback within that boundary. This skill reuses the `devin-implement` transport rather than creating another launcher or monitoring system.

**Worker role guard:** If `DEVIN_IMPLEMENT_ROLE` is set or this session is the assigned worker, execute the brief without launching another worker or applying this orchestration workflow.

## Authority and ownership

- Invocation or an approved plan must authorize live testing through Devin. Discovery of this skill, a code change that might benefit from live testing, or offline-test permission alone is insufficient.
- Follow [test-bluestacks-live](../test-bluestacks-live/SKILL.md) as the canonical live policy. Resolve targets through repository configuration, treat `accounts[].live_roles` and the canonical lease as authority, verify fresh identity and screen state, and preserve pre-existing instances.
- Delegate actions permitted by the resolved live role and lease. If an action may spend resources, the request or approved plan must provide the exact action, target, and budget required by [write-code-live](../write-code-live/SKILL.md); include those limits in the brief and let Devin execute only within them.
- Use one worker and one declared instance bundle. Before launch, confirm the lead and other workers do not hold or use the target instance; consult `py -m pnc_automation.bluestacks_management reservation-status` when a long reservation may exist. Prefer one in-process task lease across dependent checks. If existing checks require separate processes, run sequential leased phases; never hold a parent task lease while a child process needs to acquire it. Release every task lease during cleanup.
- A prompt, plan, or series may also declare a persistent agent-scoped long reservation over the task leases. When one applies, the brief must carry the issued receipt to Devin through a secure transport without exposing its contents in the brief text, name the renewal checkpoints, and state whether this assignment owns the reservation's terminal release. A reservation inherited from a broader plan or series remains held for its owner; Devin releases it only when the assignment owns the terminal semantic scope.
- The assignment owns live validation only. Devin may inspect code and artifacts and run existing checks, but must not edit source, tests, fixtures, configuration, plans, tracked documentation, or Git state; install dependencies; commit; or open a pull request. Preserve the starting source tree exactly. Ignored runtime evidence, the required shared incident reports, and the result package are permitted outputs.
- Do not place credentials, tokens, ignored configuration values, or account secrets in the brief, manifest, or handback. Let the canonical runtime resolve authorized local configuration.

## Define one complete assignment

Give Devin outcomes and boundaries rather than a step-by-step test script:

1. Prepare the coordinator's [live-test batch](../test-bluestacks-live/references/live-test-batch.md) before launch. Read [failure reporting](../test-bluestacks-live/references/failure-reporting.md); supply the absolute shared report repository root, unique run ID, and coordinating owner before target preflight. Name every live boundary, its production entry and observable postcondition, and dependencies between cases. Group compatible checks on the same target into one assignment, using one in-process task lease where supported or sequential leased phases where separate processes are necessary. Declare a long reservation when the batch requires exclusive ownership between those phases.
2. Identify the authorized account/castle or apply the canonical default: the active castle on the configured `testing` instance. Declare any multi-instance bundle, allowed live roles, switching authority, spending action and budget, and cleanup policy up front.
3. Bind cases to one clean integration commit containing the bundle to test. Provide its SHA, worktree, included commits, known passing offline evidence, prohibited actions, stable ending screen, and stop conditions. Resolve every material choice that could require user input before launch.
4. Let Devin choose the smallest existing live tests, application entry points, or authored workflows that prove the assignment. It may run the smallest missing offline preflight and sequence dependent checks without returning for routine choices.
5. Set attempt limits only where risk or an external budget requires them. Otherwise apply the canonical rule: repeat a live action only after a relevant implementation or state change produces a materially different diagnosis.

Write the assignment with [live-test-brief.md](references/live-test-brief.md). Missing live authority, an ambiguous mutation boundary, or an unspecified required spending budget blocks launch; ordinary execution choices do not.

## Launch once and wait

Read the existing [runtime](../devin-implement/references/runtime.md) and [keepalive](../devin-implement/references/keepalive.md) references before launch. Use `devin-implement/scripts/devin_worker.py` with `--preamble-file .agents/skills/devin-live-test/references/worker-preamble.md` so the assignment inherits the verified `swe-2-max` session, process supervision, completion delivery, and monitor without the implementation worker's `NEEDS_LEAD` contract.

Use a fresh ignored run directory under `.local-data/devin-live-test/runs/<assignment>` and keep the brief under `.local-data/devin-live-test/briefs/`. Launch from the exact clean target Git root with its verified HEAD. Have Devin verify the same SHA, clean tree, and production import root before execution and handback; the launcher's HEAD check alone does not bind uncommitted source. Show Devin's live-output console unless the user explicitly requests no console. Use the launcher's existing permission mode; game and resource authority comes from the brief, configured live role, and canonical lease.

Register the run with the single lead monitor under `.local-data/devin-monitor`, then yield. Do not request per-check progress, poll the emulator, ask Devin to narrate intermediate results, or duplicate its observations. Use `status` only when the user asks for progress or the monitor reports an actionable transport anomaly. Do not use side questions to supervise test decisions.

## Devin execution contract

The brief must tell Devin to read `AGENTS.md` and [pnc-live-testing](../pnc-live-testing/SKILL.md), including its canonical live policy and failure-reporting reference, before target preflight or ADB access. Devin should:

- select and run all checks needed for the assignment, preferring supported repository entry points over raw ADB commands;
- retain one task lease for checks in the same process, or acquire and release each sequential process's own task lease; avoid repeated setup or identity discovery while instance continuity holds;
- perform routine bounded recovery — for unrelated popups, the [popup recovery playbook](references/popup-recovery.md) — and inspect screenshots, OCR, observations, and logs when a check fails;
- classify the observed stopping boundary and keep a feature case pending when an unrelated precondition prevented its execution;
- publish each required incident at the first safe checkpoint and link it from the manifest, including preflight and recovered failures;
- continue to remaining safe checks when one check fails, recording dependencies that make another check unsafe or meaningless;
- make ordinary test-selection, sequencing, evidence, and diagnostic decisions itself instead of returning them to the lead; and
- end on the requested stable screen, apply the cleanup policy, release every task lease, preserve any instance that was already running, and release a declared long reservation only when the assignment owns its terminal semantic scope.

Devin must not return `NEEDS_LEAD`, ask routine questions, or stop merely because a check failed or evidence is incomplete. It completes every safe authorized check and packages failed, blocked, or not-run results. It may return `BLOCKED` only when progress requires concrete user intervention, such as new authorization, credentials, an account action, a target choice unavailable from configuration, or a resource-budget decision. Consolidate every known required user action into that one terminal handoff instead of revealing blockers serially. Transport or tool failure without a user remedy is `FAILED`, not a blocker.

A process or test exit code alone is not proof. Before handback, Devin must verify assignment coverage and curate the proof into `evidence.json` in `DEVIN_IMPLEMENT_TURN_DIR`. Raw screenshots, traces, OCR, observations, and workflow results remain under the canonical configured artifact root. The manifest references only the smallest sufficient set, explains what each artifact establishes, and records incomplete or failed checks explicitly; it does not copy raw evidence into the Devin run directory.

## Collect the packaged result

The terminal handback consists of the normal supervisor result, a compact `handoff.md`, and the curated `evidence.json`; required incident reports are already published in the shared collections and linked from that manifest. The handoff states the overall status and manifest path plus the consolidated required user actions when blocked; it does not repeat per-check evidence already present in the manifest.

Read the handoff and manifest, then reconcile each assigned case with the coordinator's batch record. Do not recursively scan `.local-data/devin-live-test/`, the canonical artifact tree, full logs, or the Devin conversation. Open only a manifest-cited artifact when independent acceptance requires visual confirmation or when the package is internally inconsistent. Do not rerun passing checks or reconstruct Devin's investigation.

Accept `READY_FOR_REVIEW` only when the manifest covers every assigned check, identifies the clean tested candidate and import root, cited paths exist, every required interruption has a published incident report, authority and budget stayed within bounds, cleanup and every lease release are recorded, and no material contradiction remains. The coordinator verifies publication and publishes pending local reports; shared indexes belong to the collection owner or weekly reporting job. After a missing handoff or crash, use the failure-reporting contract to retain supported incidents and coverage gaps from known saved evidence without live reproduction. A `BLOCKED` result goes to the user with the exact intervention Devin identified; resume the same session only after that intervention. A `FAILED` result remains a completed package for lead review and does not trigger a conversational retry loop.

After a terminal handoff, the lead reviews the saved evidence and may perform the coordinator correction checkpoint defined by `test-bluestacks-live` only when lead source edits and live execution are authorized and all Devin processes and live resources are released. Otherwise, leave affected checks pending and either wait for the stated intervention or issue a concrete delta assignment. A delta brief names the lead-resolved defect, exact changed candidate and import root, affected cases, retained passing proof, unchanged or revised authority and budget, and next stop condition. Devin remains source-read-only. Never turn a failed package into an automatic retry or treat a checkpoint as acceptance of untested cases.

Report the overall outcome, target and live role, manifest path, authorized and actual spending, cleanup, lease release, user intervention if blocked, and material remaining uncertainty. Do not enumerate raw artifacts or claim usage savings without measured account-level evidence.
