# Step 2: Puzzles & Conquest Automation Sub-Plan

## 1. Purpose

This document is the dependency-ordered second plan and covers automation orchestration design.

The automation framework described here is already implemented in code. This document now serves as a fixed reference for later sub-plans instead of a remaining implementation to-do.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which covers account-specific bootstrap and castle-targeting behavior,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which covers concrete task behavior,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which covers reusable navigation flows.

This file owns only automation orchestration concepts.

## 2. Scope

This sub-plan should define:

- the canonical execution loop,
- script loading and script-step execution,
- the generic task contract,
- runner and verifier responsibilities,
- retry and stop policies,
- sequencing rules between tasks, task sub-plans, and screen flows.

## 3. Automation ownership

Automation should own:

- loading a selected run script,
- resolving steps to registered tasks,
- validating step parameters,
- executing tasks in script order,
- invoking reusable screen flows when tasks require them,
- verifying task outcomes,
- deciding whether the run continues, retries, or stops.

Automation should not own:

- raw ADB command execution,
- screenshot capture,
- low-level image interpretation,
- game-specific selector definition,
- reusable screen-flow definitions,
- concrete task internals.

## 4. Canonical execution loop

For each requested run:

1. Load the selected account config and selected run script.
2. Open or connect to the correct BlueStacks ADB endpoint.
3. Ensure the Android device is responsive.
4. Ensure Puzzles & Conquest is running or foregrounded.
5. Capture an observation.
6. Execute the next script step when its task is applicable.
7. Re-capture observation.
8. Verify the state transition.
9. Persist logs and screenshots.
10. Continue until the script completes or a fail-fast condition stops the run.

Single-account sequential execution should be the only initial mode. Do not add concurrency until selectors, navigation, and recovery are stable.

## 5. Generic task contract

Every task should implement the same contract:

```python
class AutomationTask(Protocol):
    id: TaskId

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool: ...
    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]: ...
    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult: ...
```

This is the canonical extension model.

Rules:

- `is_applicable` prevents invalid task execution.
- `plan` emits declarative actions and never calls ADB directly.
- `verify` confirms state change from fresh observation.
- task-specific parameters come from the current script step, not from account config.

## 6. Script runner

The script runner should be intentionally simple:

1. read steps from the selected script in order,
2. resolve each step to a registered task,
3. validate the step parameters,
4. execute the task when its preconditions are satisfied,
5. stop on fail-fast errors or continue to the next step after verified success.

Step ordering belongs to the run script, and script parsing belongs to `automation`, not to account config and not to each task implementation.

## 7. Generic task categories

At this stage, automation should reason about generic task categories, not final screen-specific flows:

- game bootstrap task,
- popup recovery task,
- login task,
- castle selection task,
- city-management task,
- world-map task,
- campaign task.

Concrete behavior for `game bootstrap task`, `popup recovery task`, `login task`, and `castle selection task` belongs in [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md).

Concrete behavior for the remaining task categories belongs in [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md).

## 8. Module boundaries

Automation consumes:

- typed account config,
- typed run script,
- typed observations from `pnc`,
- reusable navigation flows from [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md),
- account-navigation task definitions from [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md),
- concrete post-navigation task definitions from [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md).

Automation produces:

- task execution decisions,
- action execution requests,
- retry or stop decisions,
- run-level results and status transitions.

## 9. Failure and stop policy

Automation should centralize:

- fail-fast stop conditions,
- allowed retry counts,
- whether a task failure aborts the run,
- whether popup recovery may be attempted before failing,
- whether verification mismatch is retryable.

The first version should stay conservative:

- fail fast on unknown screens,
- allow only small, explicit retry rules,
- stop the run when verification cannot confirm expected state.

## 10. Validation ownership

Automation must enforce the rule that work is not complete without validation evidence.

At the automation layer, this means:

- runner and script-loader changes require unit tests,
- task-contract changes require unit tests,
- retry and stop-policy changes require unit tests,
- any orchestration change that affects live execution order must also be checked with a targeted smoke run.

Automation should also define what evidence is recorded when a task verification fails so the validation result is inspectable.

## 11. Relationship to other plans

This file must not duplicate:

- concrete selectors from [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md),
- account-navigation task behavior from [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md),
- reusable screen flows from [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md),
- concrete post-navigation task internals from [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md).

It is the canonical place for automation orchestration only.
