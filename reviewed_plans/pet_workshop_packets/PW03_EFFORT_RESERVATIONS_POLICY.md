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

### Lead correction checkpoint — 2026-09-17

Candidate **`0fbc61dcca8314762dec551904301305bbea0fdf`** contains the lead's S3/S4 corrections, rebased without conflicts onto `6d128f3` (the intervening base changes are packet status documents). `allocate_goal` now owns the shared pool for requirements, feed ingredients, producer acquisition, effort and planning targets. The obsolete independently reconstructed estimate was removed. Repeated fresh finite producers consume new ingredients and upstream energy; an observed finite producer retains unknown capacity. A reachable first construction remains useful when the total further acquisition cost is unknown. Exact finite generator requirements are protected against exhaustion, while unlimited required generators remain usable.

**Passed:** 162 focused policy/validation/planner tests on the same source before the documentation-only rebase; `git diff --check`. New regressions include lower-ready-order theft of feed, a separately required extra feed, Pot-to-Bowl reconstruction after absence/exhaustion, shared fresh finite capacity, repeated rebuild costs, free merge-built feed, reachable producer upgrades and finite versus unlimited exact generator stock. The final `tools/run_tests.py affected --base origin/main --explain` selected all 330 portable modules because this branch adds production modules; it is running with the correct Python 3.13/RapidOCR 3.4.5 environment. Log: solver `.local-data/review/pw03-pw04/final-affected.log`.

**Remaining acceptance finding:** a previously proposed Tree Produce still validates after a fresh complete survey contains no eligible order. The planner correctly stops, but executor revalidation must also reject that now-useless spend and inspect unresolved goal facts. Reproduction is solver `.local-data/review/pw03-pw04/production-revalidation-finding.txt`. Keep the candidate frozen during the active suite; apply the scoped validator/shared-rule correction afterward and test the final revision. This is a pure offline boundary, not a live-account blocker. PW03/PW04 are not accepted or merged at this checkpoint.

**Later resolution / final validation pending:** the lead fixed that last finding in an isolated `pet-workshop-solver-final` checkout while the earlier full run stayed frozen. `ddd7afd` adds one shared production-contribution calculation and makes revalidation reject vanished goals, changed chains and stock-satisfied demands, while unresolved surveys return UNCERTAIN. All **166 focused tests passed**. The original full run at `0fbc61d` then passed **2,744 tests: 2,737 passed, 7 environmental skips, zero errors/failures**, with source fingerprint `8dcd42e37885f9579ab787e9959577ea7da2bbc2d3219b5c3d1846ae33afe206`. Its immutable evidence is solver `.local-data/review/pw03-pw04/full-0fbc61d-results.json` and `full-0fbc61d-selection.json`.

The original solver checkout was fast-forwarded to the correction and rebased onto documentation-only `origin/main` at `d202dc3`; final code candidate **`dc810c8288e1c72e09b667111e3ed7e9aa99ebde`** has exactly the same production/test/design tree as focused-tested `ddd7afd`. The runner selects a full fallback for the final shared public-rule addition, so the earlier broad result is not final acceptance. Validation-only brief `.local-data/devin-briefs/pw03-pw04-final-validation.md` is ready for `absorbing-vicuna` once the Main evidence-correction worker finishes. No further code edits are assigned; return actual command results, final revision/fingerprint and concise failure evidence. The lead retains acceptance and integration. Both solver checkouts are clean; all code remains unpublished.

## Focused validation

Cover multiset allocation at different tiers, un-splittable high tiers, protected progress, zero-cost goals, uncertain finite capacity, and the documented mixed-output estimate. Exercise the shared validator against permitted and forbidden actions; PW04 owns complete decision-sequence replay.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Reviewed estimator/allocator/validator implementation, example ranking diagnostics, uncertainty limits and focused test results. PW04 consumes this exact implementation; the executor later calls the same validator.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.

## Implementation review — correction batch 1

**Disposition: Fixing findings; not accepted.** Lead reviewed the full solver production diff at `a9f79ae00592c71b8ad895a4b8709fc7a0274602` (PW03 commit `4abc8fd`, PW04 commit `a9f79ae`). The lead then rebased the clean, unpublished two-commit branch onto fetched `origin/main` at `cf171fdb4110093ccc29ce3f1f9c1491e8936d3c`, without conflicts. New candidate baseline: `b868a5f646928dc83cd146da6720ad87b105d2e8`; the solver content is unchanged by this rebase.

