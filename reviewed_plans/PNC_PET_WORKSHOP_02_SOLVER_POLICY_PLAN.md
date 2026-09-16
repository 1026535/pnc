# Pet Workshop 02 — Pure solver and gameplay policy

Date: 2026-09-16. Design plan; [current packet status and next assignment](PNC_PET_WORKSHOP_ROADMAP.md).

## 1. Outcome, dependencies and owner

Given a typed Workshop state and the recovered catalog, propose one useful permitted action with an understandable reason. Favor the user's reward hierarchy and expected reward per additional energy, preserve higher-priority progress, and replan after observed outcomes. This is a practical goal-directed solver, not a claim of globally optimal stochastic play.

Read the [shared contract and agreed decisions](PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#2-agreed-behavior-shared-by-the-three-plans). They are canonical for this plan set. [Plan 03](PNC_PET_WORKSHOP_03_EXECUTION_INTEGRATION_PLAN.md) executes decisions through the existing runtime; this package contains no image handling, filesystem persistence, clock reads, ADB, BlueStacks or network calls.

**Dependency:** lead-accepted Plan 01 packet PW01, including catalog/models and `plan_next` / `validate_intent` signatures. The solver worker can implement and qualify this package entirely offline while the recognition worker completes PW02. Do not define substitute item/order/state models to start before PW01.

Use a focused `app/automation/pet_workshop/` package. Keep policy/eligibility, recipe effort and decision selection as cohesive modules only where their responsibilities warrant it. The catalog, shared models and source facts remain owned by Plan 01. One `validate_intent` implementation supplies the rules used by both the planner and executor revalidation.

## 2. Policy and planning semantics

### Orders, ranking and reservations

1. Recognize orders of every size, but admit only requirements whose quantities sum to exactly two. Unknown requirements or incomplete cards do not qualify. A repeated `{item: 2}` is eligible; `{item: 3}` and `{a: 2, b: 1}` are not.
2. Classify an eligible order by its highest recognized nonzero reward category in the agreed hierarchy. Lower-category rewards do not compensate for a worse category. Unknown reward facts needed to rank an order request inspection rather than a fabricated score.
3. Within that category, ready orders and unfinished orders achievable entirely through free, qualified merges/activation/feeding both have zero additional production-energy cost. Rank this zero-energy class ahead of positive-cost goals: larger primary reward first, then fewer remaining non-production actions, lower-category reward quantities and a stable observed-order tie-break. Prefer an actually ready order when the preceding comparisons tie. For positive-cost goals, maximize primary reward quantity divided by estimated additional gross production energy, using cross-products rather than an arbitrary epsilon. Equal ratios prefer less remaining effort, then the stable reward/order tie-break. Never divide by zero or invent an energy charge for a free merge.
4. Choose one primary goal from the highest available reward category using that ranking; it may be ready or unfinished. A ready primary goal is submitted first. While the primary is unfinished, a lower-ranked ready order may proceed under the reservation rule below, including a lower-ranked order in the same category. Goals may span runs; do not abandon a Wood 10 goal merely because the current bar cannot finish it. Recompute from the actual board on a later run, retaining useful intermediate pieces in the game rather than replaying a stored action queue.
5. Reserve exact required items first, then useful lower-tier ingredients needed to build the remaining requirement quantities. Allocate the largest usable intermediates first so a completed coconut is protected while unrelated fruit remains available. A higher-tier piece cannot be split to satisfy a lower-tier demand.
6. A ready lower-priority order may be submitted only from the remaining unreserved multiset. Apply the same test to merges, feeds and recycling that could consume reserved progress. The chosen goal may consume its own reservations through an action that advances that goal; otherwise protection would prevent all progress.
7. Reservations are quantities by item ID, not guaranteed surviving squares. The game chooses duplicate pieces for submission. If three identical Normal pieces exist and one is reserved, consuming two through another permitted order preserves one regardless of which cells disappear. Unknown/non-Normal items are not counted as spendable stock.

The reservation result is an ephemeral derivation of the current board and chosen goal, not a second persistent inventory. Report the selected goal, missing quantities and protected quantities in decision diagnostics. Do not create a generalized resource-lock service.

### Estimated effort: small, explicit and advisory

Use the catalog's merge DAG and weighted outputs. The estimate selects among plausible goals/producers; it never authorizes a gesture or supplies a predicted drop.

- Expand missing targets through binary merge predecessors and allocate current pieces without double-counting. For a chain whose next item takes two copies, a usable tier contributes its corresponding base-unit value only toward demands at that tier or above. Preserve separate tier demands so a bulk base-unit total cannot silently consume a required low-tier item.
- Compute each available generator's expected useful output per energy from its weighted drop group and supported mode. Ignore outputs above a demanded tier when they cannot be split back down. Count zero-cost manual merges as work, not as energy spend.
- Add per-demand production estimates as a conservative ranking proxy. When one generator supplies several demanded families, label the resulting estimate conservative because useful byproducts may satisfy both requirements during the same run. Do not present `max(deficit/yield)` as an exact joint expectation: it is only a lower bound and can inflate a goal's apparent efficiency. For a synthetic generator emitting A or B with equal probability, one of each has isolated costs 2 + 2 = 4 in this proxy, while its exact joint expected draw count is 3; retain that example as the estimator's documented limit. A sampled item is allocated once, and subsequent planning credits its actual contribution to the remaining requirements. No joint stochastic state-space solver is required for this release.
- Compare directly available producers and useful reachable producer upgrades. Include the ingredients needed to create/feed a required producer; do not treat a missing Bowl 5 or Food 3 feed as free. For a newly constructed finite producer, its configured capacity can inform an amortized estimate with provenance. For an existing finite producer with unknown remaining uses, do not grant it a fresh full lifetime in the estimate.
- Unknown remaining finite capacity produces an explicitly uncertain effort estimate for that path. Known estimates rank before unknown estimates within the same reward tier; use reward quantity and a stable tie-break when all relevant estimates are unknown. This affects efficiency preference, not eligibility or the legality of one visibly available production action.
- Do not credit hypothetical future recycling refunds, regeneration, level-up rewards or unclaimed inventory as guaranteed budget. Re-read those gains after they occur. This avoids negative-cost loops and unsupported energy guarantees.
- Keep caches limited to immutable catalog recipe/drop calculations and one planning invocation. No Monte Carlo simulator, reinforcement learning, whole-board permutation search, remote solver service or runtime tuning framework is required.

Accept this approximation through scenario tests and clear diagnostics. Add more sophisticated estimation only if later recorded choices demonstrate a material defect, not to obtain a theoretical optimality claim.

### Generator upgrades, feeding, finite production and activation

- A generator upgrade is an ordinary matching-ID merge with a valid successor. Permit it when the resulting producer advances the current goal or provides the capacity needed for it. Never merge past a required ingredient tier or mistake two maximum-level pieces for an upgrade.
- A finite producer is a producer whose disappearance/transformation is a supported possible exhaustion result. Its configured maximum is static information; the planner does not invent a current counter. Replan from the new board when it expires and build another only when that advances an eligible goal.
- Feed only a visibly feed-locked producer with the exact catalog ingredient, using an unreserved copy or an explicitly allocated part of the primary goal's production recipe. Never treat a feed as a generic same-icon merge or use arbitrary inventory food. The logical Feed intent names the food and generator cells; Plan 03 owns the qualified food-to-generator gesture.
- Activate only a known inactive/grey piece with a matching Normal piece and a valid merge successor, when the activation advances a goal, required producer or useful board-space recovery. A level-locked square and a purchasable bubble are different states and do not qualify.
- The catalog's Auto type does not prove an automatic generator is currently supported, and it is unrelated to permission to use premium Auto Fusion. Ordinary automated manual gestures remain the execution method.

### Level-linked progression and blocked goals

Use the [reviewed progression evidence](PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#workshop-progression-and-order-selection). Do not add a strategy that switches production to a lower-ranked unfinished order solely because the preferred chain is hypothesized to be locked. The existing exception for a lower-ranked **ready** order that preserves reservations remains unchanged.

Determine current progress from observed usable items and supported recipes. Apply a qualified feed, ordinary/producer merge, inactive activation or producer reconstruction when it advances the goal; handle cooldown through the existing bounded wait. Neither a missing current producer nor an unknown finite-use count proves a permanently locked chain. Only when no permitted useful progress or bounded information acquisition remains should the existing known-blocked/unknown result end the attempt. Orders supplied by the game remain representable even when catalog/level expectations disagree; never fabricate prerequisite completion, hidden order type or server IDs to make them fit.

### Full board and recycling

Before production, establish at least one usable empty square from current facts. If space is blocked, prefer a permitted ready submission or useful merge/activation/feed that frees space while preserving the primary goal. Do not add arbitrary rearrangement: swapping positions does not create capacity.

The only recycling candidates are Normal, unreserved Fruit 5 or Statue 5, selected only when the board is confirmed full and no useful permitted space-making action is available. Recycle one piece, observe the result, then replan; never batch-delete. If both qualify, prefer the candidate with lower usefulness to currently eligible orders, then the stable item/cell tie-break. The user accepts either allowed item; do not introduce an invented permanent stock floor.

Do not manufacture a recycling loop as a new reward objective. A useful merge that consolidates surplus fruit/statue pieces can free space, but cannot consume ingredients reserved for a higher-priority order. Recycling is unavailable at observed zero even if it could restore energy. If no allowed candidate exists, return a board-blocked stop with the actual remaining energy.

## 3. Decision order and revalidation

Implement a deterministic decision sequence; no persistent action queue:

1. **Terminal evidence first:** if energy is reliably zero, Stop immediately. If the surface is an unexpected refill/purchase/unknown modal, return the corresponding stop or safe inspection need; never propose a board mutation through it.
2. **Establish required facts:** request bounded inspection/survey for missing order contents, relevant item/status, selection or coverage. Do not replace unknown with empty, zero or ready. A nonparticipating unknown need not block a decision whose required facts are established.
3. **Select and protect the primary goal:** use the ranking and quantity-allocation rules above. An incomplete order survey cannot justify claiming the globally best reachable order.
4. **Submit a permitted ready order:** submit the primary if ready; otherwise take the best lower-ranked ready order only after reservation validation, retaining the unfinished primary as the focus for subsequent progress.
5. **Take useful non-production progress:** finish required ordinary merges, producer upgrades, grey activation or feeding. Prefer the action nearest a missing target; ties favor freeing usable space, then stable source/destination IDs. Do not merge an exact completed ingredient into the next tier just because a pair exists.
6. **Handle capacity:** when confirmed full, try useful permitted space-making work, then one restricted recycling candidate, then Stop(board_blocked).
7. **Produce:** select the known available generator with the best expected progress toward the primary goal per energy. If it is known unselected, propose Select first; once selection is observed, propose Produce. Reobserve and replan after every output.
8. **Cooldown or inability:** if a supported useful producer is cooling down and no other useful action exists, return Wait with the agreed 60-second ceiling. The executor owns elapsed monotonic time for that continuous episode and returns Stop(cooldown_timeout) when exhausted. Other unknown/unsupported dependencies request Inspect or Stop with their specific reason.

No eligible goal is a distinct stop reason; do not complete a three-piece order or spend energy randomly to force the bar to zero. If three-piece rejection eventually affects server order assignment, record that observed limitation without silently changing the user's policy.

`validate_intent` uses the same canonical predicates as this sequence: relevant known item/status/selection, recipe/feed identity, quantity reservations, order eligibility/readiness, energy, space, restricted recycling and surface. Plan 03 adds freshness, target identity, authority and evidence-of-result checks at the execution boundary. It must not reimplement reward ranking or quantities.

### Order knowledge and refresh

The planner consumes a survey of the **currently reachable UI orders**, not the entire packaged order list as if it were active. Requirement/reward signatures help comparison but are not unique permanent IDs. Card coordinates are absent from the solver.

Plan 03 must complete the initial strip survey and refresh order-dependent state after mutations that may change order readiness, display or membership before selecting the next order-dependent mutation. Reuse already decoded templates/catalog data and narrow OCR; do not persist stale clickable cards. The first implementation may conservatively resurvey after each production/merge/feed/activation/submission/recycle. Reduce survey frequency only when current evidence supports an invalidation rule that preserves the selected policy; do not hide this optimization inside a second planner.

`Inspect` and `Wait` are requests to the execution owner. Repeated failure to obtain new information ends the bounded attempt; the planner does not schedule retries or future jobs.

## 4. Separate implementation packets

| Packet | Deliverable |
| --- | --- |
| [PW03](pet_workshop_packets/PW03_EFFORT_RESERVATIONS_POLICY.md) | Effort estimates, allocation, ranking, reservations and shared legal-action validation. |
| [PW04](pet_workshop_packets/PW04_ONE_STEP_SOLVER.md) | One-step planner and deterministic typed scenario replay. |

[PW03](pet_workshop_packets/PW03_EFFORT_RESERVATIONS_POLICY.md) starts after [PW01](pet_workshop_packets/PW01_SHARED_CONTRACT_CATALOG.md); [PW04](pet_workshop_packets/PW04_ONE_STEP_SOLVER.md) consumes its tested policy implementation. The same worker may complete both with one combined lead-review handoff; a separate worker receives the accepted PW03 commit. This lane is independent of [PW02](pet_workshop_packets/PW02_RECOGNITION_CONTROLS.md) recognition. The lead reviews the actual solver decisions before [PW05](pet_workshop_packets/PW05_SCREENSHOT_PROPOSAL_MILESTONE.md) consumes them; this is a review gate, not another coding packet. See the [common handoff and review workflow](PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review).

## 5. Required scenarios and acceptance limits

| Scenario | Required result |
| --- | --- |
| Saved ready three-coconut chest order | Ineligible because total quantity is 3; no SubmitOrder. |
| Synthetic two identical ingredients | Eligible only with two known Normal usable copies and a permitted ready order. |
| Saved Wood 10 + coconut lasso goal | Eligible but not ready; protect coconut and useful Wood progress, favor Tree output for the missing chain. |
| Ready lower-tier order using the reserved coconut | Reject that submission. An otherwise equivalent order using only true surplus may proceed. |
| Three duplicate pieces, one reserved, two requested elsewhere | Permit consuming two when all other rules pass; verify preservation by quantity, not chosen cells. |
| Same reward tier, different quantity/effort | Choose greater estimated reward per energy; ready and free-merge-only goals are ranked without division by zero. A bigger lower-tier reward never overtakes a lasso merely through weighting. |
| Existing high-tier item with lower-tier demand | Do not count it as splittable stock; preserve exact required lower-tier pieces from over-merging. |
| Shared Tree fruit/wood outputs | Label the additive effort proxy conservative; test the synthetic A/B 50:50 example and ensure each actual item is allocated only once before replanning. |
| Known unselected/selected Tree 4 | Select first only when needed, then Produce. A selected reward piece never receives a generic inspection tap. |
| Finite producer expires earlier than its configured maximum | Do not invent remaining stock or retry the vanished producer; update the missing-production path. |
| Feed-locked Trap with exact Food 3 / wrong food / reserved food | Permit only the exact qualified, policy-allocated feed; reject wrong/otherwise protected ingredients. |
| Matching grey piece / bubble / level-locked square | Only the supported matching inactive activation qualifies. |
| Full board with useful merge versus allowed recycle candidate | Prefer permitted useful space-making work; otherwise recycle one unreserved Fruit 5/Statue 5; never any other item. |
| Full board without permitted recovery | Stop(board_blocked), keeping positive energy distinct from zero. |
| Observed zero with a ready order or recyclable piece | Immediate Stop(zero_energy), with no submission or recycling. |
| Cooldown, no useful alternative | Wait request capped at 60 seconds; no paid acceleration or repeated fresh 60-second windows. |
| Partial order, unknown relevant item/status, unexpected surface | Inspect or Stop; no speculative mutation. |
| Level-linked order with a missing/feed-locked/exhausted producer | Use an existing permitted feed/merge/activation/rebuild path when available; otherwise inspect or return the existing blocked/unknown outcome. No fabricated level guarantee or new lower-ranked production objective. |
| Passive regeneration or recycling gain | Use the newly observed energy; do not infer spend from session net difference or force an initial-energy tap count. |

Run focused solver tests with the repository runner, then `py tools/run_tests.py affected --base <accepted-base> --explain`. Shared-model changes return to PW01's owner and trigger the affected contract tests. Full testing is warranted when the runner selects it or at final shared integration; no live energy is needed to qualify this package's pure rules.

Offline acceptance proves the policy and responses to supplied states, not the accuracy of every screenshot label or the game's current server transition. Exact drop weights, hidden finite capacity and unseen order assignment remain evidence limitations, handled through observed execution and the bounded live gates in Plan 03. Do not promise that every allowed run reaches zero when no useful permitted action exists.

The worker follows Plan 01's common architecture and the [roadmap dispatch workflow](PNC_PET_WORKSHOP_ROADMAP.md#worker-dispatch). A Devin coding worker or Luna xhigh agent can complete PW03/PW04 independently from the recognition worker after PW01; the lead owns review and acceptance. This plan does not start live play, create schedules, alter account configuration or authorize unrelated cleanup.
