# Host Safety and Runtime Isolation Implementation Plan

Status: **implemented and validated** on `codex/host-safety`.

## Context

This plan turns `04_host_safety.md` from local commit
`f9da4aa3b7b47089f021fe690bd75884338dc2ad` into an executable change set on
feature branch `codex/host-safety`, based on `origin/main` commit
`ff82f2d37feae5b75245b505adf1beb6beef04e2` after final synchronization.

The completed but uncommitted audit work in
`C:/Users/lebel/.codex/worktrees/a032/pnc` is evidence and a source of focused
hunks, not a branch to copy wholesale. Every hunk must be reconciled with the
newer canonical owners on the feature base.

The plan's earlier `is_app_foregrounded` lead is already resolved on the base
by commit `bffd316a305434cf69799583f9f7d6901957f0e8`. The current implementation
parses exactly one `mCurrentFocus` field, ignores retained background windows,
and has deterministic malformed/duplicate/background-window tests. No further
foreground parser change belongs in this feature.

## Goals

- Encode `adb shell input text` as one literal AOSP-shell argument while
  preserving Android's `%s` space convention and keeping rejected input out of
  diagnostics.
- Reject BlueStacks display-name rebinding during startup and make host binding
  validation the single canonical authority used by both host-only and full app
  config loaders.
- Make multi-instance lease acquisition, initialization, rollback, and release
  bounded and exception-safe without hiding primary or cleanup failures.
- Preserve every same-label, same-second artifact with atomic exclusive file
  creation rather than an overwrite-prone existence check.

## Non-Goals

- No host schema, local account/castle config, role assignment, or credential
  changes.
- No broad host-management refactor, full BlueStacks restart, castle switch,
  game action, claim, send, or resource spending.
- No movement of shutdown tests; that remains coordinated with the separate
  test-modularity work.
- No speculative changes to the already-canonical foreground-window parser.

## Current State

- `core/infra/emulator/session.py` manually escapes a subset of shell
  metacharacters, leaves expansion forms such as `$()`, backticks, globs, and
  backslashes ambiguous, and includes rejected multiline text in structured
  error details.
- `BlueStacksInstanceResolver` re-resolves by display name after launch but does
  not verify that the refreshed record has the original instance key.
- `core/config/host.py` owns complete case-insensitive host binding checks behind
  a private function, while `app/authoring/config/validation.py` duplicates only
  part of that policy and compares display names case-sensitively.
- `InstanceLeaseRegistry` validates only sign/range basics, rolls back partial
  bundles only for contention, can leave a native handle open during
  initialization failure, and may skip `close()` when explicit unlock fails.
- `ArtifactStore.persist_bytes` writes directly to the timestamp-derived path,
  replacing an earlier artifact with the same directory, label, extension, and
  second.

## Target Design

1. `session._encode_adb_text` replaces Android spaces with `%s`, then applies
   `shlex.quote` to the entire remote argument. Multiline rejection reports only
   the validation condition.
2. `core.config.host.validate_host_bindings` is the public canonical policy for
   instance/account ids, casefolded display names, account references, per-account
   roles, and shared-instance read-only/active conflicts. The app loader adapts
   its typed models to `BlueStacksInstanceBinding` and `AccountBinding`, then
   retains only application-specific validation.
3. The resolver retains the pre-launch instance key and rejects a refreshed
   display-name match that points to any other key.
4. Lease timing inputs reject booleans, non-numeric values, NaN, infinities, and
   invalid signs before acquisition. All partial acquisitions roll back on any
   exception. Initialization and release always close handles. When both the
   primary operation and cleanup fail, both exceptions remain available through
   an exception group or the existing lifecycle helper.
5. Artifact filenames retain the current canonical timestamp/label stem. The
   first writer creates the unsuffixed path with `xb`; collisions retry `_1`,
   `_2`, and so on using exclusive creation, so concurrent writers cannot race
   through a check-then-write window.

## Implementation Phases

### Phase 1: Remote Text Safety

- Change `pnc_automation/core/infra/emulator/session.py`.
- Extend `tests/unit/core/infra/emulator/test_emulator_session.py` with shell
  expansion, quoting, backslash, glob, whitespace, and secret-redaction cases.
- Acceptance: every supported payload forms one literal remote-shell argument;
  multiline input fails before an ADB call and is absent from error details.

### Phase 2: Identity and Canonical Host Authority

- Change `pnc_automation/core/infra/emulator/bluestacks_instance_resolver.py`,
  `pnc_automation/core/config/host.py`, and
  `pnc_automation/app/authoring/config/validation.py`.
- Extend the resolver and host-config tests so both config entry points reject
  case-insensitive display collisions and mixed read-only/active roles.
- Acceptance: one host validator owns the shared policy; the app validator keeps
  only app-specific login, target, roster, and output-root rules; launch-time
  remapping fails closed with expected and actual instance keys.

### Phase 3: Lease Exception Safety

- Change `pnc_automation/bluestacks_management/instance_lease.py`.
- Add deterministic failure injection to
  `tests/integration/emulator/test_instance_lease.py`.
- Acceptance: unexpected second-lock acquisition errors release earlier locks;
  owner-write and unlock failures close native handles; invalid waits fail before
  acquisition; simultaneous primary and cleanup failures preserve both causes.

### Phase 4: Artifact Collision Preservation

