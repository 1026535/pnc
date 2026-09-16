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

## Accepted implementation coverage, September 16

Implemented on `codex/vision-v10-v11-bag` atop accepted V15 `7127266`. Baseline evidence: tour22 native `bag_speedup_tab.png` (2026-09-15 `vision_live_tour_20260915`, run `b519129c`) plus the independent `mega_old_acc` percentage-bonus capture `bag_speedup_bonus_tab.png` (accepted V09 live run `20260916T055657Z_a7e1320c`, both tracked under `tests/data/screen_recognition/bag_variants/` with manual annotations).

- `domain/bag_items.py` owns `TimeReductionIdentity(applicability, minutes)` and `SpeedBonusIdentity(applicability, percent, active_minutes)` as distinct members of the `BagItemIdentity` union — percentage bonuses (`Boosts X speed by N% for 1 hr`) are never flattened into minute reductions. `BagItemFacts` carries `selected_tab`, optional resolved `identity`, optional `owned_count` and measured `inspection_glyph_present`; `ListEntryKind.BAG_ITEM` plus `DetectedListEntry.bag_item_facts` follow the accepted typed-facts pattern.
- `vision/bag_items.py` (`BagItemContentProducer`) reuses `detect_bag_card_geometry` and bounded name/description/owned reads per card — no second scanner, no Resource copy. Identity resolves from displayed name or description tokens; both read and contradictory → unknown. The observed `Bo0sts` OCR noise on `Boosts` is tolerated by token parsing; the then-accepted 1.2.3 backend's dropped leading digit (`-min Speedup`) is recovered from the description duration rather than decoder workarounds. The shared [OCR modernization plan](../PNC_OCR_TEXT_LOCALIZATION_MODERNIZATION_PLAN.md) owns future backend/localization changes; reproduce historical failures against the accepted V13 backend before treating them as current.
- All Speedup rows publish `no_action` with no action point: the evidenced flat-reduction cards carry no inspection control, percentage-bonus `Use` buttons are observation-only, and **no Speedup detail route is qualified** — the plan's documented missing-detail limit stands. The visually similar 10/15/30/60-minute artwork family (0.92-0.97 mutual similarity) is noted; identity never comes from art.
- Both publishers merge and provenance-bind `BAG_ITEM` rows; closed/tab-changed frames publish nothing.

Tests: `tests/unit/app/pnc/vision/test_bag_items.py` covers identity parsing (flat/hour conversion, percentage+active-hour, contradictions, letter-confused levels), owned-count forms, duplicate-identity gating and dispatch gates. `tests/integration/vision/test_bag_items_publication.py` replays both native captures through `ObservationBuilder` and `NavigationPerception` with real bounded RapidOCR: six flat reductions (5-180 min, owned 50/14/3/4/39/1) and six bonus rows (10/30% Build/Research/Training, owned 1/7/1/3/1/5), all `no_action` with correct provenance.

Lead review corrected missing/zero parsed values to remain unknown and retained
Research/Heal applicability on flat reductions rather than forcing General.
The shared V10/V11 full gate ran2395 tests (2386 passed,7 skipped,2 methods failed);
the obsolete expectations/signature failures were corrected and scoped checks
passed. Lead's final26 unit tests and affected captured/navigation checks passed.
Live Speedup content and zero actionable item rows were verified on mega_old_acc
in runtime `20260916T123800Z_1853a038`; the completed shared return route is
`20260916T124230Z_463bd47d`, final Home at12:44:58Z. No item was used, and no
Speedup detail was invented. Accepted for this explicitly stated coverage.
