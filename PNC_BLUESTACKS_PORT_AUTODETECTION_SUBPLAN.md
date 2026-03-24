# PNC BlueStacks Port Autodetection Sub-Plan

## 1. Purpose

This document defines the bounded refactor that removes dynamic BlueStacks ADB ports from authored repo configuration and resolves the live endpoint at runtime from authoritative BlueStacks host metadata.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md), which owns login and castle-targeting behavior after a session exists,
- [PNC_KINGDOM_CHAT_MONITOR_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_KINGDOM_CHAT_MONITOR_IMPLEMENTATION.md), which owns the Kingdom Chat monitor itself.

This file owns one architectural correction:

- authored instance config must identify one BlueStacks instance by a stable BlueStacks identity,
- runtime must resolve that instance's current ADB port automatically,
- session startup must fail fast when the live BlueStacks metadata is missing, ambiguous, or inconsistent.

## 1.1 Implementation status

Status:

- completed in repo on 2026-03-24,
- authored instance config now uses stable `display_name` values plus `defaults.bluestacks_config_path`,
- runtime resolves the live `device_id` from BlueStacks host metadata before building a session,
- automated coverage now validates config migration, resolver failure modes, successful port resolution, and ScriptRunner session wiring,
- 2026-03-24 review follow-up closed the stale/shared-port runtime correctness gap, consolidated live runtime construction behind one public `ScriptRunner` boundary, and added top-level application wiring coverage for the resolver path,
- 2026-03-24 live connection checks resolved `serious_stuff -> 127.0.0.1:5555` and `testing -> 127.0.0.1:5566` through the canonical runtime path.

## 1.2 Triggering live evidence

On 2026-03-24, live validation of the Kingdom Chat monitor against `serious_stuff` exposed that the current config boundary is wrong:

- [config/accounts.yaml](/c:/Users/lebel/pnc/config/accounts.yaml) still mapped `bs-main` to `127.0.0.1:5556`,
- the running BlueStacks window titled `serious_stuff` was actually listening on `127.0.0.1:5555`,
- `C:\ProgramData\BlueStacks_nxt\bluestacks.conf` reported that same live instance under `display_name="serious_stuff"` with `status.adb_port="5555"`,
- `testing` remained on `5566`, confirming the ports were assigned by the live BlueStacks launch state rather than by the repo config.

The live run only proceeded after a throwaway config override changed the stale port manually. That is exactly the workflow we want to eliminate.

## 2. Current problem

Today [pnc_automation/config/models.py](/c:/Users/lebel/pnc/pnc_automation/config/models.py) and [pnc_automation/config/loader.py](/c:/Users/lebel/pnc/pnc_automation/config/loader.py) treat `instances[].device_id` as stable authored configuration.

That is the wrong ownership boundary for BlueStacks because:

- the user selects or launches BlueStacks instances by instance name, not by ephemeral ADB socket,
- BlueStacks can assign a different local ADB port on a later launch,
- the repo config therefore goes stale even though nothing meaningful changed about the intended emulator target,
- the stale port failure happens before any real automation logic can even begin.

This creates concrete runtime problems:

- live smoke and operator runs can fail on connect before task logic starts,
- correct runs require temporary config rewrites,
- the config file pretends to own data that BlueStacks itself already owns authoritatively,
- one bad stale port can make the wrong problem look like an automation bug.

## 3. Goals

- Keep one canonical implementation for BlueStacks endpoint resolution.
- Stop storing dynamic ADB ports in authored repo config.
- Resolve the current BlueStacks ADB endpoint automatically at runtime.
- Use a stable, operator-facing BlueStacks identity in config.
- Fail fast when the requested instance cannot be resolved exactly.
- Keep local tests deterministic by allowing the discovery source to be fixture-driven.
- Preserve the existing downstream `BlueStacksSession` and `AdbClient` contracts once a runtime `device_id` has been resolved.

## 4. Non-goals

- Supporting emulator vendors other than BlueStacks.
- Guessing across arbitrary attached Android devices.
- Keeping two permanent authored identity systems for the same BlueStacks instance.
- Silently falling back to a random listening port when discovery fails.
- Hiding host-side BlueStacks failures behind retry loops.

## 5. Core architectural decision

The config must identify a BlueStacks instance by stable BlueStacks identity, and the runtime must derive the current `device_id`.

Recommended canonical model:

1. `BlueStacksInstanceConfig` should stop storing `device_id`.
2. It should instead store the BlueStacks instance `display_name` used by Multi Instance Manager and the live window title, for example `serious_stuff` or `testing`.
3. One new BlueStacks runtime-discovery component should read the authoritative host metadata file and resolve that `display_name` to the current `status.adb_port`.
4. The runtime should then materialize the actual endpoint as `127.0.0.1:<resolved_port>` and pass that into the existing session layer.

Why `display_name` is the right authored key:

- it is what the operator already reasons about,
- it matched the live March 24, 2026 session titles directly,
- it avoids leaking BlueStacks' install-local engine keys such as `Nougat32` into authored automation config.