- Change `pnc_automation/core/infra/storage/artifact_store.py`.
- Extend `tests/integration/vision/test_capture_storage.py` with fixed-time,
  same-label captures and verify both payloads remain byte-for-byte intact.
- Acceptance: no existing artifact is replaced and no check-then-write race is
  introduced.

### Phase 5: Combined Verification

- Run the exact focused modules after each phase.
- Run affected-test selection against `origin/main`, the full portable suite,
  and `git diff --check` after all slices are combined.
- Run one bounded, zero-spend live proof through the configured `testing`
  instance/current castle using the canonical reservation and runtime.

## Slice-by-Slice Live Validation Matrix

Target for every applicable check: account role `testing` / current castle / its
configured BlueStacks display name. No castle selection is authorized.

| Slice | Live boundary | Expected disposition |
|---|---|---|
| Remote text | Under one scoped reservation, connect and use the configured ADB client to round-trip literal text through remote `printf`; do not inject text into the game UI. | `passed` when bytes equal the `%s`-spaced payload; otherwise `blocked` or `engineering_failure` with trace evidence. |
| Identity/authority | Rebinding and contradictory role/config states must not be induced on the live host. Verify only that the configured identity and role load and resolve consistently. | `applicability_skip` for destructive fault induction, backed by deterministic metadata fakes; live preflight must still pass. |
| Lease cleanup | Hold the canonical reservation across connection and evidence capture, then release it normally and prove a bounded reacquisition succeeds. | `passed` only if the same configured display name can be safely reacquired. |
| Artifact preservation | Capture evidence through the canonical screenshot/artifact path and verify the artifact exists; collision behavior remains deterministic offline proof. | `passed` for production-path capture plus offline collision regression. |

Live precondition: the configured `testing` account has the required smoke role,
the runtime resolves exactly one display-name/instance-key binding, and the
screen state is known or recoverable. Stop on ambiguous identity, unknown screen,
lease timeout, or failed Home recovery. Preserve the run summary, trace, and
screenshots under `.local-data/`. Return Home through canonical navigation when
possible and preserve any pre-existing instance.

## Data, Config, and Migration Notes

No serialized schema or config migration is required. Existing artifact names
remain readable; only new collisions gain numeric suffixes. Existing lock files
and owner metadata retain their current format.

## Validation Plan

Focused commands:

```powershell
py -m unittest tests.unit.core.infra.emulator.test_emulator_session
py -m unittest tests.unit.bluestacks_management.test_bluestacks_instance_resolver tests.unit.bluestacks_management.test_bluestacks_host_config
py -m unittest tests.integration.emulator.test_instance_lease
py -m unittest tests.integration.vision.test_capture_storage
```

Combined commands:

```powershell
py tools/run_tests.py affected --base origin/main --explain
py tools/run_tests.py full
git diff --check
```

The live command will be a narrowed copy of the existing audit probe that keeps
only configuration/role verification, scoped reservation, connection, literal
remote-shell round-trip, canonical artifact capture, final Home, and normal
lease release/reacquisition. It is bounded to ten minutes and eight navigation
transitions with zero resource spend.

## Risks and Mitigations

- Shell quoting may be confused with Windows host quoting. Test the emitted ADB
  argument and an actual AOSP-shell `printf` round-trip.
- Public host validation may accidentally absorb app-only rules. Adapt only the
  shared typed binding fields and retain app-owned checks in the app validator.
- Broad `BaseException` cleanup can hide cancellation or keyboard interrupts.
  Re-raise the original after rollback and preserve simultaneous cleanup errors.
- Windows file-lock failure paths can behave differently from fakes. Keep the
  fault tests deterministic and add bounded normal acquire/release live proof.
- Artifact suffix allocation can race if implemented with `exists()`. Use only
  exclusive creation and retry on `FileExistsError`.

## Open Questions

None block implementation. The foreground-window concern is closed by current
base evidence; shutdown-test relocation remains out of scope.

## Validation Results

- Focused baseline: 58 tests passed before implementation.
- Focused final tree: all 67 session, identity/config, lease, and
  artifact-storage tests passed.
- Affected selection on the first rebased tree: 1,753 tests passed with five
  expected optional skips.
- Final full portable suite after the non-overlapping open-building rebase:
  1,754 tests passed with five expected optional skips.
- `git diff --check`: passed.
- Live target `testing` / current castle / configured `testing` display:
  - remote text: `passed` by literal AOSP-shell `printf` round-trip;
  - identity/authority: destructive rebinding fault induction
    `applicability_skip`, with configured identity preflight passed and the fault
    covered by deterministic metadata tests;
  - lease cleanup: `passed` by scoped reservation and bounded reacquisition;
  - artifact preservation: `passed` through canonical live capture plus the
    deterministic same-label/same-second regression;
  - final state: Home confirmed; zero resource spend; no castle switch;
    pre-existing instance preserved.
- Live report:
  `.local-data/reports/host-safety-live-results.json`.

## Execution Checklist

- [x] Establish passing focused baselines.
- [x] Implement and verify remote text safety.
- [x] Implement and verify identity and canonical host authority.
- [x] Implement and verify lease exception safety.
- [x] Implement and verify artifact collision preservation.
- [x] Run affected and full portable validation.
- [x] Run and classify the bounded zero-spend live proof.
- [x] Review the final branch diff and generated-output status.
