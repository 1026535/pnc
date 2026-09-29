# Configurable support-building acquisition

**Recheck:** 2026-09-29. **Client baseline:** PNC 5.0.203 / 233 from the accepted
APK evidence map. Saved Home captures are from 2026-09-22; their installed build
is not recorded. This note covers acquisition prerequisites for Alliance Hall and
Market, with Blacksmith as the existing third eligible occupant. It does not
qualify their feature actions or new public routes.

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
- **Unknown:** Market's native body crop, clear action region, endpoint identity
  and actual return. None is supplied by the reviewed Home fixture index or
  endpoint manifest. The old artifact
  `20260825T150419Z_phase1_upgrade_focus_market_post_action_3.png` shows foggy
  Home, not a Market body or endpoint; its filename is not identity evidence.
  A missing body match does not establish unavailability.

Lua paths above are relative to `.local-data/apk-exploration/gameplay-lua/`;
building item/component paths start with `scenes/cityscene/buildings/`.

## Automation implications

Alliance Hall can join measured discovery candidates once the new body tests are
validated. Its target uses the existing fixed-landmark pose and slot matcher;
it adds no pan implementation or localization vote. Final entry requires a fresh
same-type/same-slot template body and an unobstructed native action point.

The public core still refuses Alliance Hall and Market before capture because
neither has a reviewed return edge. The new fake tests isolate acquisition with
a test-only endpoint edge; they do not qualify an automatic production route.
Existing V37/V27 menus, parsers and mutations remain feature-owned.

## Next smallest observations

These are pending coordinator-owned cases for the existing live worker. Add them
to a released batch with explicit limits before execution; they are not added to
the current integrated helper's scope by this note. Reuse the configured testing
instance's active castle and established identity/lease authority. Do not move
buildings or switch castles to manufacture a permutation.

| Case | Precondition and allowed action | Required evidence |
| --- | --- | --- |
| CFG-P1 Market body | During one bounded shared discovery, passively inspect eligible slots 11/12/13. Camera movement uses the existing core only; no Market tap. | One full native body with readable Market identity, current fixed-landmark pose, observed slot, and clear interior point away from bubbles/help/area controls; one separate capture as holdout. If unresolved, keep availability unknown. |
| CFG-E1 Alliance Hall endpoint/return | After body-data acceptance, current measured Hall body at its observed slot, with a clear point. Coordinator may release one non-spending body entry and one measured **top-left Back** return through the existing capture workflow. | Exact body/slot/source and actual tap receipt, fresh native Alliance Hall title plus static description, independently measured top-left Back, its receipt and fresh Home completion. Do not tap Upgrade, Send Back, Reinforce or Join Alliance. A public-route refusal is not successful capture or permission to bypass its policy. |
| CFG-E2 Market endpoint/return | Only after CFG-P1 supplies reviewed body/action evidence. Coordinator may release one non-spending body entry and one measured top-left Back return. | Exact body/slot/source and actual tap receipt, full native Market identity with static supporting content, measured Back and fresh Home completion. Capture any observed intermediate state and stop for review; do not guess a new control. Do not tap Upgrade, Resource Transport, Join Alliance or any claim/purchase. |

One observed placement per available type is sufficient for these missing native
boundaries. Slot eligibility and selected-slot persistence have deterministic
coverage; new native permutations require observed variability that affects the
contract. Entry/capture alone does not qualify a route until its destination and
return are independently reviewed.
