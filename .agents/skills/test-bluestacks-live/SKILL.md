---
name: test-bluestacks-live
description: Run bounded live BlueStacks validation for PNC behavior that depends on ADB, emulator state, current UI, selectors, or navigation. Use for explicit live-test requests or when offline evidence cannot prove a changed live boundary.
---

# Test BlueStacks Live

Use live validation only when its fidelity is needed. Prefer deterministic offline tests and saved screenshots for behavior they can prove. Do not spend emulator time, host resources, or live actions on protection whose realistic likelihood-and-impact reduction is negligible.

## Safety

- Resolve the account, castle, display name, role, ADB path, and BlueStacks config through repository config and the canonical runtime. Do not hard-code ports or device IDs.
- Treat `accounts[].live_roles` as authority. A specific target castle named in the current request or plan being executed explicitly authorizes switching to that castle within the selected, role-authorized account and instance; do not ask for separate castle-switch confirmation. It does not authorize switching accounts or instances. If no castle is named, use the active castle on the configured `testing` instance and do not switch.
- Acquire the canonical process-scoped task lease before ADB access; it remains the default when nothing else is declared. Keep one task lease across dependent steps in a process and declare a multi-instance bundle up front. A separate process cannot inherit that lease; use an in-process entry point for a continuous phase or run sequential leased phases. If exclusive instance ownership must span those phases, declare the long reservation below; task leases alone leave a gap between processes.
- A prompt, plan, or series may declare a persistent agent-scoped long reservation over a configured instance or bundle. When one is declared, claim it through `py -m pnc_automation.bluestacks_management claim-reservation` (validating `--instance` names against the configured inventory), carry the issued receipt path (for example through `PNC_INSTANCE_RESERVATION_RECEIPT`) without ever printing or logging its contents, renew it on scope resumption and at meaningful work checkpoints, and release the entire declared scope only at terminal completion — never on per-process exit or per-task close. Before selecting an instance, check `reservation-status` and defer to an active foreign reservation; the registry rejects foreign admission regardless.
- Validate castle identity when first taking over an instance, after an authorized castle change, or after instance replacement. Reuse that proof across the batch while instance continuity is established. Observe the current screen and action preconditions before each relevant action; do not repeat a full castle workflow per check.
- The outer assignment owns cleanup. Preserve instances that were already running unless the task explicitly authorizes closing them. Cleanup releases every task lease; it releases a long reservation only when the task owns that reservation's terminal scope.
- Default to non-spending actions. If validation may spend resources, use [write-code-live](../write-code-live/SKILL.md) with the exact action, target, and budget.
- Do not modify local config merely to make a smoke test pass.

## Workflow

1. Run the smallest relevant offline group or affected selection. Do not run the full suite merely because a live test follows.
2. The coordinator writes a [live-test batch](references/live-test-batch.md) before execution: bind each case to its candidate, precondition, production action, observable result, dependencies, target, and authority. Read [failure reporting](references/failure-reporting.md) and declare the shared report repository root and unique run ID before target preflight. Accumulate related cases through a coherent development batch; checkpoint before dependent work relies on an unproven boundary or before promotion. Do not pause after each edit.
3. Group cases sharing a target and compatible candidate into one assignment. Use one scoped lease when checks run in the same process; otherwise run sequential leased phases. Acquire the runtime, establish instance and castle identity as required above, verify the initial screen, and capture a baseline. Sequence cases so setup is reused without hiding a feature-owned entry route.
4. Perform the smallest supported action or workflow for each case and capture its postcondition. If an unrelated popup interrupts a case, first use the canonical bounded recovery. If it fails, take a fresh screenshot and use an unambiguous on-screen dismissal control, including a manual tap on its visible X, under the same lease and authority. Reobserve the screen and resume affected checks once their preconditions hold. Do not guess a control, infer Android Back, dismiss a task-owned dialog, or perform an unauthorized mutation; stop only the affected action if no permitted dismissal can be established. Continue independent cases that remain safe and meaningful.
   For an unrelated castle-identity or BlueStacks instance-management interruption, the assigned tester or authorized worker inspects the canonical status and artifacts, makes the smallest bounded correction through existing identity or readiness entry points, and re-establishes identity and readiness before resuming. Host-management mutation still requires that subsystem to be in scope and must satisfy the role, idle-lease, and `read_only` boundaries below. Do not turn the live batch into an unrelated code fix or prolonged host investigation. If the precondition still cannot be established, keep dependent cases pending, assign the underlying defect separately, and continue independent checks.
