# V09 — Bag shell, common cards and Resource inventory

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01. Deliverable: current selected-tab identity, reusable card facts, and corrected Resource viewport handling.

## Current owners and gaps

`app/pnc/vision/resource_inventory.py` owns Resource parsing; `domain/resource_items.py` owns canonical resource identities; `_build_bag_additions` in the enricher owns publication; `daily_maintenance/resource_inventory_session.py` owns the inventory consumer. Preserve that scanner and its item-use boundary.

Tour19 publishes six canonical Resource rows despite OCR errors such as Fo0d/Wo0d. The [resource inventory note](../../docs/game-reference/workflows/resource-inventory.md) and recognition follow-up describe small partial cards being omitted and tall partials labelled unreadable rather than clipped. Non-resource tabs currently lack rows.

## Implementation

1. Identify Bag shell and current subtab from visual selected-state evidence. Publish only controls belonging to that tab; switching tabs invalidates prior rows.
2. Extract only the shared card/viewport geometry needed by V10–12. Keep resource identity parsing and the existing inventory scanner canonical. Use one typed shared item/row representation where new fields are needed, with feature-specific content conversion.
3. Fix edge-fragment detection: retain visible partial cards with honest CLIPPED/unresolved status and no action. Do not invent item names or quantities from incomplete cards.
4. Preserve Resource kind/size/quantity and exclusion semantics. Item artwork supports identity; changing quantities and denomination variants use bounded OCR and the existing item catalog.
5. Publish via both observation paths. Existing whole-inventory traversal uses refreshed rows and its current termination rules; do not create another scrolling engine.

## Acceptance and proof

Target `test_resource_inventory_vision.py`, `tests/contract/workflows/test_resource_inventory_core_navigation.py` and real Resource captures. Include the observed short edge fragments, a complete row, tab switch and ordinary inventory continuation. Require no stale Resource actions on Speedup/Treasure and no fabricated quantity for a clipped card.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Home → Bag → Resource → one bounded scroll → inspect current rows → Bag/Home return. Save viewport frames, row statuses and trace. Stop before Use or any quantity-confirm action. The result must keep existing resource consumers working while exposing the shared contract for later tabs.