The lead independently passed all **129 focused policy/validation/planner tests** using the isolated Python 3.13 validation environment. Those tests do not cover the counterexamples below. The worker's broader run reported 2,710 tests with 14 errors from missing current RapidOCR because it used global Python; it is **failed evidence**, not an environmental waiver. Its selection/results remain in the solver worktree's `.test-impact/`. A corrected final-candidate affected run is required after fixes, using the explicitly supplied interpreter.

| Finding | Reviewed owner and concrete failure | Required correction / proof |
| --- | --- | --- |
| S1 | `policy.py` / `goals.py`: a clipped order is silently discarded; an unknown reward category can change which ready card should win; an unread secondary quantity on a third tied contender never triggers inspection. | Distinguish known ineligibility from relevant missing knowledge; inspect every contender whose unread facts can change the decision, using the canonical category-ordered reward comparison. |
| S3 | `effort.py` / `rules.py`: a lower chest order consumes Food 3 needed to feed the primary goal's Trap. When Food 3 is itself an exact requirement, it is also credited as feed and no additional food-production target is created. | Allocate exact requirements and selected recipe ingredients from one multiset; share that result between estimates, reservations and action targets. Prove protection and the extra-feed production sequence. |
| S4 | `effort.py` / `rules.py` / `planner.py`: Pot 4 cannot start the reachable missing-Bowl-5 path toward food. Repeated finite Bowl construction reuses the same on-board parts without charging additional acquisition energy. | Trace supported producer prerequisites and finite reconstruction from remaining stock, including acquisition energy or honest uncertainty. Replan after outcomes; retain the additive advisory estimator. |
| S5 | `goals.py`: `energy=None` is treated as certain and outranks a visibly available finite producer. Two uncertain finite paths use speculative reward/energy ratios instead of the approved reward-quantity tie-break. | Separate known estimates from absent/uncertain estimates. Cover unavailable Animal production versus available Fishing Tool, and lasso quantities 1 versus 2 with unknown remaining capacity. |
| S6 | `effort.py`: Normal Fruit 1 x2 plus inactive Fruit 2 can build Fruit 3 through a merge then activation, but the goal is priced as positive production energy. | Recognize the attainable free sequence without double-counting stock or consuming exact lower-tier demands; prove ranking against a positive-cost competitor. |

