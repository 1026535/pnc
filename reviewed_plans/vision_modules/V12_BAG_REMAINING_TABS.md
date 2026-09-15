# V12 — Remaining Bag tabs on the supported layout

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V09. Deliverable: the small remaining Bag card family, with an explicit capture-derived tab inventory.

## Evidence gate and scope

The tour qualified Resource and captured Speedup/Treasure; it did not establish the names or semantics of every remaining subtab. Do not assume a “Military”, “Misc” or artifact tab exists from memory. This packet covers only remaining tabs that share the Bag card/detail structure. Gear, Relics and other standalone feature inventories are separate work.

## Implementation

1. Read current Bag profiles, screenshots and enum/selector entries, then capture missing visible tab labels through a bounded read-only route if needed. Record each tab as supported, empty or unqualified.
2. If there are more than two materially different remaining card/detail families, split this packet into named feature packets before coding. A single Luna assignment must not become “all inventory UIs”.
3. Reuse V09's tab, viewport and card geometry. Add family-specific item identity using artwork plus observed title/variant and quantity. Items with unknown semantics remain unresolved; do not squeeze them into Resource/Speedup models.
4. Qualify one common non-spending detail layout per included family, with current owned controls and close destination. Publish only fields consumed by inspection or an existing feature contract.
5. Wire both publishers and verify that switching tabs clears prior-family rows and actions.

## Acceptance and proof

Add a captured test family named after the actual included tabs. Run real OCR planning through both publishers; assert tab identity, complete versus clipped cards, item variant/quantity and correct return. Use empty-state evidence only if available, not as an excuse to manufacture inventory changes.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One testing core-runtime route visits the included tab or shared family, inspects one safe detail when present, and returns Home. Save the discovered tab inventory, typed rows and source/return frames. Stop before Use, Open, Redeem, Equip or a selection confirmation. If the current layout contains no additional tabs, finish with evidence and no unnecessary production code.
