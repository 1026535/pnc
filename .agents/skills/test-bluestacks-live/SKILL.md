---
name: test-bluestacks-live
description: Run bounded live BlueStacks validation for PNC behavior that depends on ADB, emulator state, current UI, selectors, or navigation. Use for explicit live-test requests or when offline evidence cannot prove a changed live boundary.
---

# Test BlueStacks Live

Use live validation only when its fidelity is needed. Prefer deterministic offline tests and saved screenshots for behavior they can prove. Do not spend emulator time, host resources, or live actions on protection whose realistic likelihood-and-impact reduction is negligible.

## Safety

- Resolve the account, castle, display name, role, ADB path, and BlueStacks config through repository config and the canonical runtime. Do not hard-code ports or device IDs.
- Treat `accounts[].live_roles` as authority. If no castle is named, use the active castle on the configured `testing` instance; never switch accounts or castles without explicit authorization.
- Acquire the canonical process-scoped lease before ADB access. Keep one reservation across dependent steps and declare a multi-instance bundle up front.
- The outer live phase owns cleanup. Preserve instances that were already running unless the task explicitly authorizes closing them.
- Default to non-spending actions. If validation may spend resources, use [write-code-live](../write-code-live/SKILL.md) with the exact action, target, and budget.
- Do not modify local config merely to make a smoke test pass.

## Workflow

1. For implementation work, complete a larger, coherent slice before applying [AGENTS.md](../../AGENTS.md)'s Offline Validation policy; for standalone live validation, apply it to the existing scope. Do not run the full suite merely because a live test follows.
2. Choose one smoke path that exercises the changed boundary.
3. Acquire the scoped runtime, verify fresh identity and screen state, and capture a baseline.
4. Perform one bounded action or workflow and capture the observable postcondition.
5. On failure, inspect screenshots, OCR, observations, and logs under `.local-data/artifacts/`. Change code or state only when the evidence supports it, then rerun the same proof.
6. Stop repeated attempts that produce the same evidence without a new diagnosis. Add an offline regression for a reproducible live defect when practical.
7. End at a stable screen when the existing flow supports it and apply the outer phase's cleanup decision.

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

Stop the affected live action when identity cannot be verified, the screen or selector is ambiguous, ADB cannot become responsive within its configured bound, the next action crosses an unauthorized mutation boundary, or the authorized budget is exhausted. Preserve the last useful artifact and continue safe offline diagnosis when possible.

## Report

State the target, offline and live commands, observed result, relevant artifact paths, cleanup decision, and any material blocker. A process exit alone is not proof of the UI postcondition.