5. On failure, inspect screenshots, OCR, observations, and logs under the configured artifact root. Classify the failed boundary as environment/lease, unrelated entry or popup, feature behavior, safety/authority, or inconclusive evidence. Publish every castle selection/identity, popup, or BlueStacks instance-management incident through [failure reporting](references/failure-reporting.md), including preflight and recovered failures; link its stable ID and report path in the batch. A failure before a feature's valid precondition does not prove that feature failed. A manual equivalent precondition may isolate the feature action when authorized, but it cannot prove an automated entry route that is part of the contract.
6. Change code or state only when evidence supports it. Repeat only affected checks after a relevant change or materially different diagnosis; add an offline regression for a reproducible defect when practical. Record required cases that could not run as pending, without treating them as passing.
7. End at a stable screen when the existing flow supports it, apply the outer assignment's cleanup decision, and record every lease release and per-case result in the batch document.

## Coordinator correction checkpoint

The coordinator may take one short correction cycle only for a named, high-impact critical-path blocker whose unresolved result prevents dependent acceptance or work from advancing, and only when one lead-owned feedback cycle is likely to reduce blocked time. Saved evidence must support one narrow, testable hypothesis and one small source correction. Routine feature checks and ordinary failed cases remain with the assigned live-test owner. This is an exception for a short feedback loop, not the default owner for delegated live execution. All of these conditions must hold:

- The current request or approved plan authorizes the lead to edit the affected source and perform the live action. Do not infer either authority from offline-test permission or from a Devin assignment.
- The failed boundary, affected production entry, and expected postcondition are clear from saved evidence. The correction does not require a second hypothesis, broad exploration, or an unrelated architecture change.
- The epic ledger and live-test batch name the blocker and the dependent plans or cases it holds up. If no downstream work is waiting, use the ordinary assigned live-test workflow.
- The checkpoint is non-spending. Resource-spending work follows `write-code-live` and its exact action, target, and budget requirements; it is not eligible for this fast path.
- Any Devin assignment that touched the source or target has returned a terminal handoff; verify its process and live resources are released before lead edits or ADB access. Do not compete with an active worker.
- The target, role, identity, report destination, and lease or reservation ownership are resolved under this skill's normal rules. Use a task-owned checkout and record the exact candidate SHA or direct-edit source fingerprint plus production import root.

Limit the checkpoint to 20 minutes of lead active effort, including evidence review, setup, one corrective candidate, one affected live-test batch, cleanup, and reporting. This is a pilot coordination budget, not a timeout for an in-flight UI action: do not interrupt an action unsafely or omit required cleanup. Do not restart the budget by renaming the attempt or creating another candidate.

Use this sequence: review the existing failure artifacts; state the one hypothesis and affected cases in the existing batch; make the supported correction and add a practical offline regression when appropriate; run the smallest relevant offline check; pin the candidate and import root; acquire the normal lease and recheck identity and action preconditions; run the affected cases once; then release resources and update the batch and epic ledger. Keep the lead responsible for acceptance.

Stop after a failed or inconclusive retest, when the time budget is reached, when a second hypothesis is needed, or whenever normal identity, lease, reservation, role, or mutation safeguards require stopping. Preserve evidence, keep unproven cases pending, and record the next owner and trigger. A later worker assignment must name the changed candidate, affected cases, retained proof, and unchanged or revised authority; it is not an automatic conversational retry. A passing action after manually establishing a precondition does not prove an automated entry route that the case is meant to cover. The checkpoint does not accept an epic or any cases it did not run.

Run multiple castles or instances only when the contract names them, configuration differs materially, or observed behavior is target-dependent.

## Smoke Commands

```powershell
$env:PNC_RUN_LIVE_SMOKE="1"; py -m unittest tests.test_live_account_navigation_smoke
$env:PNC_RUN_LIVE_CHAT_SMOKE="1"; py -m unittest tests.test_live_chat_workflow_smoke
$env:PNC_RUN_LIVE_DAILY_TASK_SMOKE="1"; py -m unittest tests.test_live_daily_task_smoke
$env:PNC_RUN_LIVE_HOME_CITY_MAP_SMOKE="1"; py -m unittest tests.test_live_home_city_map_smoke
$env:PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION="1"; py -m unittest tests.test_live_world_map_movement_calibration_smoke
```

Use selector or host-management commands only when that subsystem is in scope. Inspect the command's help, implementation, and focused tests rather than loading every operational case into the skill. Host mutation must honor current role authority, the idle lease, and the `read_only` boundary.

## Stop Conditions

Stop the affected live action when identity cannot be verified, the screen or selector is ambiguous, ADB cannot become responsive within its configured bound, the next action crosses an unauthorized mutation boundary, an active foreign long reservation covers the target, or the authorized budget is exhausted. A missing task lease stops all ADB access on that instance. Preserve the last useful artifact, continue other safe checks only when their preconditions can be established, and continue offline diagnosis when possible. Required live cases remain pending until proven; do not promote a material live boundary on an unrelated failure or a process exit alone.

## Report

Report the batch document, candidate, target, per-case outcomes, offline and live commands, incident IDs and published report paths (or publication gaps), relevant artifact paths, cleanup and lease release, and any material pending case. Reconcile incident publication before closing the reporting handoff; a passing feature case does not erase an interruption. A process exit alone is not proof of the UI postcondition.
