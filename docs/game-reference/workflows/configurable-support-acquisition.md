# Configurable support-building acquisition

**Recheck:** 2026-09-30. **Client baseline:** PNC 5.0.203 / 233 from the accepted
APK evidence map. Saved Home captures are from 2026-09-22, 23 and 29; the live025
endpoint/return receipts are from 2026-09-30; the installed builds are not
recorded. This note covers acquisition prerequisites for Alliance Hall and
Market, with Blacksmith as the existing third eligible occupant. It does not
qualify their feature actions.

## Findings

- **Repository-proven, high confidence:** slots 11, 12 and 13 each allow
  Blacksmith, Market and Alliance Hall. `home_city_slots_for_object` publishes
  those eligibility records. The calibrated pivot is fixed slot geometry;
  current occupant identity remains observed. Reference slots on body templates
  only translate crop/action geometry to a selected candidate. They do not name
  an account's current layout. Movable building landmarks cannot localize pose.
- **Artifact-observed, high confidence:**
  `tests/data/home_city_slot_bodies/home_city_pan2_f5_20260922.png` shows a readable
  Alliance Hall nameplate and its clear body at slot 13, as indexed in that
  directory's manifest. `home_city_wall_slot2_f6_20260922.png` is a separate
  capture at essentially the same fixed-landmark pose. This establishes one
  observed occupant/skin, not a live permutation proof for slots 11 and 12.
- **Artifact-observed, high confidence:** the new `alliance_hall_body.png` is
  an exact RGBA crop `(106,610,162,180)` from f5. It excludes the nameplate and
  floating upgrade arrow/level badge. The candidate action is clear front-wall
  pixels at `(172,736)`, with a measured 20×20 interior region. Under the saved
  pose `zoom=1`, translation `(-1632,-718)`, those map to reference bounds
  `(1206,1550,162,180)` and point `(1272,1676)`, or atlas point `(1804,1454)`.
  The template is authored at reference slot 13; the shared matcher searches
  every eligible slot. Native source/holdout matching and live collider behavior
  remain pending. Blacksmith's existing data is unchanged.
- **Repository-proven, high confidence:** body handlers `builditem_1009.lua:84–88`
  and `builditem_1010.lua:109–113` call the existing `BuildClickComponent`.
  Its `ClickHandler:17–21` calls `BuildTableData:OpenBuildWin` for the current DTO.
  `vo/buildtabledata.lua:161–164` maps Market to `FAIR_WIN` and Alliance Hall to
  `EMBASSY_WIN`. These branches support candidate entry identity; current native
  completion and return still require observation.
- **Artifact-observed, high confidence:** the packaged
  `alliance_variants/alliance_remaining_hall.png` provides static Alliance Hall
  title/description and a separate top-left Back match. Its `screen_anchors.json`
  profile `alliance_remaining_hall` cites capture group
  `2026-09-13/capture_gap_exploration/20260913T030954Z/0181_alliance_hall` and is
  explicitly `guarded_reference_only`. It is reusable feature-owned identity
  evidence, without a native Back-to-Home receipt or current full endpoint.
- **Repository-proven, high confidence:** `uis/embassy/embassywin.lua:39` binds
  `backBtn` to `BtnHandler`; lines 102–127 show this is the bottom **Send Back**
  reinforcement action, including confirmation and repatriation. It is not the
  top-left navigation Back control. `uis/fair/fairwin.lua:33–35` makes its main
  button open a Transport member list. These actions remain feature-owned and
  are outside acquisition/return capture scope.
- **Artifact-observed, high confidence:**
  `tests/data/home_city_camera/home_city_wall_corridor_regression_20260923.png`
  contains a labeled Market at slot 11. The exact native RGBA crop
  `(130,875,155,110)` is `market_body.png`; it includes the stalls and central
  plinth, excluding the nameplate, badge and floating controls. The candidate
  body point `(213,949)` and 20×20 interior region map under the recorded
  `zoom=1`, atlas translation `(-1298,-645)` to reference bounds
  `(896,1742,155,110)`, reference point `(979,1816)` and atlas point `(1511,1594)`.
  The source file SHA-256 is
  `374949a21e6f30f40f02b6782bbad7db7ffd918470e908e915ed031a8fc804fa`.
  This Wall diagnosis frame is template source evidence, not an unseen holdout.
