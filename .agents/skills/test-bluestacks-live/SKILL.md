---
name: test-bluestacks-live
description: Explore, checkpoint, or accept PNC behavior through BlueStacks when current UI, ADB, selectors, navigation, timing, or real transitions materially affect the work.
---

# Test BlueStacks Live

Use live evidence where its fidelity changes implementation or acceptance. Separate pre-implementation exploration, development checkpoints, and final acceptance; they do not share one universal smoke rule.

Read [references/live-phases.md](references/live-phases.md) to select and execute the phase. Read [references/failure-handling.md](references/failure-handling.md) only after a failure or when manual recovery may establish a feature precondition.

## Safety

- Resolve the account, castle, display name, role, ADB path, and BlueStacks config through repository config and the canonical runtime. Do not hard-code ports or device IDs.
- Treat `accounts[].live_roles` as authority. The `live_testing` role supplies standing authority for bounded agent-led exploration on that configured target; other roles authorize only their named modes. An explicit current-task instruction may narrow this authority. If no castle is named, use the active castle on the configured `testing` instance; never switch accounts or castles without explicit authorization.
- Acquire the canonical process-scoped lease before ADB access. Keep one reservation across dependent steps and declare a multi-instance bundle up front.
- The outer live phase owns cleanup. Preserve instances that were already running unless the task explicitly authorizes closing them.
- For any resource-consuming phase, follow [write-code-live](../write-code-live/SKILL.md). Its exploration mode permits non-premium, non-protected in-game resources without a numeric per-action budget and treats diamonds as non-premium; its strict mode governs canaries, unattended execution, protected or irreversible actions, and uncertain retries.
- Do not modify local config merely to make a smoke test pass.

## Workflow

1. Classify the phase and its questions or acceptance cases.
2. Run focused offline checks before validating modified code; discovery of not-yet-implemented behavior does not require tests for that future code.
3. Acquire one scoped runtime for the connected work, verify fresh identity and state, and capture a baseline.
4. Exercise the phase's related questions or distinct cases through production boundaries and capture observable results.
5. Preserve reusable evidence and add an offline regression for a reproducible defect when practical.
6. End at a stable screen when supported and apply the outer phase's cleanup decision.

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

Stop the affected action when identity cannot be verified, the next action would be blind or cross an unauthorized/protected boundary, ADB cannot recover within its configured bound, an acceptance limit is exhausted, or further attempts repeat unchanged evidence. Preserve the last useful artifact and continue independent safe work where possible.

## Report

State the phase, target, questions or use cases, commands, observed results, relevant artifacts, resource mode, cleanup decision, and material limitations. A process exit alone is not proof of the UI postcondition.
