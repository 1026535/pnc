# Measured Home camera and building entry

Observed on 2026-09-16 UTC through the replacement core on the user-authorized
`mega_old_acc` active castle. Its configured live role is `daily_canary`.
The game build was not recorded by these runs. No account/castle switch,
research, Trial challenge, reward claim or resource spending was performed.

## Camera evidence

The camera uses the existing 900x1600 atlas basis. Castle and Infantry Barracks
anchor the reference translation at (-532,+222); a screenshot point is
`(atlas_point + translation) * frame_size / reference_size`.
Current structural matches establish translation; finger movement never does.
At least three agreeing patches from two independent scene groups are needed.
Insufficient or conflicting evidence cannot authorize a building tap.

Live Home initially had only garden and barracks matches because the right
offer rail and quest HUD covered the other catalog patches. The existing
south-plaza crop at reference (540,1340,130,50) matched at 0.993; saved Tower
and mega views scored 0.916 and 0.984, while World negatives scored about 0.52.
It shares the plaza group with the nearby plaza crop. The qualified Tower body
also supplies the independent Tower group as northern landmarks leave view.
Camera landmarks and target bodies share their canonical reference bounds.

Two scoped calibration captures extended the catalog southeast. From a live
Home re-localized at (-532,-843), one .25-ratio left gesture moved content
(-477,0) to (-1009,-843); a second .20-ratio gesture moved (-414,0) to
(-1423,-843). Blacksmith (640,1845,120,130) and courtyard (640,1530,100,100)
crops qualified the corridor; four eastern crops — aqueduct (1451,1505,120,140)
and parapet (1651,1715,80,60) in one group, cliff rock (1681,1825,80,140) and
rock trees (1521,1965,120,100) in another — bridged to the saved 2026-09-15
Campaign view at image translation (-1350,-931), atlas (-1882,-709). The
structural portal pedestal crop (1480,1306,150,70) matched the T2 frame at
0.953 and carries the verified tap (201,412); its action region is
(1540,1332,22,22). The canonical Campaign map coordinate is now (2083,1121).

A Campaign target needing horizontal acquisition first descends to the
measured southern corridor (atlas camera Y in [-850,-620], aim -709): a
dominant northern horizontal pan would shed every supported landmark before
the eastern crops enter below the viewport. Inside the corridor, ordinary
measured horizontal planning applies. Short corridor corrections use the measured
error without the ordinary minimum gesture, which can overshoot this narrow
band. Every step still requires fresh
localized proof, real motion and the canonical gesture budget. The T2 portal
point (660,278) sits slightly above the HUD-safe band, so the route pans and
reacquires before tapping.

## Observed routes and failures

- Institute: Home localized at (-532,+222), one measured upward pan, fresh
  body reacquisition, one tap, Institute menu, then Home at (-532,-395).
  The Research Queue Go focus route was not used.
- Tower: the first pan reached the lower Home view but left only two old
  landmarks. The core stopped before tapping. The already-qualified Tower
  body matched at 0.989 and agreed with the other patches at image offset
  (0,-1065), atlas translation (-532,-843).
- After that camera correction, one tap reached Trial Challenge. Its former
  Hero-card identity anchor failed on the completed/darkened card (0.796).
  The title and fixed Progress/Total Rank toolbar matched 1.0. The existing
  profile now uses that toolbar, preserving the measured Back control.
- The corrected Tower route confirmed Trial Challenge and returned Home at
  (-532,-843). The pre-existing instance remained running and every lease
  was released.

Evidence is under `.local-data/devin-v02/` in the implementation checkout:
`live_initial`, `live_plaza`, `live_tower`, `live_tower_extended`,
`live_tower_toolbar`, `live_campaign_bridge`, `live_campaign_bridge_2`,
`live_campaign`, `live_campaign_occlusion` and `live_campaign_map`,
each with result, trace and screenshot artifacts. The successful Institute
run is `20260916T063003Z_2059c3cc`; the successful Tower run is
`20260916T064201Z_a7999ab2` (destination0029, returned Home0034). Bridge
runtimes are `20260916T065559Z_43b62d8a` and `20260916T070733Z_450b5f36`.
Tracked regressions and decoded hashes are in the Home-camera and
screen-recognition fixture manifests.

