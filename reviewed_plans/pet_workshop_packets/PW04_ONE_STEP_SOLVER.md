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

## Implementation review — correction batch 1

**Current disposition: accepted and merged/pushed** at `4f12095a1b10ff1c600a1dcdb1f0f7bf82c3000c`. The [combined PW03 acceptance record](PW03_EFFORT_RESERVATIONS_POLICY.md#accepted-and-merged--2026-09-17) owns final review, correction, test and integration evidence. The final candidate passed 2,741 tests with 7 unrelated environmental skips, including all 166 focused solver tests. Production/test content is unchanged from the tested `dc810c8` revision. The records below preserve earlier findings and are superseded by that acceptance.

**Disposition: Fixing findings; not accepted.** Combined review/revision/test evidence and worker continuation are recorded in [PW03](PW03_EFFORT_RESERVATIONS_POLICY.md#implementation-review--correction-batch-1). Lead reviewed `a9f79ae`; the unchanged solver content is now on current main as candidate baseline `b868a5f` in its isolated branch. None of this candidate has been merged to main.

**S2 — canonical validation does not cover every proposed mutation.** `planner.py` validates submissions but returns other mutations directly, contrary to its documented contract. A selected Tree 4 with unknown production mode returns Produce while `validate_intent` says UNCERTAIN. A fully observed board with unknown occupancy in every other cell also returns Produce without a confirmed empty square. `_cell_inspect` omits these missing occupancy/access facts, and the full-board activation enumerator omits the required successor check.

The same solver worker must make every proposed mutation pass canonical validation, request relevant safe inspection where facts are missing, and retain other valid work when a candidate is prohibited. Do not duplicate legality in a second planner or turn nonparticipating unknowns into a blanket stop. Add regression scenarios for these cases and validate each proposed mutation in the test-only outcome driver. PW03's recipe/reservation fixes must also prove useful recovery and free activation through complete supplied-outcome sequences.

The existing 129 focused tests passed under independent lead execution but miss these cases. Final corrected revision, regression results, broader runner evidence and lead re-review remain required before PW05 or PW07 consumes the planner. This pure package has no live gate; later recognition and execution do.


### Execution record — 2026-09-16

- Status: **Delegated**, not accepted. Foundation implementation `14b7d68` is reviewed/tested and pushed; worker base `91afce6f9a817129f2e205b9479043744c4ca300` adds its acceptance record only.
- Scope: One-step planner and synthetic scenario sequences following tested PW03 in the same worker. External consumers remain gated on lead acceptance of the combined handoff.
- Checkout/branch: `C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-solver`, `codex/pet-workshop-solver`.
- Native Devin session `absorbing-vicuna`, run `.local-data/devin-implement/pw03-pw04`, turn `001`. Startup confirmed with `swe-2-max`, expected base and native steering/cancellation controls.
- Briefs: worker `.local-data/devin-briefs/pw03-pw04-solver.md` and `pw-wave-common.md`. Use the explicit dependency-correct Python environment named there; global py/shared .venv lack current rapidocr. APK/extracted Lua remain offline references only.
- The existing lead monitor registered this run and the native completion callback targets this coordinating task. Lead owns independent review, fixes, applicable final-candidate live proof, integration and acceptance.
- Reviewed/tested result revision and acceptance evidence: pending handoff.

### Turn 003 review — 2026-09-17

Worker turn 003 completed at `761837e`, with a clean checkout and released writers. Lead passed all 146 focused tests, reviewed the correction diff, then closed the remaining ready-secondary ranking gap and made every mutation candidate pass the canonical validator in lead commit `efac6de`. The same commit proves a free Normal-partner merge followed by inactive activation and submission through the validating test-only outcome driver. The final focused suite has **150 passing tests**; `git diff --check` passed.

Detailed finding dispositions and evidence are in [PW03's current review record](PW03_EFFORT_RESERVATIONS_POLICY.md#turn-003-independent-review-and-lead-corrections--2026-09-17). S3/S4 still block combined acceptance and final affected/full testing. No solver changes were merged or pushed. The released worker slot is available for the already-authorized timed Main evidence assignment; that separate live checkout cannot qualify unfinished solver/execution code.
