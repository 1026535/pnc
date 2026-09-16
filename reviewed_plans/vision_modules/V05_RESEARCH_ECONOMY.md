# V05 — Economy research

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V04. Deliverable: Economy tree discovery, exact node selection and detail/return support through the shared research producer.

## Baseline and scope

Economy detail variants have captured recognition coverage in `tests/integration/vision/test_research_captured_variants.py`; this does not prove complete tree-node selection. Reuse V04's category-aware node/result contract, OCR planning and detail parser. Own only Economy catalog entries, profile/control variants, parser data and corresponding tests/callers. Do not clone the Development parser.

## Implementation

1. Inspect current captured Economy tree/detail evidence and newer Research work. Record supported visible nodes and layouts, not an assumed exhaustive technology catalog.
2. Register Economy category identity and node references. Discover card/icon geometry, then obtain canonical node identity and current level/lock facts from bounded regions.
3. Bind identical-looking icons and repeated names to category and displayed node information. If evidence cannot disambiguate a level/variant, retain an unresolved node instead of borrowing Development identity.
4. Use V04's shared detail semantics for costs, prerequisites, timers and ordinary/premium controls. Correct only Economy-specific layout differences.
5. Add navigation from Institute category selection through a currently complete Economy node to its matching detail and back. Refresh targets after scroll. Category support is not authority to start its research.

## Acceptance and proof

Extend the captured research variant tests with an Economy tree source frame, a different viewport or validation frame, and its matching detail. Both production publishers must agree on category/node identity and measured controls. A clipped node must have no action; a node from another category must not be published as Economy merely because its icon matches.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Institute → Economy → one available complete node → detail → Economy → Home. If scrolling is necessary, use the existing bound and reacquire once. Save source/post-selection frames, typed facts and trace. Stop before any research action or when the category is locked/unavailable. Report missing tree evidence explicitly; already-qualified details do not erase that gap.


## Lead acceptance — 2026-09-16

Accepted for the capture-derived subset through the shared category catalog,
ResearchContentProducer, both publishers and existing navigation/workflow owners.
Food Output I3/4 in a02dbcf6 and corrected Wood Output I1/5 in45be2a99; six evidenced nodes, including a newly complete Iron Harvest I on the independent holdout.

The active mega_old_acc castle was K157/NPC2/22. The matching detail, return
category and final Home were freshly observed with zero resource actions; leases
released and the existing instance was preserved. Full baseline, focused final
regressions, exact source frames and remaining limits are recorded in the
[shared category acceptance note](../../docs/game-reference/workflows/research-category-inventory.md#accepted-shared-category-implementation--2026-09-16).
Category support does not authorize Start or Research Now. Unseen variants and
unreadable fields remain unqualified.
