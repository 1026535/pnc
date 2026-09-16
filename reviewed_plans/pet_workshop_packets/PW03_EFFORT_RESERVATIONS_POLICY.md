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


### Execution record — 2026-09-16

- Status: **Delegated**, not accepted. Foundation implementation `14b7d68` is reviewed/tested and pushed; worker base `91afce6f9a817129f2e205b9479043744c4ca300` adds its acceptance record only.
- Scope: Pure effort/allocation/ranking/reservations and shared validator. The same worker may continue into PW04 only after its focused policy checks pass; one combined independent lead review follows.
- Checkout/branch: `C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-solver`, `codex/pet-workshop-solver`.
- Native Devin session `absorbing-vicuna`, run `.local-data/devin-implement/pw03-pw04`, turn `001`. Startup confirmed with `swe-2-max`, expected base and native steering/cancellation controls.
- Briefs: worker `.local-data/devin-briefs/pw03-pw04-solver.md` and `pw-wave-common.md`. Use the explicit dependency-correct Python environment named there; global py/shared .venv lack current rapidocr. APK/extracted Lua remain offline references only.
- The existing lead monitor registered this run and the native completion callback targets this coordinating task. Lead owns independent review, fixes, applicable final-candidate live proof, integration and acceptance.
- Reviewed/tested result revision and acceptance evidence: pending handoff.
