# 07 — Finish the remaining cohort's entry inventory before broad implementation

> Supporting V44 case study from the first planning pass. The [velocity roadmap](README.md) and [cause assessment](00_ROOT_CAUSES.md) supersede its priority and current-status assumptions. Reconcile historical candidate, ownership and policy notes before execution; this document is not a live assignment.

Priority: lightweight preparation before new route dispatch. Owner: V lead with the existing feature owners. Review coverage: §4A, §3 geometry limitations, §5 complete packages. No fresh live access is needed to start.

## Current state and intended artifact

The repository already has canonical target IDs/actions in `building_catalog.py`, eligible slot semantics in `home_city_slots.py`, feature ownership in [BUILDING_MENU_COVERAGE](../../BUILDING_MENU_COVERAGE.md), and evidence in [E3–E5](README.md#evidence-index). The gap is a reconciled entry contract for the remaining cohort, not another geometry extraction or building-name list.

Add a scoped **remaining-entry behavior** section to existing `docs/game-reference/workflows/home-city-slots.md` and link the current route rows maintained by 11. Keep build-scoped behavior/provenance in that tracked note; keep mutable candidate/worker/results in the existing ignored ledger. Do not duplicate the live status table in both places.

## Inventory to settle

| Cohort | Body action / potential side effect | Missing facts and action |
|---|---|---|
| Bank | Direct panel or menu; separate Auction/claim/deposit controls | Current menu/direct condition, measured controls and return; 02 |
| Watchtower | Body menu before information panel | Native menu/selector/panel/return; 02 |
| Hall of War | Initial panel rendering; deeper rally/formation separate | Full body and holdout, public route; 03 |
| Recruiting Center | Statistics/support panel in recovered build | Current occupant and endpoint; do not inherit barracks restriction; 03 |
| Infirmary | Initial information requests; explicit healing actions separate | Current occupant/panel/return; 03 |
| Four military types | Potential automatic completion collection | Preserve read-only refusal and implement explicit entry under recorded non-Main policy; 04 |
| Five resource types | Body handler may harvest same-type family | Shared effect-aware path, recognition and collect-then-open behavior; 05 |
| Trap Workshop | Conditional automatic trap collection | Occupancy, truthful effect and runtime path under existing policy; 06 |

## Steps and acceptance

1. **Reconcile evidence, not labels.** For every row record canonical ID, eligible/fixed slot, body→menu→panel sequence, possible automatic side effect, current read-only admission behavior, known return contract, build/date, confidence and provenance. Mark absent facts unknown. Use the already reviewed consultation; commission additional research only for a named unanswered question that changes implementation.
2. **Resolve material conflicts explicitly.** Source behavior from APK 5.0.203 is build-scoped. When a later authorized observation disagrees, retain both facts and update the current workflow implication. Do not overwrite the recovered finding as if it were never true, or assume the installed build matches it.
3. **Assign one code owner for admission knowledge.** Reuse `building_catalog.py`'s military predicate and its consumers in `open_building.py`, `read_only_policy.py` and `navigation_core.py`. Design one smallest shared entry-effect representation needed by the three observed collecting families, migrate consumers and remove duplicated predicates/lists. Reconcile `OpenBuildingPolicy`/workflow effects and the existing capability boundary once, as specified in 04; 05/06 consume it. Do not add a speculative all-game policy engine or infer side effects merely because a catalog lists a collection action.
4. **Gate broad route dispatch on resolved inputs.** Each package names current body evidence, intermediate controls, endpoint, return owner and policy/capability binding. [E8](README.md#evidence-index) records the superseding non-Main resource authority; do not keep the original collection question active. A capability rejection is a runtime implementation dependency, while Main or a newer explicit restriction remains a separate authority boundary. Missing UI facts become discovery deliverables, not implementation guesses.
5. **Publish stable knowledge when confirmed.** Add provenance/date/build/confidence and automation implications to the existing workflow note. Use 08's package contract and 11's route records for execution status.

**Done when:** every remaining target has an explicit entry-effect/menu/return disposition; assigned packages reference it; collection-sensitive behavior is not inferred for unrelated types by name; the recorded non-Main policy is consumed without weakening read-only/runtime contracts; all source-supported claims carry build limits; current UI unknowns have one bounded next observation and owner.

Validation for the inventory document is reference/target-ID review plus `git diff --check`. No unit suite or new emulator observation is needed merely to consolidate known evidence. Any resulting runtime admission change is implemented and tested in its owning 04/05/06 package, with affected API consumers retained.
