# Bag Speedup/Treasure cards and chest previews

## Evidence and limits

The inspected client source is PNC **5.0.203 / version code 233** from the
recovered gameplay Lua cache; see [provenance](../PROVENANCE.md). Historical
Lua is supporting evidence for handler wiring only; current observed behavior
below comes from captured frames. Qualified evidence: the September 15
`vision_live_tour_20260915` tour22/23/24 native 900x1600 captures on the
configured `testing` instance (tracked `bag_variants/bag_speedup_tab.png`,
`bag_variants/bag_treasure_tab.png`; the 540x960 `bag_arena_chest_preview.png`
is a scaled reference of tour24 — same capture group, not independent), the
independent September 16 `mega_old_acc` V09 captures (run
`20260916T055657Z_a7e1320c`, tracked `bag_speedup_bonus_tab.png` and
`bag_treasure_victory_tab.png`), the independent September 15 `bc0f132a`
preview holdout, and the lead's non-spending September 16 Common qualification
(runs `20260916T110400Z_1483bb20` and `20260916T111017Z_b5e56ff0`, tracked
native fixture `bag_common_victory_preview_20260916.png`). No direct
game-service request was made, and nothing here authorizes a mutation.

## Measured layout, September 16

**Offline checked (V10/V11, both production observation paths, real RapidOCR):**

- `PNC_BAG` / `bag` publishes six card bands on either tab (tops
  286/505/725/944/1163/1382, height ~202 at 900x1600; no band is clipped on the
  captured frames). The selected tab resolves from the existing tab-strip
  measurement; `Observation.active_bag_tab` carries it.
- **Speedup tab** rows are flat time reductions: identity resolves from the
  displayed name (`5/10/15/30/60-min`, `3-hr`) or the description duration
  (`Reduces remaining time by N mins/hrs`), never slot order or artwork —
  10/15/30/60-minute artworks share 0.92-0.97 template similarity. When the
  accepted 1.2.3 OCR backend drops the leading digit (`-min Speedup`), the
  description supplies it; a name/description contradiction keeps the identity
  unknown. All rows publish `no_action`: Speedup cards carry no inspection
  control (the historical `bagitem.lua` preview branch requires `preview`
  metadata these items lack), and visible `Use` buttons are never promoted.
  **No Speedup detail route is qualified** — that is a documented limit, not
  a hidden workflow.
- **Percentage Speedup bonuses are a separate semantics** from flat minutes:
  `10%/30% Build/Research/Training Speedup` cards describe temporary boosts
  (`Boosts X speed by N% for 1 hr`), not 60-minute reductions. They parse into
  `SpeedBonusIdentity(applicability, percent, active_minutes)` — the `for 1 hr`
  is the bonus duration, distinct from a time-reduction amount. They are
  observation-only too (they do carry `Use`, which stays unpublished as an
  action).
- **Treasure tab** rows resolve a canonical `TreasureIdentity` from the bounded
  title: Arena Surprise Chest, Common/Rare 1st Victory Chest, Pinball,
  Starna's Dice, `Lv.N Oath Rune Chest`, Diamond Chest, `Lv.N Demon Chest`.
  Levelled kinds carry the displayed level — same-art Oath/Demon variants
  (art similarity up to 0.99) are distinguished by the title text, not the
  icon. The magnifier glyph is measured per card (floor .85; observed
  positives .86-1.0, negatives <= .53); a missing glyph never falls back to
  the artwork center.
- Only **Arena Surprise Chest** and **Common 1st Victory Chest** magnifiers
  are actionable (row `complete` with measured glyph bounds inside the card).
  Every other resolved magnifier stays `no_action` — its destination family
  is unqualified. `Use`, `Use in bulk`, `Open` and claims are never actions.
  Duplicate resolved identities on the same frame mark both rows `ambiguous`
  and withhold the tap; a missing owned count alone does not block a fully
  qualified safe inspection, but an unknown identity does.
