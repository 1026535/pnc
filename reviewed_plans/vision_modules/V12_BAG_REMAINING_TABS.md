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

## Implementation coverage (worker, pending lead acceptance)

**Tab inventory established by evidence, not memory.** The lead's canonical
leased `mega_old_acc` run `20260916T130610Z_4b194a06` passed
Home → Bag Military → Misc → Home with zero item/spending actions
(`.local-data/devin-v12/live_inventory_registered/`). The actual five subtabs
are Resource, Speedup, Military, Treasure, Misc — exactly two remaining
families, both on the shared six-card Bag geometry, so no packet split was
needed. No standalone gear/relic UI exists on this screen.

**Typed identities.** `domain/bag_items.py` adds `MilitaryItemIdentity`
(kind, `duration_minutes`, `percent` required exactly for troop boosts) and
`MiscItemIdentity` (kind, `amount` required exactly for Lord EXP) to the
`BagItemIdentity` union; canonical keys carry every variant field
(`military:anti_scout:360`, `military:troop_size_boost:25:120`,
`misc:lord_exp:500`, `misc:pickaxe`). Same-art Anti-Scout 6h/12h variants are
distinguished by displayed duration; Lord EXP's `500` is the displayed
denomination, never the 2,915 owned count.

**Producer.** `BagItemContentProducer.tab_additions` reuses the V09 card
geometry and one bounded card read. Military names carry the `N-hr` duration
or boost percent; the bounded description confirms or supplies the remaining
field — name/description contradictions, missing descriptions on boosts and
unknown labels stay unknown. The accepted OCR backend systematically confuses
O/0 in this font (`Tro0p`, `B00st`, `F0R`, `ANTISC0UT`); tolerance is bounded
to the evidenced Military words only. Misc resolves directly from the
displayed label; the Lord EXP amount may be independently confirmed by the
description (`Adds N Lord EXP`), a conflict staying unknown.

**Observation-only boundary — recorded limit.** None of the 12 visible cards
carries a magnifier or any qualified read-only detail: all resolved
Military/Misc rows publish `no_action`, never `complete`; unresolved identity
is `unreadable`; clipped cards are `clipped`. `Use`, `Use in bulk` and
`Convert` are never inspection controls and are never promoted. No detail
route was added — Requirement 6's "inspect one safe detail only if present"
condition is absent, and this limit is recorded rather than manufactured.
`bag_item_inspection_supported` stays Treasure-only.

**Navigation.** `NavigationCore.select_bag_tab` already covers all `BagTab`
values: same-tab selection returns without a tap, and a cross-tab selection
requires a TEMPLATE-sourced measured control on the fresh frame. The lead's
qualified unselected-label anchors (`bag_subtab_military_unselected.png`,
`bag_subtab_misc_unselected.png`, floor .95, registry revision 4) publish the
measured points 450,236/810,236 on both production publishers — verified on
the tracked captures at native and 540x960 reference size.

**Publication and clearing.** Both `ObservationBuilder` and
`NavigationPerception` agree on all 12 rows including provenance; a
Military → Misc replay publishes only the current family on the second frame
(every fact carries `selected_tab`; no `military:` key survives onto Misc
rows). The enricher dispatches `BagTab.MILITARY`/`BagTab.MISC` to the
producer; Resource scanning and Speedup/Treasure behavior are unchanged.

**Validation.** `tests/unit/app/pnc/vision/test_bag_items.py` covers
same-art duration variants, boost percent/duration, O/0 confusion, dropped
leading digits, contradictions, model invariants and identity keys (37 pass).
`tests/integration/vision/test_bag_items_publication.py` adds
`bag_military_tab.png`/`bag_misc_tab.png` (tracked, run `4b194a06` frames
0032/0037 — same capture group, reference provenance) through real RapidOCR
on both publishers at native 900x1600 and a same-capture 540x960 resize:
exact identities/counts, `no_action`, no preview facts, provenance, measured
cross-tab TEMPLATE controls, and tab-switch clearing (10 pass, ~297s).
`BagTabSelectionTests` adds measured-control selection for both tabs
(14 pass). `py tools/run_tests.py group unit.app.pnc.vision` and
`affected --base origin/main --explain` results are reported in the handoff.

**Remaining limits.** The two captured inventories are the supported subset —
unseen cards on these tabs remain unresolved. Same-run captures are not
independent holdouts. At 540x960 the clipped Lord EXP Owned label is
unreadable and stays unknown. Final independent live Military → Misc → Home
with typed content, architectural review and acceptance remain lead-owned.

## Lead acceptance — 2026-09-16

Accepted for the twelve captured Military/Misc card variants after architectural
and repository integration review. The existing domain union, card producer,
measured tab controls and both publication paths remain the canonical owners.
Lead correction: zero OCR duration/percent/EXP amounts now stay unknown before
constructing a positive-valued identity, matching the existing Speedup contract.
All 39 focused Bag identity tests passed after this correction. The worker's
post-V16 full fallback passed 2,427 tests with 7 skipped (run
209b64c5ea854893b0d1565b3304ee1c, base 10decf7, 2026-09-16T17:03Z).

Live evidence: mega_old_acc, active K157 / NPC 2 / level22. Runtime
20260916T171915Z_3b9a2d96 captured Military frame0030 and Misc frame0034;
all twelve identities, current quantities and NO_ACTION rows matched the
visually inspected native sources. The Misc shovel count is now56, whereas the
reference capture had60; no cause of that change is inferred. A stale reference
count assertion interrupted the harness, so the canonical leased continuation
in `.local-data/devin-v12/live_return_completed/` revalidated current Misc,
returned Home, and reverified the active castle. The earlier harness provenance
attribute error and the count assertion were validation-script issues, not
production recognition failures. No Use, Convert, item or spending action was
sent; reservations were released and the existing instance preserved.

Source/typed-result/trace evidence remains in
`.local-data/devin-v12/live_accepted_corrected/` and
`.local-data/devin-v12/live_return_completed/`. No safe detail control is present
on these twelve cards, so this acceptance remains observation-only. Unseen
items and missing variants remain explicitly unqualified.
