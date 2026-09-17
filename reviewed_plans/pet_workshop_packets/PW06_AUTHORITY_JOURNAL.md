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


### Execution record — 2026-09-16

- Status: **Delegated**, not accepted. Foundation implementation `14b7d68` is reviewed/tested and pushed; worker base `91afce6f9a817129f2e205b9479043744c4ca300` adds its acceptance record only.
- Scope: Canonical authority, invocation factory and durable journal/migration. UI interpretation/execution belongs to PW07; no live or account/config access.
- Checkout/branch: `C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-authority`, `codex/pet-workshop-authority`.
- Native Devin session `fearless-sprite`, run `.local-data/devin-implement/pw06`, turn `001`. Startup confirmed with `swe-2-max`, expected base and native steering/cancellation controls.
- Briefs: worker `.local-data/devin-briefs/pw06-authority.md` and `pw-wave-common.md`. Use the explicit dependency-correct Python environment named there; global py/shared .venv lack current rapidocr. APK/extracted Lua remain offline references only.
- The existing lead monitor registered this run and the native completion callback targets this coordinating task. Lead owns independent review, fixes, applicable final-candidate live proof, integration and acceptance.
- Reviewed/tested result revision and acceptance evidence: pending handoff.

### Recovery and resolved type/budget choices

Turn 001 was interrupted when all three Workshop worker/monitor processes disappeared around 2026-09-17 01:34 UTC; cause unestablished. No tracked PW06 implementation had been saved. Lead verified absent local writers/tests, matched native `fearless-sprite` identity with `devin list` in the exact checkout, preserved `turn-001/state-before-host-recovery.json`, and repaired the stale record. The checkout was fast-forwarded to accepted main `4f1e119ae3f7a6d9e5e8891c81347a3656fbf4d3`.

Same session resumed as **turn 002**, supervisor 57492, with native SWE-2 Max readiness confirmed. Delta brief: `.local-data/devin-briefs/host-recovery.md`. The lead resolved two questions from the bounded saved analysis: retain the existing building enum and a narrow Workshop action enum under one supported feature-kind union/parser; normalize supported old flat counted inputs and the new tagged Workshop budget once at the input boundary into one canonical tagged representation, rejecting conflicting simultaneous declarations. Required persisted-data migration remains one-way. No duplicate internal budget path or generic registry framework is needed.

Implementation, focused proof and final-candidate affected evidence remain pending. The Main release belongs to a separate live assignment; this authority/journal worker remains offline.
