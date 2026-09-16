# PW03 — Effort estimates, reservations and legal-action policy

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW01](PW01_SHARED_CONTRACT_CATALOG.md)

## Read before implementation

- [Plan 02: policy and planning semantics](../PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md#2-policy-and-planning-semantics)
- [Plan 02: canonical legal-action revalidation](../PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md#3-decision-order-and-revalidation)
- [Plan 02: required scenarios](../PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md#5-required-scenarios-and-acceptance-limits)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** solver worker. **Prerequisite detail:** accepted PW01. **Offline only.**

Implement catalog-driven missing-ingredient allocation, producer contribution/effort estimates, order classification/ranking, reservation checks and `validate_intent`. Keep numeric estimates separate from confidence/legality so an uncertain efficiency estimate cannot become permission to act on an unknown item.

Follow [level-linked progression and blocked goals](../PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md#level-linked-progression-and-blocked-goals): no speculative lower-ranked production strategy or hidden server-order eligibility check. Existing feeding, merging/activation and producer reconstruction remain useful progress when their preconditions hold.

Test the allocation and score with small authored graphs and representative real catalog chains. Include quantities at several tiers and a generator that produces two families; do not test only a function's own internal representation. Return the estimate, selected tier and material uncertainty in diagnostics.

## Acceptance

A reviewer can explain why an order or action was chosen using its requirements, reward and remaining effort; no piece is double-counted, no larger piece is assumed splittable, and a lower-priority order cannot consume reserved progress.

## Focused validation

Cover multiset allocation at different tiers, un-splittable high tiers, protected progress, zero-cost goals, uncertain finite capacity, and the documented mixed-output estimate. Exercise the shared validator against permitted and forbidden actions; PW04 owns complete decision-sequence replay.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Reviewed estimator/allocator/validator implementation, example ranking diagnostics, uncertainty limits and focused test results. PW04 consumes this exact implementation; the executor later calls the same validator.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.
