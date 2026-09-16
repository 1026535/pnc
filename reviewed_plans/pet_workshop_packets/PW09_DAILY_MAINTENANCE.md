# PW09 — Daily Maintenance integration

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW07](PW07_WORKFLOW_EXECUTION.md)

## Read before implementation

- [Plan 03: Daily Maintenance behavior and results](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#daily-maintenance)
- [Plan 03: scope factory and observed-bar authority](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#exact-feature-identity-authority-and-budgets)
- [Plan 03: persisted invocation and pending operations](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#persistence-and-migration)
- [Plan 03: required offline checks](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#6-tests-and-completion)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** Daily integration worker. **Prerequisite detail:** lead-accepted PW07 commit. Can run alongside PW08; neither depends on the other's public adapter.

Own the optional Workshop field in `DailyMaintenanceTargetConfig`/loader, Daily connected runner/factory migration, phase continuation mapping and `_run_instance` integration. Call the accepted connected workflow directly after existing work; do not call the connection-opening public API. Map phase results through PW07's single `CONTINUE`/`STOP_INSTANCE` classifier and retain the detailed reason in the summary. Use the [current-run and later-invocation rules](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#continuation-and-later-invocations); Daily must not persist a separate instance block or automatically retry a stopped target list. Add repeated-same-day, safe/unsafe prior-phase, omitted policy and physical-instance isolation tests. Update the existing Daily documentation and a sanitized example.

## Acceptance

Every enabled safe maintenance invocation re-reads Workshop state and invokes the same workflow once for each selected castle; other independent instances continue after a typed instance stop. No fake Daily row, duplicate scope factory or second connection is introduced.

## Focused validation

Test enabled/omitted policy, execution after existing safe work, unsafe prior-phase suppression, repeated same-day invocations after earlier zero, and typed physical-instance stop propagation. Preserve existing Daily behavior when Workshop is omitted. The connected adapter must not acquire a second connection or call the connection-opening public API. A later authorized maintenance invocation explicitly selecting B may proceed only after fresh validation, preserving A's unresolved action; encountering A again must retain its block. Reuse PW07's scenario to verify the adapter mapping without duplicating recovery logic.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Daily adapter/configuration migration diff, sanitized example, same-day/isolation test results and the PW07 dependency commit. Lead combines it with PW08 without moving common lifecycle logic into either adapter.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.
