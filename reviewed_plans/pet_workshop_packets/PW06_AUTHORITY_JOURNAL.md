# PW06 — Feature authority and durable journal

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW01](PW01_SHARED_CONTRACT_CATALOG.md). Independent of recognition, solver and screenshot-tool completion.

## Read before implementation

- [Plan 03: existing owners, authority and persistence](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#2-canonical-owners-and-necessary-extension)
- [Plan 01: shared models and interface ownership](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#4-shared-interface-contract)
- [Plan 03: required offline checks](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#6-tests-and-completion)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** authority/persistence worker. **Prerequisite detail:** accepted PW01 types and the existing authority/journal owners. Can run alongside PW02 and PW03/PW04. No live emulator access.

1. Implement the typed Workshop action identity, observed-bar/count-based budget support, scope normalization and shared invocation-boundary factory from Plan 03. Preserve existing counted/building behavior. Own the feature-kind extension in `WorkflowSpec` and the authority/dispatch portion of `CoreMutationBoundary`; PW07 owns Workshop context methods and connected action binding.
2. Extend the existing journal schema, invocation/sequence records, migration, cross-reset pending lookup and durable reconciliation lifecycle. Reuse `JournaledMutationDispatcher` and its dispatch/reconcile callbacks. PW06 stores and enforces the result disposition for the resolved account/castle; PW07 interprets current UI evidence to produce it. Follow the [pending-operation lifetime](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#persistence-and-migration): preserve the affected castle's pending record across aliases/dates/entry points, without adding a permanent instance-wide block. Do not implement a screenshot parser or an operation-specific UI receipt here.
3. Validate scope/target/budget and retain pending operations through the existing authority/store. Accept the typed Workshop policy/scope as an explicit factory input. Do not require PW09's optional Daily configuration field, PW08's CLI/TaskId registration or PW03's policy defaults to construct the boundary. These later callers adapt to this one factory.
4. Document authority/persistence ownership and run focused migration, budget and no-replay checks with authored typed operations and reconciliation results. Use the existing callback/test seams; no new dependency-injection framework, runtime placeholder or default permissive validator is needed.

## Acceptance

The boundary and durable lifecycle are independently testable after PW01. Existing counted/building scopes and receipts survive migration; cross-reset pending work remains blocking; ambiguous dispatch cannot replay. No fake Daily row, parallel journal, parser, solver or UI executor is introduced. Recognition, legal-action checks and settled-frame interpretation remain mandatory in PW07's connected action path before any gameplay input.

## Focused validation

Cover exact authority normalization, invalid/zero-diamond budgets, counted-budget compatibility, persisted invocation/sequence identity, checkpoint migration, cross-reset pending lookup and no replay after an ambiguous supplied reconciliation result. A separately authorized scope for castle B must not clear or inherit castle A's pending operation; another alias for A must still find it. PW07 owns the fresh UI validation and current-run stop behavior, so these persistence checks need no emulator. Existing dispatcher tests demonstrate this layer's offline test seam using callbacks and a temporary store; new Workshop cases must prove the extension. PW07 owns observed-zero, selection, gesture, optimistic-frame and recycle-confirmation tests.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Accepted scope/budget and invocation factory, journal migration/query operations, durable result contract and focused checks. PW07 connects actual policy, perception and action receipts through this boundary. PW08/PW09 later call the same factory through the common workflow; no authority or pending-operation logic moves into either adapter.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.
