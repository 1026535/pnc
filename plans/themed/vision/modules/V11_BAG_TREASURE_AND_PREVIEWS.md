# V11 — Bag Treasure, chest previews and item details

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V09; reuse the source chest-preview fix where applicable. Deliverable: Treasure card semantics and owned preview content/return.

## Evidence and owner

Tour23_bag_treasure and24_chest_preview show Treasure cards and Arena Surprise
Chest contents. Similar Demon Chest artwork is reused across levels. The
[source-fix evidence](CONTEXT_AND_EVIDENCE.md#navigation-findings-retained-in-these-plans)
qualifies `PNC_BAG_CHEST_PREVIEW`, its measured gold-X close and task-owned
observation on `4d317db`; those exact changes and fixtures are ported after
`ff38127`. Preserve this baseline while implementing Treasure and preview
content. Reconcile newer feature work before editing the shared owners.

Extend V09's card producer, feature-specific bounded OCR/content, current preview profile/control catalog and `navigation_core.py` only for evidenced additional routes.

## Implementation

1. Preserve the integrated preview identity/ownership/close and
   `bag_arena_chest_preview.png` with its provenance.
   Ordinary observation must keep the preview,
   and an absent/blocked close must stop input. Identify the selected Treasure tab and complete cards. Combine artwork with displayed chest/item name, level/variant and quantity; do not merge different chest levels by icon.
2. Distinguish the magnifier/inspection control from Use/Open. Only the measured inspection control participates in this packet's navigation.
3. Parse preview-owned content rows: displayed reward identity/quantity/range when readable, viewport clipping and close control. A possible reward is not an item owned in Bag. Do not infer odds or guaranteed amounts that the UI does not display.
4. Qualify any additional Treasure detail as a feature-owned surface with explicit close/return, reusing the existing preview pattern. Avoid automatic recovery dismissing inspection.
5. On close, restore Bag tab identity and freshly acquire the card; do not retain the old preview rows.

## Acceptance and proof

Extend existing chest-preview/known-popup tests with Treasure row parsing and preview contents through both publishers. Require distinct evidenced chest levels, owned versus possible-reward separation, preserved preview across observation and correct close destination. Keep the generic unexpected-modal guard regression.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Bag → Treasure → Arena Surprise Chest magnifier → preview → Bag → Home. Save typed card/preview facts and pre/post frames. Stop before Open/Use or any reward selection confirmation. The baseline close fix is already ported. Acceptance
requires preserving its behavior on this packet's candidate plus the new content semantics;
keep unrelated interruption and resource-action controls unchanged.

## Accepted implementation coverage, September 16

Implemented on `codex/vision-v10-v11-bag` atop accepted V15 `7127266`, integrating the lead's immutable Common qualification delta `9a98d98` (native fixture, two bounded anchors, profile/metadata tests). Baseline evidence: tour23/24 native captures (`bag_treasure_tab.png`, `bag_arena_chest_preview.png` reference), the independent `mega_old_acc` Victory capture `bag_treasure_victory_tab.png` (run `20260916T055657Z_a7e1320c`), the independent `bc0f132a` preview holdout, and the lead's non-spending Common qualification (runs `1483bb20`/`b5e56ff0`, tracked `bag_common_victory_preview_20260916.png`).

- `domain/bag_items.py` owns `TreasureIdentity(kind, level?)` — levelled Oath/Demon kinds carry their displayed level so same-art variants never merge; canonical `treasure_identity_for_label`/`treasure_identity_title`/`bag_item_identity_key` are the single parsing/matching owner shared by producer and navigation. `BagPreviewRewardFacts` keeps literal reward name, displayed range text, parsed `quantity_min`/`quantity_max` and separate `displayed_owned_count`; `BagChestPreviewFacts` carries independently parsed `title_text`, resolved `source_identity` and measured `title_bounds`. `ListEntryKind.BAG_PREVIEW_REWARD`, `DetectedListEntry.bag_reward_facts`, `Observation.bag_preview` and the `bind_bag_preview` provenance binder follow the accepted pattern on both publishers.
- `BagItemContentProducer` measures the magnifier glyph per card with a card-artwork-corner anchor (floor .85; observed positives .86-1.0, negatives <= .53 — never artwork-center fallback, no generic global selector). Only Arena Surprise Chest and Common 1st Victory Chest publish `complete` rows with the measured action point/bounds; every other resolved magnifier stays `no_action`. Duplicate resolved identities mark rows `ambiguous`. `Use`/`Use in bulk`/`Open` are never promoted.
- Preview rows parse under their own layout geometry: Arena `Owned` sits under left artwork, Common's shifted-up panel puts it in the right text column — no shared crop. The three displayed `Lost Project Book` offers (x200/x500/x1,000) stay separate rows; Common's clipped `Mithril Ore` row and Arena's `Elros Frag.` row keep `displayed_owned_count` unknown rather than zero. The screen-level `bag_preview` parses the title independently of any requested identity and preserves source/destination mismatch evidence.
- `NavigationCore.open_bag_chest_preview(identity)` rejects unsupported targets before any tap, requires a fresh CLEAR `PNC_BAG`/`bag`/Treasure source with exactly one `complete` matching typed row and bounded measured action geometry, sends one `TapListEntryAction`, and confirms two stable CLEAR preview frames whose qualified layout **and** independently parsed title identity both match. Wrong/unreadable/stale/unexpected destinations fail without retap; close reuses the existing gold-X graph (Common reuses the same close image at its own bounds/floor .94). `WorkflowContext.open_bag_chest_preview` wraps opening; the existing content-observation boundary reacquires Treasure rows after the caller navigates back.

Tests: `tests/integration/vision/test_bag_items_publication.py` replays both Treasure captures and both preview fixtures through both publishers with real bounded RapidOCR (six typed Treasure identities each, exactly one actionable row per tab, four bounded reward rows per preview, provenance and cross-screen-leak assertions). `BagChestPreviewNavigationCoreTests` in `test_navigation_core.py` covers the happy route, Common's own layout, six unsupported identities rejected pre-tap, nine unqualified sources, and wrong/unreadable/stale destinations with exactly one tap. Lead Common profile/metadata tests (`test_bag_common_preview_profile.py`, `test_visual_screen_metadata.py`) pass unchanged.

Lead acceptance: partial or zero-valued item labels remain unknown; clipped
preview rows exclude their incomplete Owned field and retain only visible
name/range facts. Arena title bounds were tightened after the independent
native `bc0f132a` capture exposed overlapping OCR fragments. Reference and
native Arena content now pass through both publishers. The action executor
matches the unique canonical item identity instead of requiring literal OCR
spacing to equal the formatted display title; the navigation regression test
uses the actual compact Common title observed live.

The shared full gate ran 2,395 tests with seven skips. Two failing methods
were corrected and their focused checks passed. Lead correction checks include
26 unit tests, seven navigation tests, both preview fixtures, and four final
native Arena/metadata checks. Production live runtime
`20260916T124230Z_463bd47d` passed Home → Treasure → Common preview → fresh
Treasure content → Home on mega_old_acc. The matching preview was confirmed
at 12:44:38Z and final Home at 12:44:58Z, with no spending. See the Bag workflow
note for the prior pre-tap failure and exact artifact provenance. After close,
the existing `observe_content` boundary reacquires Treasure rows; opening the
preview does not close it automatically.

Remaining limits: Rare 1st Victory, Pinball, Starna's Dice, Oath Rune, Diamond
and Demon destinations remain unqualified. Common was available for the live
route; Arena retains captured content/control proof. Accepted for this scope.