The first Campaign live pan moved the scene (0,+359), from (-1423,-843) to
(-1423,-484), but fixed HUD overlays hid three eastern crops. Aqueduct,
ridge-wall (1117,1365,100,130) and Alliance Hall (1197,1675,140,80) independently
agree on the new camera. Ridge-wall shares the fortification group; Alliance
Hall supplies a separate structure group. Their match scores were 0.981/0.962,
with aqueduct 0.952. The independently measured pedestal body scored 0.922;
its calibrated floor is 0.90 against retained non-Home negatives below 0.40,
with the same 8px projection-agreement requirement. The catalog has 16 patches
in 10 groups. This failure is pinned by the post-pan HUD fixture.

The next single tap reached the actual Campaign map, but it reopened at a
persisted southern scroll position outside the older identity anchors. The
new campaign_map_southern_view profile requires both Costa Dorad and Misty Bay
chapter rows and reuses the existing measured Home portal; foreign event
labels and the top chapter text establish no map identity or active chapter.

**Live observed, 2026-09-16:** corrected runtime 20260916T081624Z_9828df1b
started at default Home (-532,+222), made two measured pans, freshly reacquired
the portal, confirmed Campaign map (destination0034 at081812Z), and returned
Home0040 at081820Z with camera (-532,+222). The lead inspected both screenshots.
The Home portal reset the Home camera in this run. Lease released; instance
preserved; no resource actions. The current game build was not read.

Confidence is high for these current routes and captured states. Other Home
appearances, Arena's separate residual and Trial-card content/eligibility
require their owning packets; these runs prove neither a general appearance
catalog nor Trial eligibility.

## Western camera coverage, September 16

The V05–V07 live route stopped before its first building action at
`20260916T163414Z_core_20260916T163112Z_b7342adf_0023_core_6_building_camera_source.png`.
Home identity was clear, but only the Tower body matched (0.98152). The camera
correctly rejected that single group. The active castle remained K157/NPC2/22;
the build version was not read. No building tap or pan was sent.

The independently localized `home_city_tower_lower_20260916.png` reference
supplies two additional static scene patches. Its six existing correspondences
in five groups agree on image translation (0,-1065). In its normalized native
frame, Tower retaining wall (110,810,120,140) maps to reference
(110,1875,120,140), and Sanctum column (50,940,80,105) maps to
(50,2005,80,105). Both crops exclude text, HUD and promotion controls.

Against the later live west capture, the wall scored 0.98505 and the column
0.97685; both use a 0.95 floor. Together with the existing Tower body, they agree
exactly on image translation (458,-1034), atlas translation (-74,-812).
The wall remains in the Tower structure group; the column belongs to Sanctum.
The catalog now contains 18 patches in 11 groups and retains its three-match,
two-group requirement. A courtyard candidate scored only 0.655 and was excluded.

The tracked independent west holdout preserves native 900×1600 geometry and
masks only the chat band. Its manifest records source and derivative hashes.
The corrected leased runtime20260916T171016Z_a02dbcf6 localized this western
view, made two measured Home pans, freshly acquired Institute and completed
Economy, Military and Fortification detail/return routes. Final Home frame0089
was captured at17:16:15Z. No resource action occurred; the lease released and
the existing instance was preserved. The camera correction is accepted.

Distribution verification also found that the built wheel omitted the camera
PNG directory. The package-data glob now includes it; a rebuilt wheel contains
all19 camera images.

## Lower-Tower ground lane, 2026-09-16

