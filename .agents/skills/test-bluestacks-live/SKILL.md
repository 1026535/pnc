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
12. For multi-step Python live workflows, use one `with api.use_account(...)` or `with api.reserve_accounts((...))` scope for the complete sequence. Do not make separate one-shot calls for dependent steps, because another process may acquire the instance after an isolated call releases its lease. The active scope rejects accounts that were not declared in its bundle.
13. Keep the configured BlueStacks working-set monitor running as a supervised host task. Watch mode continues monitoring other instances after a per-instance recovery failure and persists structured evidence; one-shot and fatal host/configuration errors are nonzero. Emit failures through the bounded rotating state log without raw secrets.
14. The separately scheduled 01:55 America/Toronto fleet-maintenance boundary snapshots configured instances that are open, acquires their complete bundle, and restarts only that snapshot. It must not launch instances that were closed; use `restart-open --require-maintenance-window --include-read-only` for that explicit boundary.
15. Choose the BlueStacks session cleanup policy at the outer live-testing phase boundary. Use `BlueStacksSessionCleanupPolicy.keep_warm()` for short probes or when another live operation will follow. Use `BlueStacksSessionCleanupPolicy.close_at_phase_end()` for instances launched by the phase; pass `close_preexisting_instance=True` only when the agent explicitly decides that the selected managed target should close even though it was already open. A shutdown request is deferred until the last same-process lease reference is released. The default two-minute quiescence window then runs without holding the old lease, so newly queued work can claim the instance and cancel or replace the pending shutdown. Cancellation is observed within a short polling interval rather than making the completed task wait for the full window. Cleanup must re-acquire the lease and revalidate the exact intent, instance key, and PID before stopping anything.

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
5. Keep one connected runtime and its lease across dependent operations in the same live-testing phase. Pass the chosen cleanup policy when building the runtime or calling `ApplicationRunner.run`; do not close and reopen between short substeps merely to perform cleanup.
6. Use observation-based waits and bounded retries. Avoid blind sleeps except for short, justified settle windows already modeled by the runner.
7. On failure, inspect generated screenshots, OCR JSON, logs, and observation artifacts under `artifacts/` before changing code.
8. Preserve evidence paths in the final report, including the live flag, account, smoke module/tool, cleanup decision, and artifact labels.

For example, an agent-controlled phase can select the policy explicitly:

```python
from pnc_automation.core.infra.emulator.session import BlueStacksSessionCleanupPolicy

cleanup_policy = (
    BlueStacksSessionCleanupPolicy.close_at_phase_end(
        close_preexisting_instance=True,
    )
    if live_phase_is_complete_and_long
    else BlueStacksSessionCleanupPolicy.keep_warm()
)
runtime = script_runner.build_connected_runtime(
    account=account,
    required_role=LiveAutomationRole.SMOKE_TEST,
    session_cleanup_policy=cleanup_policy,
)
```

For the recommended multi-call Python API, put the policy on the outer scope so
preparation and every dependent task inherit one decision:

```python
with api.use_account(
    "testing",
    session_cleanup_policy=cleanup_policy,
) as session:
    session.collect_kingdom_chat()
    session.open_building(building="farm")
```

The expression `live_phase_is_complete_and_long` is an agent/task decision, not a
timer or an emulator heuristic. The safe default preserves an instance that was
already open before the phase. Use `close_preexisting_instance=True` only when
that managed target should be reclaimed after the phase; never infer this for a
manually used or read-only instance.

The shared smoke helpers also accept the agent-selected environment value
`PNC_LIVE_SESSION_CLEANUP=keep_warm` (the default) or
`PNC_LIVE_SESSION_CLEANUP=close_at_phase_end`. The latter is an explicit decision
to close the selected managed smoke target, including when it was already open.
Set it on the command that owns the complete outer reservation for a longer
live-testing phase, never on an unreserved intermediate command.

Phase-end intent is persisted with the exact instance key and PID before live
work starts. The supervised `pnc_automation.bluestacks_management monitor`
reconciles an intent left by an abruptly terminated agent only after acquiring
the now-idle lease. It starts the same quiescence window when the crashed owner
could not do so, then reloads role authority and rejects changed identities.
Never implement the grace period by sleeping while retaining the prior lease;
that would prevent the follow-up task the window is intended to detect.

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