- **Artifact-observed, high confidence:**
  `tests/data/home_city_slot_bodies/home_city_warehouse_slot3_0084_20260929.png`
  independently shows a labeled Market at slot 11 on a different date, session
  and camera pose (`zoom=0.75`, translation `(-389,-427)`). The file SHA-256 is
  `7ef0c47ea6e7fa377d5b090cd54b18133ea0b2858467edaf3506dc7f82b12fee`.
  Native matching on candidate `82730082` measured bounds `(678,708,116,82)`,
  action `(740,764)`, score `0.9704` and projection error `6.40px`. The
  camera-only point `(744,769)` differs from the measured body point; navigation
  must use the latter. The older reduced
  `home_city_pan_07.png` shows an empty slot 11 between Blacksmith and Hall and
  supplies a real negative. These observations do not prove other placements,
  other skins, collider behavior, or an operational public route.
- **Live-observed, 2026-09-30, installed build unrecorded:** turn025 on
  `157_farm` reacquired the measured Market body at slot 11 (point `(492,756)`)
  and the Alliance Hall body at slot 13 (point `(708,654)`); each entered to
  its typed endpoint (`PNC_MARKET` through the new `building_market` profile,
  `PNC_ALLIANCE_HALL` through the guarded `alliance_remaining_hall` profile)
  and returned to fresh Home through measured top-left Back at `(81,44)` and
  `(81,52)`, including one current-Market takeover return. Same-process
  developmental receipts, not public-caller acceptance; evidence under ignored
  `.local-data/devin-live-test/runs/v44-publication-20260928/turn-025/` and
  parent review `v44-live025-independent-review-20260930.json`.
  The old artifact
  `20260825T150419Z_phase1_upgrade_focus_market_post_action_3.png` shows foggy
  Home, not a Market body or endpoint; its filename is not identity evidence.
  A missing body match does not establish unavailability.

Lua paths above are relative to `.local-data/apk-exploration/gameplay-lua/`;
building item/component paths start with `scenes/cityscene/buildings/`.

## Automation implications

Alliance Hall and Market can join measured discovery candidates once their body
tests are validated. Both use the existing fixed-landmark pose and slot matcher;
neither adds a pan implementation or localization vote. Their reference slots
translate body geometry only; current matches bind occupants to slots 11/12/13.
Final entry requires a fresh
same-type/same-slot template body and an unobstructed native action point.

`reviewed_navigation_edges` now carries the measured top-left Back -> Home
edge for both `PNC_MARKET` and `PNC_ALLIANCE_HALL`, so `open_building` and
`open_visible_building` admit both targets through the shared measured
operation: route review before observation, exact optional slot, fresh typed
body at a safe point, one observed-point tap, then the confirmed Back return.
Public-route candidate status is pending final batched live validation through
production `open_building`; the turn025 receipts came from the developmental
helper, not the public caller. The remaining fake tests isolate acquisition
with a test-only endpoint edge and do not qualify an automatic production
route. Existing V37/V27 menus, parsers and mutations remain feature-owned.

## Next smallest observations

CFG-E1 and CFG-E2 receipts were delivered by turn025 on 2026-09-30 (same-process
developmental helper, per above). The remaining public-route qualification is a
coordinator-owned live batch through production `open_building`; CFG-P1 stays
open only for a second native Market body sighting. Reuse the batch-assigned
`157_farm` instance's active castle and established identity/lease authority. Do not move
buildings or switch castles to manufacture a permutation.

| Case | Precondition and allowed action | Required evidence |
| --- | --- | --- |
| CFG-P1 Market body | After the saved native matching checks pass, include Market in one bounded shared discovery. Use the existing core; no Market tap. Source and separate holdout are already available above. | Current passive match with readable Market identity, fixed-landmark pose, observed slot and clear interior point; bind the result to the exact final candidate. If unresolved, keep availability unknown. |
| CFG-E1 Alliance Hall endpoint/return (delivered turn025, developmental helper) | Final public-caller validation through production `open_building` remains coordinator-owned. | turn025 receipts: Hall body slot 13 point `(708,654)` -> typed `PNC_ALLIANCE_HALL` -> measured top-left Back `(81,52)` -> fresh Home. |
| CFG-E2 Market endpoint/return (delivered turn025, developmental helper) | Final public-caller validation through production `open_building` remains coordinator-owned. | turn025 receipts: Market body slot 11 point `(492,756)` -> typed `PNC_MARKET` -> measured top-left Back `(81,44)` -> fresh Home, including a current-Market takeover return. |

One observed placement per available type is sufficient for these missing native
boundaries. Slot eligibility and selected-slot persistence have deterministic
coverage; new native permutations require observed variability that affects the
contract. Entry/capture alone does not qualify a route until its destination and
return are independently reviewed.
