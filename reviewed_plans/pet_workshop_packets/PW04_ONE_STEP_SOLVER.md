# PW04 — One-step solver and deterministic scenarios

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW03](PW03_EFFORT_RESERVATIONS_POLICY.md)

## Read before implementation

- [Plan 02: decision order and revalidation](../PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md#3-decision-order-and-revalidation)
- [Plan 02: required scenarios and estimator limits](../PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md#5-required-scenarios-and-acceptance-limits)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted PW01 contract and the tested PW03 implementation as described below. Cross-worker handoffs require an accepted commit. Reconcile newer changes by symbol and keep shared-contract corrections with their owner.

## Assignment

**Owner:** preferably the PW03 solver worker. **Prerequisite detail:** PW01 and the tested PW03 policy implementation. The same worker may continue directly and return PW03/PW04 for combined lead review; a separate worker starts from the accepted PW03 commit. No recognition dependency for typed scenarios.

Implement `plan_next` using the agreed intents and decision sequence. Keep state transitions in a small **test-only** scenario driver using authored outcomes; do not add a production game simulator. Apply actual/synthetic outputs to the next typed state and require the next decision to react correctly.

The offline analysis entry point from Plan 01 calls this same public planner once PW02 is ready. No solver-specific image parser or separate screenshot-only policy is allowed. Update the solver/policy/extension sections in `docs/PET_WORKSHOP_DESIGN.md` and the task usage documentation with clear distinction between proposals and executed actions.

## Acceptance

The full typed scenario suite passes and the public planner is ready for PW05's screenshot milestone; ready three-coconut rejection is independent of the order's displayed Complete control or valuable reward.

## Focused validation

Complete the typed decision scenarios in Plan 02, including immediate zero stop, unsupported orders, generator selection, all four ordinary mechanics, constrained recycling and wait requests. Supply authored outcomes to a test-only driver; PW05 separately proves decisions from real screenshot labels. Include the distinction between a recoverable feed/exhaustion state and an unresolved production path: use the supported mechanic when possible, otherwise the existing inspection/blocked result, without a new locked-chain fallback objective.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Public plan_next implementation, typed scenario results and lead-reviewed decision examples. PW05 and PW07 consume the same accepted planner without screenshot-only or runtime substitutes.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.
