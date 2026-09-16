# V04 — Institute, Development research and shared research parsing

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01; V02 for automatic Home entry. Coordinate with [feature 01](../PNC_CORE_REMAINING_01_RESEARCH_LIVE_PLAN.md). Deliverable: one complete non-spending node-inspection route and reusable research facts.

## Current state and ownership

`app/pnc/vision/pnc_observation_enricher.py` owns `_build_research_tree_additions`, Development label/candidate helpers and `_build_research_queue_popup_additions`. `ocr_region_plan.py`, visual profile/control data and `domain/observation.py` own the associated inputs/publication. Research callers live in `app/automation/research.py` and `tasks/research_task.py`; preserve their action/queue contracts.

Tour09/10/12 show five upper nodes, a detail popup and lower scrolled nodes. Training Speed I, Fast Heal I and Food Output I are omitted after scroll; fully visible Miraculous Survival I is incorrectly clipped. Detail variants and queue recognition already have captured tests.

## Implementation

1. Recheck newer feature01 work, then define one category-aware research producer. Extract the changed research functions together if needed; retain one canonical catalog/typed representation.
2. Use icon/card/label geometry to discover visible nodes within the real scroll viewport. OCR only node labels, levels and requested state regions. Keep partial/ambiguous nodes explicitly unresolved; do not discard small edge fragments or let the fixed header become part of the actionable viewport.
3. Publish category plus canonical node ID, measured action bounds, observed level/max level, selection and lock state when visible. Unknown or duplicate labels do not acquire an action. Tree position alone cannot prove identity after scroll.
4. Parse the selected detail separately: verified node/category, level/effect, explicit prerequisites, ordinary cost/time and the distinct premium Research Now control. Represent missing facts as unknown. Preserve Research Queue identity and distinguish observed active/idle evidence from merely missing a timer.
5. Wire both publishers and existing consumers. A node click must verify the matching detail. Reacquire after scroll and on return; do not let a previous node's facts survive selection.
6. Keep research start, budget and receipt handling with feature01. This packet completes visual readiness and non-spending navigation only.

## Acceptance and proof

Target `test_research_tree_visual_controls.py`, `test_research_captured_variants.py`, `test_research_queue_navigation.py`, `test_research_observation.py` and research workflow contracts. Replay upper/scrolled/detail/queue source captures through both production paths with real region planning; verify the three omitted nodes, corrected clipping and distinct ordinary/premium controls.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Home → Institute → Development → one bounded scroll → a complete node → matching detail → tree → Home. Optionally inspect an already-visible queue without changing it. Save frames, typed node/detail facts and navigation trace; stop on unknown node/detail or unavailable queue. Never press Research or Research Now for proof.

## Reviewed implementation coverage, September 16

Implemented on `codex/vision-v04-research` (result `9b85351`, rebased onto accepted V09 `32a0349`), reviewed by the lead and corrected in one R1–R5 batch. Baseline evidence: package `com.global.tmslg` 5.0.203/233 (September 12 inspection), September 15 `vision_live_tour_20260915` testing captures at 900x1600 (tour09 upper, tour10 detail, tour11 post-close tree, tour12 scrolled) and tracked 540x960 fixtures.

- `domain/research.py` owns the nine tier-I Development `ResearchNodeId`s, `ResearchNodeFacts`, `ResearchDetail` (typed food/wood `ResearchResourceCost`, times, premium gem cost and read-only button bounds, queue state/timer) and `ResearchQueueRow`; `vision/research.py` owns `ResearchContentProducer` geometry-first discovery.
- Detail profiles share `research_tree_node_detail`; the queue profile is `research_queue`. Both publishers bind typed detail/queue provenance (`frame_ref`, `source_screen`, `source_layout_id`) through the existing `observation_provenance` owner; contradictory pre-bound evidence is rejected and the canonical same-frame merge preserves the fields without cross-frame carry.
- `NavigationCore` opens one unique COMPLETE typed row and requires a fresh matching typed detail; scroll/close send one reviewed gesture each with no replay. `WorkflowContext.open_research_node` primes `_research_node` only on a measured TEMPLATE Start control. `ResearchTask` scopes its pending selection to `TaskContext.runtime_state` and promotes it only after the selected-source action yields a newer clear matching detail in the same capture session/epoch; a conflicting category fails and pre-existing or unrelated active panels stay read-only.
- Mutation ownership (Start authorization, exact budget, receipts, journal) remains with feature01/`CoreMutationBoundary`; premium geometry is read-only.

Lead review corrections (R1–R5): completed typed provenance publication on both paths plus replay serialization; separated read-only detail inspection from mutation selection proof and repaired the legacy task lifecycle; distinguished CLIPPED (partial/outside viewport) from UNREADABLE (contained tile, unproved icon frame) with no actions in either case; made tree/detail calls reuse one prepared matcher frame and one RGB array across glyph/frame helpers; added the portable real-capture acceptance suite (`test_research_captured_acceptance.py`, including the tracked `research_tree_scrolled.png` tour capture), provenance/merge regressions, navigation open/scroll/close tests and the scoped workflow note `docs/game-reference/workflows/research-development.md`.

**Remaining gate:** automatic Home entry still depends on V02. The supported non-spending route (Home → Institute → Development → one bounded scroll → a complete node → matching detail → tree → Home) is proved offline on saved captures only; the lead runs its bounded live proof after V02 entry is ready and before accepted merge/push. Active-queue layout and non-Development categories remain outside V04 coverage (V05–V08).
