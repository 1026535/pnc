# Production boundary ownership

Script authoring owns `TaskRegistry` and preparation against task contracts.
`app.entrypoints.task_registry` owns default concrete task construction.
Daily automation owns `ConnectedClaimOnlyCastleRunner`; the entrypoint module
`app.entrypoints.daily_maintenance` builds and injects its application dependencies.

`app.pnc.domain.castles` owns castle identity, identity keys, roster ordering, and
`PncAccountCastleRosterConfig`. The existing roster class name is retained to
preserve caller and serialized diagnostic names; it is a domain value, not a
configuration loader. Authored configuration refers to these canonical values.

`core.vision.observation_policy` owns the neutral `ObservationMode` enum.
`app.pnc.domain.observation_policy` owns immutable artifact selection and resolution
because its kinds, owners, and routines include P&C world-map concepts. Runtime
services retain responsibility for artifact emission. The `app.runtime` package
exports remain supported, but production consumers import the canonical owners;
the obsolete runtime observation modules are removed. Diagnostic tool callers
and offline tests use the canonical owners. No compatibility modules or second
policy implementation remain.

`pnc_automation.app` retains its public `ApplicationRunner` and
`build_application_runner` exports and loads composition only when requested.
Importing an inner application submodule does not load the composition root.

The ownership and import checks live under
`tests/architecture/architecture_boundaries/` so affected selection includes their
source-scanning assertions in the mandatory architecture tier. Run the focused
group with `py tools/run_tests.py group architecture_boundaries`.

## Accepted safety dependency

The dependency from `core.infra.emulator.session` to
`bluestacks_management.instance_lease` is explicitly accepted. The latter remains
the single implementation and owner of `PROCESS_INSTANCE_LEASES`,
`InstanceLeaseRegistry`, `ProcessInstanceLease`, and `InstanceLeaseBundle`.
Session acquisition before ADB, shared process reservations, bundle ordering,
bounded acquisition, and failure cleanup continue using that owner. Phase 3
does not relocate, duplicate, or alter any lease or emulator lifecycle code.
This is a safety infrastructure dependency, not permission to import host
monitoring or restart policy into core vision or application domain modules.

This boundary refactor is validated offline. It does not supply live promotion
evidence or authorize unattended execution.
