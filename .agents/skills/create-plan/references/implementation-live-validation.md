# Implementation Live-Validation Planning

Use this reference when a plan changes selectors, screen classification, navigation, ADB/emulator integration, authored live workflows, scheduling, or any action that mutates live game state.

## Slice Contract

Plan runtime work as small, independently promotable slices. Every slice must state:

1. the one behavior and canonical owner being changed;
2. the exact files or components expected to change;
3. deterministic offline coverage, including a saved-screen regression fixture when live evidence exposed the defect;
4. the smallest opt-in live smoke entry point that exercises the same production code path;
5. the verified account, castle, and BlueStacks display name for each planned target;
6. the typed precondition, action or mutation boundary, expected postcondition, and safe recovery path;
7. bounded retries and immediate stop conditions;
8. screenshot, observation/OCR, and log/run-summary artifacts to preserve; and
9. the promotion rule that keeps the slice out of unattended execution until validation passes.

Run focused offline tests first, then the full offline suite when the slice changes shared runtime behavior, then the live smoke. A live smoke must validate observations before and after the action; process exit code alone is insufficient. Convert a live-discovered failure into an offline regression test before retrying the live path when practical.

## Planned-Target Matrix

For every runtime-affecting slice, include every instance/castle named by the plan. Record exactly one result per target:

- `passed`: the applicable behavior and postcondition were observed through the canonical runtime;
- `applicability_skip`: the feature was unavailable or had no eligible action, and the smoke proved the typed, expected skip without mutation; or
- `blocked`: the environment, selector, unexpected screen, authorization boundary, or safety precondition prevented proof.

Do not use `not tested`, a blank cell, or one target as a proxy for another. A target-specific skip needs a concrete applicability predicate. A blocker needs the last observed state, artifact paths, and exact next command or evidence needed. If a feature is permanently out of scope for a target, encode that in typed configuration and test the skip path live once.

## Mutation Safety

Separate read-only navigation from the final state-changing action. Before mutation, freshly observe and re-resolve the selector or spatial target; never reuse coordinates from a stale screenshot. Geometry may determine click coordinates, while OCR or text may supply semantic validation, but semantic recognition must not silently become the coordinate source when the architecture forbids it.

Each mutating smoke performs the minimum action that proves the slice, verifies the resulting game state, and stops. It must name prohibited adjacent actions such as premium spending, bulk use, refreshes, extra battles, or additional marches. A failed or unknown postcondition stops that target rather than repeating the mutation blindly.

## Incremental Promotion

Treat the first live target as a canary, then run the same narrow smoke on the remaining planned targets. Preserve target-specific results instead of averaging them. Only add the slice to the composed unattended routine after all required matrix cells are `passed` or approved `applicability_skip` results.

For scheduler work, test the wrapper manually, then register the scheduled task disabled. Validate its principal/logon mode, local-time trigger, overlap policy, missed-run behavior, working directory, exit-code propagation, and artifact output before enabling it. Encode the requested policy explicitly: `StartWhenAvailable` controls catch-up, `WakeToRun` controls waking, and `MultipleInstancesPolicy` controls overlap.

## Primary Sources Behind This Contract

- Google SRE recommends small, self-contained releases, automated tests, canary exposure, and an explicit evaluation before broader rollout: <https://sre.google/workbook/canarying-releases/>.
- Android documents verifying the exact ADB target and capturing screenshots as device evidence: <https://developer.android.com/tools/adb>.
- Python `unittest` supports explicit conditional skips with reasons; use them for true applicability conditions, not untested behavior: <https://docs.python.org/3/library/unittest.html#skipping-tests-and-expected-failures>.
- Microsoft documents Task Scheduler logon types and task settings, including `StartWhenAvailable`, `WakeToRun`, and `MultipleInstances`: <https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-logontype>, <https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings>, and <https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-multipleinstances>.
