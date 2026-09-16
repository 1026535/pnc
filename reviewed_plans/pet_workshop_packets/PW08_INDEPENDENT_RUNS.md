# PW08 — Independent CLI, API and authored runs

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW07](PW07_WORKFLOW_EXECUTION.md)

## Read before implementation

- [Plan 03: public behavior](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#required-public-behavior)
- [Plan 03: exact authority and budget contract](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#exact-feature-identity-authority-and-budgets)
- [Plan 03: independent entry points](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#independent-api-cli-and-authored-task)
- [Plan 03: results and physical-instance isolation](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#results-and-isolation)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** independent-entry worker. **Prerequisite detail:** lead-accepted PW07 commit. Can run alongside PW09.

Own `TaskId.PET_WORKSHOP`, its typed parameter/registry/core-dispatch binding, application/direct API and the `pet-workshop` CLI target/acknowledgement adapter. Use the accepted common boundary/target runner. Add CLI parsing, alias/authority prevalidation, authored repeat and one-core/lease parity tests; update the independent/authored usage documentation. Do not edit Daily runner/configuration or recreate the lifecycle.

## Acceptance

Direct and authored execution invoke the same workflow, without any Daily quest scan or generic task retry path; selected target ordering and failure isolation match the common result contract.

## Focused validation

Test exact CLI/acknowledgement parsing and pre-connection failures, direct API delegation, authored task/repeat binding, target aliases/order and one-core/lease reuse. Prove the adapter calls the accepted workflow/result owner. Reuse PW07's lifecycle tests instead of implementing a second loop just for these entry points. Check adapter parity with the [later-invocation rule](../PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md#continuation-and-later-invocations): a separate explicitly selected B run on the same instance still goes through fresh validation, while A's pending action stays blocked. No public flag may clear pending work or bypass the shared continuation decision.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Independent/authored adapter diff, usage example and focused validation, with the PW07 dependency commit. Lead combines it with PW09; shared document sections are reconciled by ownership.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.
