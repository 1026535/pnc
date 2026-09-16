# V06 — Military research

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V04. Deliverable: supported Military research nodes, states, detail inspection and return.

## Baseline and scope

Military detail variants are represented in `test_research_captured_variants.py`; wider tree discovery is not established by that fact. Extend V04's canonical research producer/catalog and `ocr_region_plan.py` only for Military-specific needs. Keep shared parsing and mutation ownership unchanged.

## Implementation

1. Inventory saved Military tree/detail captures and current feature commits. Qualify category chrome independently, then measure visible node/icon/card regions.
2. Add canonical Military node entries for the evidenced set. Pair icon evidence with displayed label/level; similar troop artwork is insufficient to choose a node or tier.
3. Publish visible selection, level, locks and prerequisite text through V04's facts. Unsupported tier names, clipped edge nodes and uncertain icon matches stay unresolved with no action point.
4. Use the shared detail parser and distinguish the ordinary research control from premium Research Now. Verify selected detail identity against the requested category/node before a consumer receives readiness.
5. Wire category entry, bounded scroll if required, node selection, detail close and return using current navigation edges. Remove any touched duplicate Military parsing path.

## Acceptance and proof

Use real Military tree/detail frames through both production publishers, with at least one representative reused-icon or neighboring-node case from available captures. Assert correct category/node identity, viewport clipping, measured action bounds and unknown handling. Do not create an exhaustive troop-tier test matrix without evidence of layout variation.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One testing core-runtime route: Institute → Military → one available complete node → matching detail → tree → Home. Save the frame/observation pairs and action trace. Stop if the category is inaccessible or identity is ambiguous; do not unlock it, train troops or start research to produce a fixture. Record the supported subset and unavailable variants.


## Lead acceptance — 2026-09-16

Accepted for the capture-derived subset through the shared category catalog,
ResearchContentProducer, both publishers and existing navigation/workflow owners.
Siege ATK I2/3 in a02dbcf6; nine evidenced nodes, including seven literal MAX badges without invented numeric maxima.

The active mega_old_acc castle was K157/NPC2/22. The matching detail, return
category and final Home were freshly observed with zero resource actions; leases
released and the existing instance was preserved. Full baseline, focused final
regressions, exact source frames and remaining limits are recorded in the
[shared category acceptance note](../../docs/game-reference/workflows/research-category-inventory.md#accepted-shared-category-implementation--2026-09-16).
Category support does not authorize Start or Research Now. Unseen variants and
unreadable fields remain unqualified.
