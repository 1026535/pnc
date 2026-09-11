---
name: test-bluestacks-live
description: Validate PNC automation against a live BlueStacks instance through opt-in smoke tests, ADB connectivity checks, screenshots, observations, and generated artifacts. Use when the user asks Codex to run or design BlueStacks live tests, verify emulator behavior, inspect ADB/runtime issues, validate selectors or navigation on a real emulator, run live smoke flags, or diagnose live PNC automation failures.
---

# Test BlueStacks Live

## Overview

Run live emulator validation only when the fidelity is worth the cost. Use offline tests and deterministic screenshots first, then opt into BlueStacks smoke tests to prove behavior that depends on ADB, emulator state, live PNC UI timing, or real navigation.

## Safety And Preconditions

1. Confirm the requested account, castle, and BlueStacks display name exist in `config/`.
2. Let the canonical runtime launch the configured BlueStacks instance when it is not running.
3. Confirm ADB is enabled in BlueStacks and reachable through the resolved local endpoint after startup.
4. Use the repo's configured `adb_path` and `bluestacks_config_path`; do not hard-code ADB ports or device IDs.
5. Keep ADB local. Treat exposed ADB ports as sensitive because unauthenticated ADB access can control the emulator.
6. Never overwrite real local config unless the user explicitly asks.
7. Treat castle inventory and live execution eligibility as separate concerns. Keep every configured account's castle roster current even when that account is excluded from testing.
8. Treat `accounts[].live_roles` as the live authority and validate the requested role before constructing a runtime. Account/display assignments such as `testing`/`smoke_test`, `serious_stuff`/`live_testing`, `mega_old_acc`/`daily_canary`, and `main`/`read_only` are current examples and may be reassigned; do not hard-code them as permanent workflow ownership.
9. The host-management CLI loads only host bindings, roles, metadata, and memory policy, so it must not require credentials or castle files. It rereads valid host authority every monitor sample and again under the instance lease before destructive mutation. Durable recovery intent and cooldown survive process restarts; bound recovery to 3 launch attempts per pass and 9 persisted attempts total, and block pending launches after role or identity revocation.
10. Do not bypass an instance-busy error. The process-scoped instance lease is the canonical ownership gate. Hold it across preparation, dependent work, and cleanup. Wait through its bounded acquisition policy; if the bound expires, choose another role-eligible instance or report the owner.
11. A process that needs several instances must declare and acquire the complete instance bundle before touching any of them. Never acquire additional instances incrementally while retaining earlier leases.
12. Keep the configured BlueStacks working-set monitor running as a supervised host task. Watch mode continues monitoring other instances after a per-instance recovery failure and persists structured evidence; one-shot and fatal host/configuration errors are nonzero. Emit failures through the bounded rotating state log without raw secrets.
13. The separately scheduled 01:55 America/Toronto fleet-maintenance boundary snapshots configured instances that are open, acquires their complete bundle, and restarts only that snapshot. It must not launch instances that were closed; use `restart-open --require-maintenance-window --include-read-only` for that explicit boundary.

## Workflow

1. Start with offline validation. Run the relevant unit tests and saved-screenshot tests before live smoke tests.
2. Select the smallest live smoke that proves the risky boundary:
   - `PNC_RUN_LIVE_SMOKE=1` for shared account navigation and spatial-surface smoke tests.
   - `PNC_RUN_LIVE_CHAT_SMOKE=1` for chat workflow validation.
   - `PNC_RUN_LIVE_DAILY_TASK_SMOKE=1` for daily-task workflow validation.
   - `PNC_RUN_LIVE_HOME_CITY_MAP_SMOKE=1` for home-city atlas/building navigation.
   - `PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION=1` for movement calibration.
3. Acceptance smoke suites must use a configured account carrying the requested `smoke_test` role (currently `testing`) and whichever castle is currently active when no castle target is specified. General live investigations may use an account carrying `live_testing`, but must not silently substitute one into a smoke acceptance matrix. Verify the active identity and do not select or switch castles unless the user explicitly names and authorizes one.
4. Run through the existing live helpers and smoke modules. Reuse `ScriptRunner`, `BlueStacksInstanceResolver`, `BlueStacksSession`, observation services, selector tools, and artifacts.
5. Use observation-based waits and bounded retries. Avoid blind sleeps except for short, justified settle windows already modeled by the runner.
6. On failure, inspect generated screenshots, OCR JSON, logs, and observation artifacts under `artifacts/` before changing code.
7. Preserve evidence paths in the final report, including the live flag, account, smoke module/tool, and artifact labels.

## Reliability Rules

- Treat live tests as high-fidelity but less deterministic than offline tests.
- Keep each smoke test narrow, bounded, and reversible.
- Validate the pre-run and post-run observations so the smoke proves state transition, not just command success.
- Prefer stable selectors, accessibility/text anchors, and existing registry entries over screen coordinates. Use coordinates only through existing spatial/navigation abstractions.
- Record enough artifacts to reproduce the failure locally or add a deterministic regression fixture later.
- Convert live-discovered bugs into offline regression tests when practical.

## Common Commands

Use commands that match the target smoke:

```powershell
$env:PNC_RUN_LIVE_SMOKE="1"; py -m unittest tests.test_live_account_navigation_smoke
$env:PNC_RUN_LIVE_CHAT_SMOKE="1"; py -m unittest tests.test_live_chat_workflow_smoke
$env:PNC_RUN_LIVE_DAILY_TASK_SMOKE="1"; py -m unittest tests.test_live_daily_task_smoke
$env:PNC_RUN_LIVE_HOME_CITY_MAP_SMOKE="1"; py -m unittest tests.test_live_home_city_map_smoke
$env:PNC_RUN_LIVE_WORLD_MAP_MOVEMENT_CALIBRATION="1"; py -m unittest tests.test_live_world_map_movement_calibration_smoke
```

For selector and navigation investigations, consider:

```powershell
py tools/validate_navigation_selectors.py
py tools/update_selector_registry.py
py tools/discover_selector_registry.py
py tools/run_world_map_movement_calibration.py
py -m pnc_automation.bluestacks_management monitor --watch
py -m pnc_automation.bluestacks_management restart-open --require-maintenance-window --include-read-only
```

## Quality Gate

Before finishing, report:

- Live preconditions checked.
- Whether the configured BlueStacks instance was already running or launched by the runtime.
- Offline tests run before live testing.
- Exact live command, environment flag, account, and smoke target.
- Artifact paths inspected or generated.
- Whether failures were product issues, test flakiness, environment issues, or expected skips.
- Follow-up regression test or fixture plan for any live bug discovered.