**Live observed:** on camera translation (-532,-840), the old Institute pan
from native (621,710) to (621,889) intersected Blacksmith and opened its menu.
The navigation guard stopped immediately. Source: research inventory runtime
20260916T131246Z_8676bbd3, frames0022/0023, under ignored
`.local-data/research-inventory/economy/artifacts/` in the V05–V07 checkout.
This disproves the fixed x=.69 lane for this otherwise qualified Home view.

The measured courtyard between Tower and Blacksmith defines the atlas strip
Bounds(1042,1510,60,265). Use its translated center only when the whole vertical
gesture fits inside the visible strip and its x lies within the HUD-safe band.
The saved `home_city_tower_lower_20260916.png` also shows this ground. Other
views retain their existing lane; this is not a generalized obstacle detector.

**Live observed:** corrected runtime20260916T132437Z_e369463f first returned
from Blacksmith using its current template Back control, then performed the
same Institute acquisition with ground-lane pan (540,710) to (540,889).
Post-pan frames0027/0028 remained Home; fresh body acquisition reached Institute
frame0032. Its measured Economy category opened the actual Economy tree0033,
where capture stopped because category identity is not yet qualified. No
research, upgrade or item action occurred; the scoped lease released. Build
unknown; confidence high for the measured strip and this transition. Full
integration validation passed in the V13 full run (2449 passed,7 skipped) and
the final Research live route45be2a99 reached Wood Output I and returned Home.

## Atlas open-route observation boundary — 2026-09-16

Devin's V22 acquisition on 3xx_spies (active K303 level5 castle) exposed a
precomputed route that appended a coordinate tap derived from the pre-swipe
frame. The observed executor rejected that tap with FrameProvenanceError;
run20260916T213633Z_df961556 is the captured failure. Route planning also
consumed the predicted destination's tap attempt before a fresh frame arrived.
The later run20260916T215006Z_f0d0ee29 repeatedly returned the same Wall/Alliance
Hall view. The quest guide is visible; whether it pinned the camera or the
swipe lane failed is unknown. These reports do not establish Blacksmith absence.

The atlas planner now returns only its route swipes, requests a Home observation
after the last swipe, and plans any tap on the next freshly localized frame.
Predicted landings no longer populate remembered tap coordinates, including
focus-coordinate plans. Route planning leaves the destination tap attempt
available; an unchanged observed route signature stops with a diagnostic.
The measured NavigationCore building-camera path and its provenance guards
remain canonical and unchanged. Focused navigation checks passed 309 tests;
affected selection passed 1,152 with two skips (run
`2ab484f103b54897b78582db46e8334d`, candidate `54c036a`).

**Live observed:** Devin's `home-atlas-route-refresh` turn 002 on `3xx_spies`
started from a Castle/Infantry Home view at 23:25:29Z. The offscreen Alliance
Hall approach emitted three swipes and no tap. The last swipe requested a
fresh Home observation; the next plan consumed exactly that returned artifact
and fingerprint at 23:26:01Z with the same navigation state. The lead reviewed
the source/action/result records and the post-route/final images. Subsequent
anchorless views emitted no predicted coordinate taps. Evidence: the ignored
`vision-v01-foundation/.local-data/devin-live-test/runs/home-atlas-route-refresh/`
turn-002 manifest and `harness_run_log_turn002.json`; native frames under
`artifacts/2026-09-16/3xx_spies/20260916T232601Z_live_alliance_hall_route_alliance_hall_open_step_0_post_action_3.png`
and `20260916T232819Z_live_alliance_hall_route_restore_start.png`.

The run ended on clear Home at the existing flow-budget stop, with no spending,
alliance action or tap on an unobserved point; the lease released and the
instance was preserved. It did not reach Alliance Hall, so this accepts only
the swipe/reobserve/replan correction, not that building's route or V22.
The repeated-coarse-view diagnostic remains covered offline; live views had
different signatures. No further live repetition is required for this fix.
Build unknown; the route-refresh behavior is high confidence, while remaining
route non-convergence and Blacksmith availability are unresolved.
