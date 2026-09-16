# V07 — Fortification research

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V04. Deliverable: Fortification tree and detail inspection through the same research contract.

## Baseline and scope

Fortification detail variants already have captured tests; node selection and scrolling need separate evidence. Own Fortification category/node references, its region/layout differences and relevant tests. The shared research producer, semantic model and navigation belong to V04's existing path.

## Implementation

1. Reuse saved Fortification detail evidence and inventory available tree captures. Establish the visible category identity before parsing its nodes.
2. Measure node/card regions, then read only the fields necessary to identify each node, displayed level and lock/prerequisite state. Support only the evidenced node set; do not populate visible facts from an inferred full technology tree.
3. Handle shield/wall/trap artwork reused by nearby nodes using category plus label/level evidence. Ambiguous identity remains non-actionable.
4. Reuse shared detail facts for ordinary cost/time, premium control and unmet requirements. Keep a locked node's inspectable detail distinct from eligibility to research it.
5. Complete category → visible node → verified detail → category return, refreshing geometry after any scroll.

## Acceptance and proof

Extend `test_research_captured_variants.py` and the shared tree tests with actual Fortification tree/detail captures. Both publishers must preserve category/node identity and current state. Use a locked node capture if already available to verify “inspectable” does not become “research eligible”; do not create that state through spending.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route on testing: Institute → Fortification → one complete visible node → matching detail → tree → Home. Save source/detail/return frames, typed results and trace. Stop on unavailable category, unknown node or an action boundary. No research, unlock or prerequisite upgrade is part of this proof.


## Lead acceptance — 2026-09-16

Accepted for the capture-derived subset through the shared category catalog,
ResearchContentProducer, both publishers and existing navigation/workflow owners.
Wall DEF I2/10 in a02dbcf6; seven evidenced nodes, including five observed padlocks. A lock is distinct from inspection permission and research eligibility.

The active mega_old_acc castle was K157/NPC2/22. The matching detail, return
category and final Home were freshly observed with zero resource actions; leases
released and the existing instance was preserved. Full baseline, focused final
regressions, exact source frames and remaining limits are recorded in the
[shared category acceptance note](../../docs/game-reference/workflows/research-category-inventory.md#accepted-shared-category-implementation--2026-09-16).
Category support does not authorize Start or Research Now. Unseen variants and
unreadable fields remain unqualified.