The resolved runtime `device_id` should still exist on [pnc_automation/emulator/bluestacks_instance.py](/c:/Users/lebel/pnc/pnc_automation/emulator/bluestacks_instance.py), but it should be derived output, not authored input.

## 6. YAML and model contract

### 6.1 Authored config

The authored `instances:` contract should move toward a stable identity like:

```yaml
defaults:
  adb_path: C:\Program Files\BlueStacks_nxt\HD-Adb.exe
  bluestacks_config_path: C:\ProgramData\BlueStacks_nxt\bluestacks.conf

instances:
  - id: bs-main
    display_name: serious_stuff
    app_package: com.global.tmslg
  - id: bs-main-1
    display_name: testing
    app_package: com.global.tmslg
```

### 6.2 Discovery source

The canonical runtime discovery source should be BlueStacks' own host metadata file, not `adb devices`.

`adb devices` is useful for readiness checks, but it is the wrong place to infer which socket belongs to which named BlueStacks instance. The discovery step should instead:

- parse the BlueStacks metadata file once,
- find the exact instance whose `display_name` matches the configured one,
- read that record's runtime `status.adb_port`,
- build the final `device_id` from that resolved port.

### 6.3 Fail-fast rules

The resolver must raise clear errors when:

- the BlueStacks config file does not exist,
- the requested `display_name` does not exist,
- multiple instance records expose the same `display_name`,
- the matching record lacks a usable runtime port,
- the resolved endpoint still cannot be connected through ADB.

## 7. Work plan

### 7.1 Config-model refactor

- Replace authored `device_id` with `display_name` in the BlueStacks instance config model.
- Add one canonical host-config path setting, likely `defaults.bluestacks_config_path`, so tests can point discovery at fixture data.
- Reject the old `device_id` field once the migration is complete instead of supporting both schemas in parallel.

### 7.2 Runtime discovery service

- Add one BlueStacks metadata parser/locator that reads the host config file and produces typed runtime records.
- Resolve the configured `display_name` to exactly one runtime port.
- Materialize the runtime `device_id` only after the match is proven.
- Keep this logic out of `ScriptRunner` and out of task code; it belongs in the BlueStacks integration layer.

### 7.3 Wiring changes

- Update [pnc_automation/automation/script_runner.py](/c:/Users/lebel/pnc/pnc_automation/automation/script_runner.py) so it asks the new resolver for the current runtime endpoint before constructing [pnc_automation/emulator/session.py](/c:/Users/lebel/pnc/pnc_automation/emulator/session.py).
- Preserve the current `AdbClient` and `BlueStacksSession` APIs after resolution so the rest of the runtime stays unchanged.
- Log the resolved `display_name -> device_id` mapping once per run for diagnosability.

### 7.4 Validation

- Add config-loader tests for the new authored schema and the removal of the stale `device_id` contract.
- Add resolver tests for missing files, duplicate names, missing ports, and successful resolution.
- Add session-wiring tests that prove the runtime connects through the resolved port instead of the authored config.
- Re-run at least one live connection path on both `serious_stuff` and `testing` after restarting BlueStacks instances so the ports genuinely have a chance to move.

## 8. Expected implementation files

The likely implementation surface is:

- [config/accounts.yaml](/c:/Users/lebel/pnc/config/accounts.yaml)
- [config/accounts.example.yaml](/c:/Users/lebel/pnc/config/accounts.example.yaml)
- [pnc_automation/config/models.py](/c:/Users/lebel/pnc/pnc_automation/config/models.py)
- [pnc_automation/config/loader.py](/c:/Users/lebel/pnc/pnc_automation/config/loader.py)
- [pnc_automation/config/validation.py](/c:/Users/lebel/pnc/pnc_automation/config/validation.py)
- [pnc_automation/emulator/bluestacks_instance.py](/c:/Users/lebel/pnc/pnc_automation/emulator/bluestacks_instance.py)
- one new BlueStacks runtime-discovery module under [pnc_automation/emulator](/c:/Users/lebel/pnc/pnc_automation/emulator)
- [pnc_automation/automation/script_runner.py](/c:/Users/lebel/pnc/pnc_automation/automation/script_runner.py)
- [tests/test_config_loader.py](/c:/Users/lebel/pnc/tests/test_config_loader.py)
- [tests/test_emulator_session.py](/c:/Users/lebel/pnc/tests/test_emulator_session.py)
- one new resolver-focused test module under [tests](/c:/Users/lebel/pnc/tests)

## 9. Acceptance criteria

This plan is complete only when all of the following are true:

- authored config no longer stores dynamic BlueStacks ADB ports,
- runtime resolves the current live port from BlueStacks host metadata before building the session,
- the resolver fails fast and clearly on missing or ambiguous instance matches,
- live runs no longer require temporary port-edit config overrides after BlueStacks is relaunched,
- `serious_stuff` and `testing` can both reconnect successfully through the same canonical discovery path.
