# BlueStacks runtime port collision plan

## Objective

Make named-instance startup tolerate BlueStacks' short-lived port-metadata updates
without weakening the protection that prevents automation from attaching to the wrong
account. Keep `display_name` and BlueStacks `instance_key` as the stable identity;
continue treating the ADB port as runtime output.

This plan follows the completed
[port-autodetection plan](PNC_BLUESTACKS_PORT_AUTODETECTION_SUBPLAN.md) and its
[review](PNC_BLUESTACKS_PORT_AUTODETECTION_REVIEW.md). It does not reopen that migration.

## Diagnosis

### Repository-proven behavior

- Authored account configuration maps an account to a BlueStacks display name and does
  not store an ADB port.
- `HDPlayerBlueStacksInstanceLauncher` starts the selected BlueStacks `instance_key`
  using `HD-Player.exe --instance <instance_key>`; no port is passed to startup.
- `BlueStacksInstanceResolver` reloads `status.adb_port` after a newly launched process
  appears. The existing
  `test_resolve_reloads_adb_port_assigned_during_instance_launch` regression proves a
  changed post-launch port is used.
- Resolution cross-checks the display name against running process instance keys. It
  ignores a same-port record for an inactive instance and rejects two running records
  that claim one port. Those are required wrong-account protections.

The original review finding that a stale inactive record could silently redirect a run
has therefore already been fixed. Removing the active-collision rejection would
reintroduce that defect.

### September 12 host evidence

- A canonical `serious_stuff` resolution failed before ADB connection or game input.
  The captured error identified target key `Nougat32` and running keys `Nougat32` and
  `Pie64` as claimants to runtime port `5555`.
- A later read of BlueStacks host metadata reported `Nougat32` on status port `5556`,
  `Pie64` on `5555`, and `Rvc64` on `5556`. The underlying non-status `adb_port` values
  were also reused. This shows that the host file contains mutable and stale values;
  it does not prove which earlier assignment BlueStacks intended.
- At the later diagnostic snapshot no `HD-Player.exe` process, local ADB listener, or
  attached ADB device was present. The earlier collision was no longer active and could
  not be safely resolved after the fact.
- Process command-line discovery can be denied in restricted Windows execution
  contexts. The existing unique-and-reachable-port fallback remains valid only when no
  other host record claims the same runtime port.

### Conclusion

Starting by name is already implemented. The observed defect is a BlueStacks host
binding in which two running instance records claimed one port; the resolver correctly
stopped. The later metadata change makes a startup convergence race plausible, but does
not prove one. The first milestone must classify the collision as transient or
persistent. Only a demonstrated transient race justifies changing resolver timing. A
persistent duplicate remains an identity ambiguity and must be repaired in host state
before ADB or game access.

## Scope

In scope:

- bounded classification of transient versus persistent active-port collisions;
- bounded post-process metadata convergence in the canonical resolver;
- actionable, non-secret diagnostics for a persistent active-port collision;
- deterministic regression coverage for transient and persistent collisions;
- one read-only live resolution proof on `serious_stuff` after offline validation.

Out of scope:

- authored ADB ports or changes to account mappings;
- direct edits to `C:\ProgramData\BlueStacks_nxt\bluestacks.conf`;
- choosing an arbitrary connected ADB device;
- ignoring a persistent duplicate claim;
- automatically stopping or restarting a different task's instance;
- game navigation, login, castle switching, resource spending, or message sending.

## Target design

Keep `BlueStacksInstanceResolver` as the single owner of name-to-runtime-endpoint
resolution. After the exact target process is present, resolve a usable binding only
when one catalog snapshot proves all of the following:

1. the configured display name still maps to the original instance key;
2. exactly one running process exposes that instance key;
3. its `status.adb_port` is valid;
4. no other running instance record claims that port; and
5. the local endpoint is reachable when reachability is required by the existing path.

If bounded evidence establishes that BlueStacks publishes a transient duplicate after
startup, reload the complete catalog using the existing launch poll interval and attempt
budget. Do not issue another launch request during this wait. Return immediately once
the binding is proven. If the duplicate remains stable across the budget, retain the
current immediate fail-closed behavior except for improved diagnostics; repeated waiting
would only delay an actionable host failure.

When the budget expires, raise one structured `ConfigurationError` containing the target
display name, target instance key, last observed port, conflicting running instance keys
and display names, poll count, and failure phase. Do not include process command lines,
host tokens, account identifiers, or other BlueStacks configuration values.

When convergence is demonstrated, use the same owner for an already-running target and
a newly launched target. The launch path should wait first for the exact process and then
for the exact runtime binding. Reuse the current `launch_poll_attempts` and
`launch_poll_interval_seconds`; no new configuration knob is justified unless live
evidence shows the process and metadata need different budgets.

Persistent collision recovery stays outside ordinary resolution. An operator may use
the existing fleet restart owner only after naming the complete affected display-name
bundle and acquiring all of its leases. The resolver itself must never stop another
instance to make its target usable.

## Implementation steps

### 1. Classify the live collision without ADB or game input

