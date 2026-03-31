# Review: BlueStacks port autodetection implementation

Commit reviewed: `70d0316106a406b12c2dc4c507fc175932b8e500` (`Implement BlueStacks port autodetection`)

Scope reviewed:

- config/model migration from authored `device_id` to authored `display_name`,
- BlueStacks host-metadata parsing and runtime resolution,
- `ScriptRunner` session wiring,
- live-tooling updates,
- new and updated tests.

## Summary

The config-schema migration is clean, the resolver is well scoped, and the targeted unit tests currently pass. I still found one high-severity runtime correctness issue plus two smaller follow-up gaps that should be cleaned up before treating this as fully robust.

## Findings

### 1. High: the resolver can silently connect to the wrong emulator when `status.adb_port` is stale or shared

Evidence:

- [bluestacks_instance_resolver.py](/c:/Users/lebel/pnc/pnc_automation/emulator/bluestacks_instance_resolver.py#L66)
- [bluestacks_instance_resolver.py](/c:/Users/lebel/pnc/pnc_automation/emulator/bluestacks_instance_resolver.py#L112)
- [script_runner.py](/c:/Users/lebel/pnc/pnc_automation/automation/script_runner.py#L156)
- [test_bluestacks_instance_resolver.py](/c:/Users/lebel/pnc/tests/test_bluestacks_instance_resolver.py#L18)
- Live host metadata on this machine currently shows three different display names advertising port `5555`: [bluestacks.conf](/c:/ProgramData/BlueStacks_nxt/bluestacks.conf#L123), [bluestacks.conf](/c:/ProgramData/BlueStacks_nxt/bluestacks.conf#L165), [bluestacks.conf](/c:/ProgramData/BlueStacks_nxt/bluestacks.conf#L277), [bluestacks.conf](/c:/ProgramData/BlueStacks_nxt/bluestacks.conf#L319), [bluestacks.conf](/c:/ProgramData/BlueStacks_nxt/bluestacks.conf#L431), and [bluestacks.conf](/c:/ProgramData/BlueStacks_nxt/bluestacks.conf#L473).

Why this is a problem:

- The new resolver only proves that exactly one record matches the configured `display_name`.
- It does not prove that the matched record is currently running.
- It does not prove that the resolved port is uniquely owned by that record.
- `ScriptRunner.build_connected_session()` then trusts the resolved `device_id` and only checks that *some* ADB target responds on that socket.
- On the current host, `serious_stuff`, `mega_old_acc`, and `157_farm` all claim `status.adb_port="5555"` in `bluestacks.conf`, while only `HD-Player.exe --instance Nougat32` is actually running on that port.
- With the current implementation, resolving `mega_old_acc` would still return `127.0.0.1:5555` and would attach to the live `serious_stuff` session instead of failing fast.

Clean fix:

1. Extend the runtime catalog so resolution is based on `display_name` plus a proven running-instance signal, not just `display_name` plus a remembered port.
2. Use the already-available BlueStacks runtime identity `instance_key` and cross-check it against currently running `HD-Player.exe --instance <instance_key>` processes, or another equally authoritative BlueStacks runtime source.
3. Reject matches whose instance key is not currently running.
4. Reject matches whose resolved port is also claimed by any other running instance.
5. Add a regression test for a matched display name whose record exists but whose instance is not running.
6. Add a regression test for two different instance records sharing the same port.
7. Add a regression test for one running instance and one stale inactive record sharing the same port.

### 2. Medium: the new canonical live-session wiring still exists in multiple wrapper shapes

Evidence:

- [script_runner.py](/c:/Users/lebel/pnc/pnc_automation/automation/script_runner.py#L156)
- [discover_selector_registry.py](/c:/Users/lebel/pnc/tools/discover_selector_registry.py#L190)
- [live_smoke_support.py](/c:/Users/lebel/pnc/tests/live_smoke_support.py#L17)
- [validate_navigation_selectors.py](/c:/Users/lebel/pnc/tools/validate_navigation_selectors.py#L107)

Why this is a problem:

- This commit correctly introduces `ScriptRunner.build_connected_session()` as the canonical session-construction boundary.
- `discover_selector_registry.py` uses that boundary directly.
- `tests/live_smoke_support.py` and `tools/validate_navigation_selectors.py` each re-implement the same `getattr` / `callable` / `isinstance` wrapper around it.
- `tests/live_smoke_support.py` also still reaches into the private `_build_runner()` API for a live automation runner.
- None of this is catastrophic today, but it is unnecessary duplication and makes the new canonical boundary easier to drift out of sync later.

Clean fix:

1. Promote one public helper for live runtime construction instead of several ad hoc wrappers.
2. Either expose that helper on `ApplicationRunner`, or add a small production helper module that accepts a typed `ScriptRunner` and `AccountConfig`.
3. Update tools and test support to use that one helper directly.
4. If live tooling legitimately needs a ready `AutomationRunner`, expose a public method for that too instead of continuing to reach through `_build_runner()`.

### 3. Low: top-level application wiring for the new resolver path is not covered by tests

Evidence:

- [app.py](/c:/Users/lebel/pnc/pnc_automation/app.py#L104)
- [app.py](/c:/Users/lebel/pnc/pnc_automation/app.py#L116)
- [test_app.py](/c:/Users/lebel/pnc/tests/test_app.py#L17)
- [test_app.py](/c:/Users/lebel/pnc/tests/test_app.py#L56)

Why this is a problem:

- The new `defaults.bluestacks_config_path -> BlueStacksInstanceResolver(config_path=...)` wiring is one of the core behaviors introduced by this commit.
- The current application-wiring tests verify selector-catalog wiring and archive-root wiring, but they do not assert that the resolver is injected at all or that it receives the resolved config path.
- That leaves a straightforward regression path where a future refactor could hardcode the default path or accidentally drop the resolver wiring without breaking the current suite.

Clean fix:

1. Add one `build_application_runner()` test that authors a relative `defaults.bluestacks_config_path`.
2. Assert that `application.script_runner.instance_resolver` is a `BlueStacksInstanceResolver`.
3. Assert that its `config_path` equals the fully resolved path from the loaded config.

## Validation performed

- Ran `py -3 -m unittest tests.test_bluestacks_instance_resolver tests.test_config_loader tests.test_script_runner tests.test_app tests.test_emulator_session`
- Result: `Ran 33 tests` / `OK`
- Also inspected the live `C:\ProgramData\BlueStacks_nxt\bluestacks.conf` contents and current `HD-Player.exe` process list on this machine to compare the resolver assumptions against real BlueStacks runtime state.