- `PNC_BAG_CHEST_PREVIEW` publishes under its qualified layout only
  (`bag_arena_chest_preview` or `bag_common_victory_preview`). The screen-level
  `bag_preview` fact carries the independently parsed title text and its
  resolved `source_identity` — never populated from a requested identity.
  Reward rows are `BAG_PREVIEW_REWARD` entries with literal name, displayed
  range (`x1~5` or single `x200`), parsed `quantity_min`/`quantity_max`, and a
  separate `displayed_owned_count` (current inventory of that reward). A
  possible reward never becomes a Bag/Resource item or a guarantee; duplicate
  displayed names (three `Lost Project Book` offers at x200/x500/x1,000)
  remain separate rows.
- **Layout geometry differs per preview.** Arena rows place `Owned` under the
  left artwork; Common's panel is shifted up with `Owned` in the right text
  column — each layout has its own measured bounds. Common's fourth row
  (`Mithril Ore x1,000`) is bottom-clipped with its Owned line cut; the count
  stays unknown, not zero. Arena's fourth row (`Elros Frag.`) shows no Owned
  line below the panel viewport — also unknown.
- All facts carry `frame_ref`, `source_screen` and `source_layout_id` bound by
  the shared provenance owner on both publication paths; Bag content never
  leaks onto the preview screen or vice versa, and unrelated/closed frames
  publish nothing.

## Navigation boundary

`NavigationCore.open_bag_chest_preview(TreasureIdentity)` accepts only
identities whose destination family is qualified (Arena, Common 1st Victory)
— anything else raises before any tap. It requires a fresh CLEAR Bag frame on
the Treasure tab (`bag` layout), exactly one `complete` typed row whose
canonical identity key matches, a measured action point inside measured action
bounds inside the card, then sends one `TapListEntryAction`. Completion needs
two consecutive fresh CLEAR `PNC_BAG_CHEST_PREVIEW` frames on the qualified
layout whose independently read title identity agrees with the request. A
wrong, unreadable, stale or unexpected destination fails without a retap.
Close reuses the existing gold-X graph (Common reuses the same close image at
its own search bounds/floor .94); an absent or blocked close sends no input.
`WorkflowContext.open_bag_chest_preview` wraps opening. After navigating back
to Bag, callers use `observe_content(expected_screen=PNC_BAG)` to reacquire
Treasure rows through the existing content-observation boundary. The tap
matches the unique canonical identity key; literal OCR spacing is preserved
and is not an additional exact-title requirement.

## Candidate acceptance, September 16

Lead architectural and caller review corrected partial/zero OCR handling,
flat speedup applicability, and preview clipping. The fourth reward row is
explicitly `clipped`; its incomplete Owned field is excluded from OCR, while
the visible name and possible quantity remain available. Arena's title crop
is confined to the actual header band. The independent native Arena fixture
`bag_arena_chest_preview_holdout_20260915.png` preserves run `bc0f132a`
provenance and passes real OCR through both publishers alongside the540-pixel
reference. Build identifiers were not queried.

Live-observed on `mega_old_acc` without spending: runtime
`20260916T123800Z_1853a038` proved Speedup content and Treasure acquisition;
its attempted preview action stopped before input because a formatted title
did not match the literal OCR title. After the canonical-identity correction,
runtime `20260916T124230Z_463bd47d` passed Home → Treasure → Common preview →
fresh Treasure content → Home. Preview frame0034 at12:44:38Z and final Home
frame0044 at12:44:58Z were inspected. The preview's three Lost Project Book
offers remain distinct, and the clipped Mithril Owned count stays unknown.
Artifacts and trace are under the task checkout's ignored
`.local-data/devin-v10-v11/live_candidate_fixed/`.

## Remaining limits

Rare 1st Victory, Pinball, Starna's Dice, Oath Rune, Diamond and Demon
magnifiers publish facts but are unsupported for inspection — their
destinations need their own qualification. Speedup inspection has no
evidenced control at all. Common is the live-qualified opening family on this
account; Arena content and controls retain their independent captured proof.
