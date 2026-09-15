# V10 — Bag Speedup cards and item details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V09. Deliverable: Speedup item identity, quantity, duration/type and detail inspection.

## Evidence and scope

Tour22_bag_speedup captures the tab; the current observation supplies no item rows. Extend V09's shared card contract and the Bag producer, profile/control catalog and bounded OCR planner. Keep a separate Speedup semantic parser/data section, not a copy of Resource inventory.

## Implementation

1. Qualify the selected Speedup tab and measure complete/partial cards inside its viewport.
2. Resolve item identity from artwork plus displayed duration and use category. Similar icons with different durations or construction/research/training applicability must not collapse into one item.
3. Publish canonical item identity where established, observed quantity and duration, applicability, row status and current action bounds. Unknown OCR/variant remains inspectable only when its safe detail control is independently proved; it is not eligible for use.
4. Capture/qualify one non-spending item-detail layout if a measured card/detail control opens it. Parse title, owned quantity, displayed selected amount and relevant controls without changing amounts.
5. Return to the selected tab and reacquire rows after close or scroll. Preserve item-use execution/journal ownership; no new auto-use routine.

## Acceptance and proof

Add Speedup cases next to the existing Bag/Resource vision tests using tour22 plus detail/validation captures when available. Both publishers must distinguish evidenced duration/type variants, preserve quantity and clear rows on tab change. Use one visually similar pair that exists in captures; no hypothetical catalog matrix.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Home → Bag → Speedup → one independently proved inspection control → detail → Speedup → Home. Stop if the available button is Use rather than inspection. Save source/detail/return frames and typed item facts. Do not consume speedups or open a timer workflow to manufacture applicability evidence. Missing detail evidence remains a stated limit.