PW04 owns [S2 and planner sequence proof](PW04_ONE_STEP_SOLVER.md#implementation-review--correction-batch-1). This is one coherent correction batch in the same worker, not separate parallel diagnoses. No runtime APK/Lua access was found in the reviewed solver package; it consumes the accepted packaged catalog.

### Reproduction and continuation

- Assigned worktree: `C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-solver`, branch `codex/pet-workshop-solver`.
- Synthetic lead reproductions and captured outcomes: `.local-data/review/pw03-pw04/lead_repros.py`, `lead-repros-a9f79ae.jsonl`, `lead-extra-a9f79ae.txt`. The extra file supplies the corrected failing uncertain-effort example (Sea Creature 4, item 41104) and competing unknown-category example. These are offline typed-state evidence, not game observations.
- Turn 001 ended `incomplete`, exit 0, with committed code and `writers_stopped: true`; its transport status does not establish implementation acceptance or a specific model failure. The lead inspected the saved diff and bounded evidence before resuming.
- Correction owner: `absorbing-vicuna`, run `.local-data/devin-implement/pw03-pw04`, turn 002. Delta brief: `.local-data/devin-briefs/pw03-pw04-review-fixes.md`. Expected return: `.local-data/review/pw03-pw04/fix-handoff.md`.
- Tests must run from the assigned checkout using `C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-castle-identity-plan/.local-data/pw-validation-venv/Scripts/python.exe` (RapidOCR 3.4.5), followed by `tools/run_tests.py affected --base cf171fdb4110093ccc29ce3f1f9c1491e8936d3c --explain` on the final committed candidate. Preserve final revision/fingerprint and compact results; let a justified full fallback finish.
- No live validation is needed for these pure rules. Main remains unavailable for the later game-facing packets until the user releases it. PW02 and PW06 can continue independently.

### Recovery and revised correction ownership

Turn 002 was interrupted when all three Workshop worker/monitor processes disappeared around 2026-09-17 01:34 UTC; cause unestablished. No correction source edits had been saved. Lead verified absent local writers/tests and the existing native session ID, preserved `turn-002/state-before-host-recovery.json`, and repaired the stale running record. The original solver commits were rebased without conflicts onto accepted main `4f1e119`, producing candidate baseline `32197aae13b4bc754acc28bf617e8a25fee3c9bb` with unchanged solver content.

Same session `absorbing-vicuna` resumed as **turn 003**, supervisor 51088, with native SWE-2 Max readiness confirmed. The bounded output still showed unresolved joint-allocation design, so the lead now owns S3/S4/S6 instead of dispatching another broad recipe-design iteration. The worker owns concrete routine S1/S2/S5 corrections and focused regressions, then returns a committed delta at `.local-data/review/pw03-pw04/routine-fix-handoff.md`. Delta brief: `.local-data/devin-briefs/host-recovery.md`. Broad final-candidate validation is deferred until the lead's recipe changes are integrated; prior 129 passing tests do not resolve these findings. No packet is accepted.

Main's later availability is now supplied by the timed release in the roadmap. It does not change this pure package's offline scope or authorize a worker to connect to the game.

### Turn 003 independent review and lead corrections — 2026-09-17

Handled native result: `.local-data/devin-implement/pw03-pw04/turn-003`, `exited`, exit 0, `writers_stopped: true`, with a recognized final response. Worker candidate `761837e6817b818f5227bf0ba02dc3d8ade11777` scoped itself to S1/S2/S5; the lead inspected its actual production/test diff and independently passed its **146 focused tests** with the required interpreter. The worker did not claim S3/S4/S6 completion.

The lead reproduced a remaining S1 defect: an unfinished lasso primary with two surplus-ready chest competitors still submitted the known-quantity card while the other's quantity was unread. The lead corrected this using the same ranking comparison and one canonical surplus-quantity check. For S2, the lead added actual `validate_intent` gating to every mutation candidate, beyond the worker's repaired individual preconditions. S5's absent/uncertain estimate ordering passed review.

Lead commit **`efac6de`** additionally resolves S6: reserve exact requirements together, then traverse free merge/activation recipes from actual Normal and inactive stock, allowing a Normal partner to be built first. Failed recipe branches restore the per-goal pool. New regressions prove free-goal preference followed by merge→activation→submit, protect an exact lower-tier demand, and inspect the unread ready-secondary reward. **150 focused policy/validation/planner tests passed**, and `git diff --check` passed. Evidence summary: solver `.local-data/review/pw03-pw04/lead-review-efac6de.json`.

**Still fixing, not accepted:** S3 joint producer/feed ingredient allocation and S4 reachable producer reconstruction/finite acquisition pricing. Broad final-candidate testing waits for that cohesive lead-owned batch. Worker `absorbing-vicuna` is idle; no solver commit has been pushed or merged to main. This pure solver work used no live target.


### Execution record — 2026-09-16

- Status: **Delegated**, not accepted. Foundation implementation `14b7d68` is reviewed/tested and pushed; worker base `91afce6f9a817129f2e205b9479043744c4ca300` adds its acceptance record only.
- Scope: Pure effort/allocation/ranking/reservations and shared validator. The same worker may continue into PW04 only after its focused policy checks pass; one combined independent lead review follows.
- Checkout/branch: `C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-solver`, `codex/pet-workshop-solver`.
- Native Devin session `absorbing-vicuna`, run `.local-data/devin-implement/pw03-pw04`, turn `001`. Startup confirmed with `swe-2-max`, expected base and native steering/cancellation controls.
- Briefs: worker `.local-data/devin-briefs/pw03-pw04-solver.md` and `pw-wave-common.md`. Use the explicit dependency-correct Python environment named there; global py/shared .venv lack current rapidocr. APK/extracted Lua remain offline references only.
- The existing lead monitor registered this run and the native completion callback targets this coordinating task. Lead owns independent review, fixes, applicable final-candidate live proof, integration and acceptance.
- Reviewed/tested result revision and acceptance evidence: pending handoff.
