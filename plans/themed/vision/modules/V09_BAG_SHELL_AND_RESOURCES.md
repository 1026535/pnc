# V09 — Bag shell, common cards and Resource inventory

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01. Deliverable: current selected-tab identity, reusable card facts, and corrected Resource viewport handling.

## Current owners and gaps

`app/pnc/vision/resource_inventory.py` owns Resource parsing; `domain/resource_items.py` owns canonical resource identities; `_build_bag_additions` in the enricher owns publication; `daily_maintenance/resource_inventory_session.py` owns the inventory consumer. Preserve that scanner and its item-use boundary.

Tour19 publishes six canonical Resource rows despite OCR errors such as Fo0d/Wo0d. The [resource inventory note](../../../../docs/game-reference/workflows/resource-inventory.md) and recognition follow-up describe small partial cards being omitted and tall partials labelled unreadable rather than clipped. Non-resource tabs currently lack rows.

## Implementation

1. Identify Bag shell and current subtab from visual selected-state evidence. Publish only controls belonging to that tab; switching tabs invalidates prior rows.
2. Extract only the shared card/viewport geometry needed by V10–12. Keep resource identity parsing and the existing inventory scanner canonical. Use one typed shared item/row representation where new fields are needed, with feature-specific content conversion.
3. Fix edge-fragment detection: retain visible partial cards with honest CLIPPED/unresolved status and no action. Do not invent item names or quantities from incomplete cards.
4. Preserve Resource kind/size/quantity and exclusion semantics. Item artwork supports identity; changing quantities and denomination variants use bounded OCR and the existing item catalog.
5. Publish via both observation paths. Existing whole-inventory traversal uses refreshed rows and its current termination rules; do not create another scrolling engine.

## Acceptance and proof

Target `test_resource_inventory_vision.py`, `tests/contract/workflows/test_resource_inventory_core_navigation.py` and real Resource captures. Include the observed short edge fragments, a complete row, tab switch and ordinary inventory continuation. Require no stale Resource actions on Speedup/Treasure and no fabricated quantity for a clipped card.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Home → Bag → Resource → one bounded scroll → inspect current rows → Bag/Home return. Save viewport frames, row statuses and trace. Stop before Use or any quantity-confirm action. The result must keep existing resource consumers working while exposing the shared contract for later tabs.

## Accepted coverage, September 16

Implemented, reviewed and verified offline and live:

- `vision/bag_layout.py` owns the shared Bag body bounds, card-band geometry with the reviewed edge-clipping rule, and the single-gold-container subtab measurement. Resource, Speedup and Treasure captures return identical card bounds; scrolled frames mark top/bottom edge bands clipped.
- `domain/bag.py` owns `BagTab` (resource, speedup, military, treasure, misc) and `bag_tab_selector_id`. `Observation.active_bag_tab` publishes through `ObservationAdditions`, both observation paths, and `NavigationPerception`; it is never carried across frames and stays absent on unrelated/blocked/unknown-selection frames.
- Selected/unselected badge-trimmed template controls for Resource, Speedup and Treasure publish on every Bag frame (positive ~1.000, negative <=0.797 on saved captures). Military and Misc. selectors remain `unsupported` pending V12 evidence.
- `_build_bag_additions` publishes shell + typed tab from pixels under proved PNC_BAG; Resource rows and the bounded body read run only on a positively measured Resource selection.
- `NavigationCore.select_bag_tab` + `WorkflowContext.select_bag_tab` tap one measured subtab once and require a fresh clear typed postcondition; unknown selection or an unresolved source guard stops before input. `require_resource_inventory_surface` now requires the typed Resource selection plus template control evidence. The connected adapter migrated to `active_bag_tab`.
- One bounded per-card row-facts retry resolves the `bag.png` `10K Food (Safe)` row (`food:10000:safe`, owned 873) that the shared body read left unresolved; clipped rows are never retried and no facts are inferred.
- Remaining outside V09: Military/Misc. selected-state and controls (V12 evidence), Speedup/Treasure item semantics (V10/V11).

Lead review found one acceptance issue: an unknown selected tab could still trigger a tap. The lead corrected the source and completion guards and added focused regressions; canonical inventory traversal, row provenance, both publication paths and existing mutation ownership remain intact. Recorded full affected fallback: 309 modules, 2,208 passed and seven expected skips. Independent lead Bag publication/navigation checks passed 17 tests; the correction's navigation suite passed 13 tests.

Live proof used the configured `mega_old_acc` daily-canary role under one canonical process reservation and its freshly verified active castle. Home → Bag → Speedup → Treasure → Resource → one bounded scroll → Home passed. The scroll published five complete Wood/Iron rows plus two clipped fragments with no facts/actions. Other tabs published their own typed selection and zero Resource rows. No Use, bulk Use or quantity action occurred. The pre-existing instance remained open at Home and the reservation was released.

Evidence lives in `C:/Users/lebel/pnc/.local-data/worktrees/vision-v09-bag/.local-data/devin-v09/live_ready/`: `result.json`, `trace.jsonl`, per-step observations and screenshots. The scrolled frame ends `0039_resource_scroll_settled.png`; final Home ends `0043_core_12_after_1.png`, both from runtime `20260916T055657Z_a7e1320c`. An earlier startup-only attempt saw black loading frames and stopped; `live/` preserves that failure. `live_diagnostic/` then independently observed Home before the successful retry. No production loading policy was changed.