Under the canonical `serious_stuff` lease, read several complete process/config catalog
snapshots across the existing poll interval. If the target is stopped, a single launch
by its exact instance key requires the same host-launch authority used by ordinary live
testing. Do not connect ADB, foreground PNC, or stop another instance.

Acceptance:

- each snapshot records only display name, instance key, PID, runtime port, metadata
  timestamp, and conflicting active keys;
- if a duplicate changes to a unique target binding within the budget, classify it as a
  transient convergence race;
- if it remains unchanged, classify it as a persistent host collision;
- if process metadata is denied, classify the issue separately and do not infer either
  port condition.

### 2. Capture the demonstrated condition as regressions

Extend `tests/unit/bluestacks_management/test_bluestacks_instance_resolver.py` with:

- if milestone 1 proves convergence, a running target whose first catalog shares its
  port with another running instance followed by a distinct-port snapshot; resolution
  must wait and return the final port without launching or connecting to the first;
- if milestone 1 proves convergence after launch, the same transient sequence for a
  newly launched target; exactly one launch occurs;
- a persistent duplicate through the full budget; resolution raises and never returns a
  device ID;
- assertions that remapped display names, changed instance keys, duplicate process keys,
  and inactive stale records retain their current fail-fast behavior.

Acceptance: each test represents the classified host condition. Do not add synthetic
retry behavior for a race that milestone 1 did not observe.

### 3. Add one bounded runtime-binding convergence helper when justified

Refactor `pnc_automation/core/infra/emulator/bluestacks_instance_resolver.py` so process
startup and port-binding completion are distinct predicates over fresh catalog snapshots.
The helper should return the validated record, exact process, and port together so later
code cannot accidentally combine values from different snapshots.

Acceptance:

- the launcher still receives only the original instance key;
- no port is read from authored repository configuration;
- a transient duplicate consumes observations but sends no host or ADB action;
- a persistent duplicate never materializes `BlueStacksInstance`;
- `host_instance_key`, `process_id`, `device_id`, and `started_by_resolver` come from the
  same proven lifecycle.

If milestone 1 proves a persistent collision, skip this code change. Keep the existing
active-port rejection and proceed to diagnostics and explicit host recovery.

### 4. Make persistent failures actionable

Retain the existing error type and add stable details for the collision and convergence
budget. Keep process-enumeration denial separate from port ambiguity so operators can
distinguish Windows permissions from BlueStacks metadata.

Acceptance: one failed run identifies which named running instances must be quiesced or
restarted, without requiring inspection of raw host configuration or exposing secrets.

### 5. Document explicit host recovery

Add a short operator note to the existing BlueStacks management documentation:

- acquire leases for every named instance in the reported collision;
- use the existing lease-aware fleet restart path for that exact bundle;
- let BlueStacks rewrite runtime ports;
- rerun ordinary named-instance resolution;
- stop if the collision remains.

Do not add automatic recovery to `resolve()`. A caller authorized only for
`serious_stuff` cannot stop `mega_old_acc` or `157_farm`.

## Validation

Offline:

1. Run the focused resolver tests through the repository runner's applicable unit group
   or the exact documented module.
2. Run `py tools/run_tests.py affected --base origin/main --explain`; accept the full
   fallback only if the selection rules require it.
3. Run `git diff --check`.

Live boundary:

- Target: configured `serious_stuff`; no castle selection is required.
- Authority: acquire the canonical process-scoped `serious_stuff` lease before any ADB
  access. If a conflicting instance is already running, report the complete collision
  and stop; do not acquire or disturb it implicitly.
- Entry point: build one connected runtime through the production resolver after offline
  checks.
- Precondition: exact display-name-to-instance-key mapping and no unresolved active-port
  collision.
- Success: the resolver records one exact instance key, PID, and unique reachable runtime
  device ID from a converged snapshot. No game input is necessary.
- Budget: at most one target launch and the existing bounded catalog poll budget.
- Stop conditions: process metadata is unavailable, identity changes, the port remains
  shared, the endpoint is unreachable, or another lease owns the target.

No resource-spending proof or full game workflow is part of this repair.

## Risks and remaining limits

- BlueStacks may retain a persistent duplicate port across the full poll window. That is
  a host-state blocker requiring an explicitly authorized bundle restart, not a reason to
  guess.
- If Windows denies process command-line metadata and host records share a port, the
  resolver cannot prove instance identity. The safe result remains failure.
- A process restart after successful resolution invalidates its PID and endpoint. The
  next session must resolve again; mid-session automatic rebinding would weaken the
  current lease and identity contract and is excluded.
- The implementation feature must start from freshly fetched `origin/main`. At this
  feature base, `origin/main` is `850bdb747be79bb78363b8dca49a0097c6ed6546` and
  already includes `5135dde` for hidden PowerShell monitor windows. Do not infer the
  state or ownership of the current local `main` checkout from this baseline.

## Completion criteria

The repair is complete when the live condition is classified, persistent collisions
remain fail-closed with useful diagnostics, focused and affected checks pass, and one
authorized `serious_stuff` runtime resolution proves the production path without game
input. When a transient race is demonstrated, the bounded convergence path must also
pass. If the host retains a persistent collision, code may be complete but live proof
remains blocked until the exact conflicting display-name bundle is explicitly restarted.
