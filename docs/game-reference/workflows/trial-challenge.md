# Trial Challenge cards and Gear Applicable Stats

## Evidence and limits

The inspected client source is PNC **5.0.203 / version code 233** from the
recovered gameplay Lua cache; see [provenance](../PROVENANCE.md). The qualified
evidence is the September 15 `vision_live_tour_20260915` tour29 capture on the
configured `testing` instance at 900x1600 (its 540x960 scaled copy is the
tracked `trial_challenge.png` reference — same capture group, not independent),
the independent September 16 `mega_old_acc` completion variant (run `bd76a1da`,
tracked `trial_challenge_completed_20260916.png`), and the lead's non-spending
September 16 Stats qualification run `8e5a65ab` on the same account (one
measured Gear Stats tap; tracked `trial_gear_stats_20260916.png`). No direct
game-service request was made, and nothing here authorizes a mutation.

## Measured layout, September 16

**Offline checked (V15, both production observation paths, real RapidOCR):**

- `PNC_TRIAL_CHALLENGE` / `trial_challenge_live` publishes six fixed card slots
  (~x23, width 852, tops 261/486/711/936/1161/1388, height 206 at 900x1600;
  glowing borders can surround the plain interior). The Sauroi card is fully
  visible with a complete border envelope — proximity to the frame bottom is
  not clipping. Category identity resolves only from each card's own bounded
  title read (`Hero/Curio/Tech/Gear/Rune/Sauroi Trial`), never slot order.
- Each card's facts are independent measured observations: displayed progress
  `n/m`, `Requires Lv.N Castle` level, countdown text, weekday text (occluded
  fragments stay unknown), lock glyph (>= .90), reward chest presence
  (>= .60 — presence only, never completion or claimability), Trial-chip
  presence and Stats-chip presence. A countdown can coexist with a castle lock
  (Rune); a locked card can still show its weekday. No availability is
  computed from schedule text or card order.
- The toolbar wing counter beside Exchange publishes once at screen level as
  an observed integer (`12712` on mega_old_acc); a lone `0` glyph is honestly
  unreadable and the counter stays unknown rather than guessed. It is not a
  named currency.
- Only the Gear card's measured Stats chip is actionable (row `complete` with
  chip bounds/action point); every other category row is `no_action`
  regardless of visible chips. Duplicate resolved categories mark rows
  `ambiguous` with no action. Trial, Rank, Exchange, Mall, Progress and
  Total Rank controls are observation-only — content OCR never grants action
  authority.
- `PNC_TRIAL_APPLICABLE_STATS` / `trial_applicable_stats` publishes the bounded
  table's nine label/percent rows preserving literal OCR text (including the
  misread `%96`) beside parsed numeric values, plus the explanatory footer
  `In Gear Trial, only gear stats are applicable.` as the sole detail-category
  source. Title or values alone never establish the screen identity.
- `TrialChallengeSummary`, `TrialApplicableStatsDetail` and every card row
  carry `frame_ref`, `source_screen` and `source_layout_id` bound by the
  shared provenance owner on both publication paths; nothing carries onto
  unrelated or later frames.

## Navigation boundary

`NavigationCore.open_trial_stats(TrialCategory.GEAR)` requires the proved list
anchor plus one unique `complete` typed Gear row, sends one `TapListEntryAction`
at the measured Stats chip, and confirms two consecutive fresh CLEAR Applicable
Stats frames whose bounded footer category agrees with the source. A wrong or
unreadable footer, stale frames or an unexpected screen fails without a retap.
The reviewed graph edge `PNC_BACK_BUTTON_TOP_LEFT` returns to
`PNC_TRIAL_CHALLENGE`. Other categories are explicitly unsupported for
inspection — they are not force-fit to the Gear detail. Trial entry, battle,
stamina/resource use, Exchange purchases and claims remain outside this
contract.
