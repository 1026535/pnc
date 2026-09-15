# V11 — Bag Treasure, chest previews and item details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V09 and the baseline chest-preview fix. Deliverable: Treasure card semantics and owned preview content/return.

## Evidence and owner

Tour23_bag_treasure and24_chest_preview show Treasure cards and Arena Surprise Chest contents. Similar Demon Chest artwork is reused across levels. The baseline already recognizes `PNC_BAG_CHEST_PREVIEW` and its measured close, preserves the preview during observation, and returns to Bag.

Extend V09's card producer, feature-specific bounded OCR/content, current preview profile/control catalog and `navigation_core.py` only for evidenced additional routes.

## Implementation

1. Identify the selected Treasure tab and complete cards. Combine artwork with displayed chest/item name, level/variant and quantity; do not merge different chest levels by icon.
2. Distinguish the magnifier/inspection control from Use/Open. Only the measured inspection control participates in this packet's navigation.
3. Parse preview-owned content rows: displayed reward identity/quantity/range when readable, viewport clipping and close control. A possible reward is not an item owned in Bag. Do not infer odds or guaranteed amounts that the UI does not display.
4. Qualify any additional Treasure detail as a feature-owned surface with explicit close/return, reusing the existing preview pattern. Avoid automatic recovery dismissing inspection.
5. On close, restore Bag tab identity and freshly acquire the card; do not retain the old preview rows.

## Acceptance and proof

Extend existing chest-preview/known-popup tests with Treasure row parsing and preview contents through both publishers. Require distinct evidenced chest levels, owned versus possible-reward separation, preserved preview across observation and correct close destination. Keep the generic unexpected-modal guard regression.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Bag → Treasure → Arena Surprise Chest magnifier → preview → Bag → Home. Save typed card/preview facts and pre/post frames. Stop before Open/Use or any reward selection confirmation. The prior close fix is already complete; success here adds content semantics without reopening that implementation.
