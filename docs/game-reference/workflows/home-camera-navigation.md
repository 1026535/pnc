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
(-1423,-484), but fixed HUD overlays hid three eastern crops. Aqueduct and
ridge-wall (1117,1365,100,130) agree on the new camera from the east-
fortification group, and the scene-fixed Campaign portal body supplies the
second independent fixed group; Alliance Hall (1197,1675,140,80) also matches
but is a player-chosen multi-type occupant, so it corroborates without
establishing or contradicting the transform. Their match scores were
0.981/0.962, with aqueduct 0.952. The independently measured pedestal body
scored 0.922; its calibrated floor is 0.90 against retained non-Home
negatives below 0.40, with the same 8px projection-agreement requirement. The
catalog has 16 patches in 10 groups. This failure is pinned by the post-pan
HUD fixture.

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

## Castle/courtyard landmark coverage, 2026-09-21

V44's production Home routes failed localization on the serious_stuff current
castle. The initial Infirmary view remains outside the landmark catalog and an
explicit Stage C prerequisite. The live exploration subsequently used unqualified
fixed scan gestures; their captures support offline image research, not acceptance
of safe production navigation or the recovery sequence.

Five new landmarks are exact crops of the authored 900x1600 reference: Castle
fountain and tower in one castle_structure group, garden_west in courtyard_garden,
and statue_wings plus plaza_ring in the existing plaza_low group. The statue and
its circular base must not count as two independent structures.
The Castle crops were independently checked against mega_castle; statue/garden
crops against tower_pan_28. Their existing independently localized frames agree
on position with the authored bounds. Plausible source appearance does not grant
universal support for other castle levels or missing landmark regions.

Tracked home_city_castle_default_20260921 (seek_0) localizes at (-532,+222), zoom1,
with three votes from castle_structure and plaza_low. The held-out panned frame
home_city_castle_holdout_20260921 (seek_4_after_1) localizes at (-545,+149), zoom1,
with four votes from castle_structure, plaza_low and courtyard_garden.
Both came from the same live session; they are different views, not independent
account/build qualification. Only the private chat band was masked. The complete
fixture manifest records original and sanitized digests.

Camera localization remains separate from fresh visible target-body proof. Both
Castle fixtures authorize no building target; the qualified target set remains
Institute/Tower/Campaign. Three agreeing patches from two genuinely independent
groups remain required. All old landmark definitions and confidence floors remain.

The initial thirteen-crop expansion raised observer cost; lead review retained
only the five crops needed for these observed coverage cases. On this machine,
the paired saved-frame probe fell from 13.65/13.90s to 9.85/9.92s per localization,
preserving both poses and required groups. Those are offline measurements, not
end-to-end live timing or a guaranteed navigation deadline. The 45s navigation
budget is unchanged and final live route qualification remains required. Native
zoom then had only algorithm-fixture evidence; the 2026-09-22 wheel captures
below now qualify the two sampled scales.

## Coarse-to-fine search correction, 2026-09-22

V44 foundation live run20260922T000737Z_863e028d (157_farm) failed its
post-pan confirmations: content observations cost ~27-55s each, so the 45s
two-settled-observation budget could not hold two observes after the gesture
dispatched, and the Campaign leg hit the 30s frame-provenance bound. Offline
diagnosis on the actual failed frames put ~16.6-16.9s of each observe inside
camera localization: 15 zoom scales x 22 fixed landmarks searched globally at
native 900x1600.

The correction keeps the one OpenCV matcher and adds a bounded coarse-to-fine
entry: one half-resolution proposal frame per localization, per-scale coarse
proposals at each landmark floor minus 0.20, distinct neighborhoods
deduplicated at coarse Chebyshev radius 3 and refined natively at the
unchanged floor, bounded to 8 neighborhoods per landmark/scale; more distinct
proposals fall back to the exact full-resolution search rather than truncating
a possible rival. Scale grid, fit/consensus/ambiguity rules, movable-landmark
exclusion and final target-body proof are unchanged.

On all five saved live008 frames (pre/post Institute, ambiguous Tower,
post-Tower, Campaign) the corrected search returned identical verdicts,
transforms, zooms, vote sets and target bodies; the ambiguous Tower frame
stays ambiguous with no actionable body. Camera localization fell from
~14.5-17.1s to ~2.8-4.3s per frame; whole content observation on the failed
post-Institute frame measured 25.43s to 11.65s cold and 22.05s to 9.27s warm
on this machine. Zero exact-search fallbacks occurred on those frames.
These are offline saved-frame measurements: live route re-qualification
remains required, the -0.20 proposal margin and bounded coarse candidate ranking
can miss native matches on unseen content or scales. Non-1.0 zoom then had only
algorithm-fixture evidence; the 2026-09-22 wheel captures below now qualify
the sampled scale ~1.072.

## Center correspondences for camera fitting, 2026-09-22

V44 foundation live run 20260922T014849Z_873314fa (157_farm) showed the
Institute leg dispatching one pan, confirming Home twice, then refusing its
pre-tap source frame (0036) as conflicting_zoom_hypotheses; no building tap
was sent. The earlier live008 Tower pre-tap frame (0040) carried the same
refusal. Diagnosis: the localizer fitted corresponding template crop
top-lefts, but neighboring template scales crop the same feature at
different sizes while each match stays centered on the physical feature;
top-lefts therefore carry a size-dependent bias, and three weak 0.95/1.05
matches of the true 1.0 scene disagreed with one another by more
than the 10px rival bound; each stayed within that bound of the strongest
1.0 fit.

The correction fits corresponding match-bounds centers against each
landmark's canonical reference center: observed vote positions, pair
seeds, residuals, the least-squares zoom/translation fit, consensus
translation, evidence centroid, cluster separation and reported residuals
all use float centers. Authored reference_bounds and measured match bounds
are unchanged for evidence, target matching, action geometry and
rendering; target-body projection keeps its separate top-left contract.
The 3px consensus, 10px rival-translation and 0.10 rival-zoom bounds, all
scales, all-pairs contradiction checks, minimum evidence and movable-
landmark rules are unchanged.

Both saved failure frames are now authored native fixtures
(home_city_institute_pretap_20260922.png,
home_city_tower_pretap_20260922.png): they localize at atlas (-537,-402)
and (-534,-372) - image translations (-5,-624) and (-2,-594) - at zoom
1.0. A deterministic differing-template-size regression proves scale
invariance, and genuine competing transforms still reject as ambiguous.
Live route re-qualification on the corrected fit remains required; native
zoom input beyond the two sampled scales and the remaining unproven slot
coverage stay open.

## Corridor-entry stroke start, 2026-09-22

V44 live012 on 157_farm (run 20260922T035556Z_a0a3c9b4, checkout
7116e58) re-qualified the corrected-fit Institute and Tower routes and
ran one bounded Campaign start-location diagnostic. With the fresh proof
at (-525,-871)@1.0, the planner's short DOWN corridor entry resolved a
centered corridor-adjacent segment; the earlier production attempt from
proof (-545,-856) had dispatched the same kind of stroke and measured no
camera motion. The diagnostic relocated only the segment's start onto the
measured lane scene point - atlas (1072,1550), 40px inside the
Tower/Blacksmith ground lane, projecting to (547,679) - kept the original
69.53px finger displacement, direction, 320ms and touchscreen primitive,
and sent one stroke. Source frame
20260922T040109Z_..._0058_c4_campaign_lane_source.png; settled frame
20260922T040127Z_..._0060_c4_campaign_lane_diag_after_1.png; exact action
and lane fields in the run's curated turn-012 evidence.json.

The camera moved to (-521,-711): atlas view-center delta (-4,-160). The
160px content motion against the 69.53px finger displacement is the
existing ~2.33 content gain, not overshoot. The observations support using
this start position for the scoped correction. Different capture times and
camera poses mean they do not isolate the earlier failure cause or qualify
the production Campaign route. The current game build and final Campaign
target body remain unmeasured in this run; no Campaign tap was sent.

The planner now prefers that qualified scene start only for a DOWN
corridor entry whose whole relocated segment still fits the transformed
lane and HUD-safe band; upward corridor entry, horizontal acquisition,
body corrections and all other lane behavior are unchanged, and an
unfittable segment falls back to the prior plan. Actual production
Campaign acquisition and return on the final candidate still require a
dedicated live route, including fresh post-stroke localization and body
proof; predicted landing is not proof. Separately noted for run hygiene:
the same run's first content baseline captured a PNC_LOADING frame, so it
cannot count as a localized Home timing, and the noncontent-derived
estimate is not acceptance evidence.

## Native wheel-zoom captures, 2026-09-22

V44 wheel-validation turn-020 on 157_farm (sticker NPC/K157, client
5.0.204/235) supplied the first independently verified native game-zoom
captures. One wheel -1 input increased scene scale; the inverse wheel +1
restored it. The lead replayed the unchanged OpenCV localizer on the
frames and accepted the sampled scales only.

Three smallest native 900x1600 frames are tracked fixtures
(`home_city_native_zoom_{baseline,holdout,restored}_20260922.png`):

- baseline: measured zoom 1.0, atlas translation (-532,+222); 11
  correspondences across 6 independent scene groups; Institute body
  qualifies via p6_path_right at (724,1253).
- holdout (after wheel -1): measured zoom 1.071989179 — off the 0.05
  hypothesis grid — at atlas translation (-603,+78); 9 correspondences
  across the same 6 groups. The p6_path_right Institute body crop is
  unmatched at this scale, so that revision localized the frame without
  qualifying an Institute target.
- restored (after wheel +1): zoom 1.0 again but atlas translation
  (-532,+73), not the baseline pose. Zoom restoration is not camera-pose
  restoration.

The eight landmarks shared by all three frames inverse-project to the same
atlas positions within ~1.2px across the zoom/pose change. Qualified scope:
the two sampled scales only. No continuous zoom interval, zoomed panning,
zoomed body taps, discovery, or ordinary routes are qualified; whole-plan
V44 acceptance is unchanged. The run used two sequential leases after a
cold-start preflight retry — recorded as a harness deviation, not a model
for future live reservations.

## Ordinary body and minimum return candidates, 2026-09-22

The lead reviewed the saved 157_farm foundation captures and added two body
targets without adding camera landmark votes. Wall uses the gatehouse at
reference bounds `(1180,1845,95,125)`, slot 2, and candidate point `(1221,1923)`.
The tracked native f6 holdout measures point `(118,983)` with score `.9943`;
it immediately follows crop-source f5 at essentially the same pose, so this
does not establish cross-pose or cross-account coverage. Source hashes and
the private-chat mask are in `tests/data/home_city_slot_bodies/manifest.json`.

Goddess first used the circular platform trim at `(380,1352,160,36)`, slot 15,
candidate point `(460,1372)` — zoom holdout and restored fixtures matched it
at `(461,1311)` and `(460,1222)`. Lead review of the final005 Goddess frame
showed that trim is decoration rather than a proved clickable body; the
2026-09-23 retarget below binds the same slot to the gold statue column.
Current camera, slot, body, HUD-safe geometry, and fresh reacquisition still
gate each actual tap.

The minimum Wall destination profile comes from the retained 2026-09-18
serious_stuff overview (`wall_overview_20260918.png`): title and static
description jointly own identity, and only its measured Back is exposed.
Blacksmith reuses its existing title/description profile and measured Back.
The candidate graph gives each its feature-owned Home return, preserving
the previously observed parent relationship. This does not port V34 content
or Defense Info, or the V22 Gear feature. Confidence is artifact-observed for
these bodies and historical parents; final-candidate entry/return and native
zoomed acquisition still require Devin live validation. Bank and Warehouse
body evidence remains unresolved and neither is considered unavailable.

## Wall acquisition through the eastern corridor, September 22

Artifact-observed: own157_farm run `20260922T232718Z_26f6cf57`, frame0050,
localized at zoom1 and translation `(-532,222)`. The subsequent horizontal Wall
pan led to healthy Home frames0051-0053 with no landmark correspondences. The
saved-frame diagnosis in `correction026-20260923/wall_camera_diagnosis.json`
reproduced the source proof and zero post-pan votes at every configured scale.
The native captures remain under `artifacts/2026-09-22/157_farm/`.

Repository-proven geometry explains the gap: at this default camera pose the
existing eastern patches start at reference-image y1306 or farther down, leaving
their full crops outside the usable scene. A horizontal pan alone cannot bring
them up. This is reference-image geometry, not an additional atlas translation.
Wall now uses the same measured southern corridor as Campaign before horizontal
acquisition. The corridor is evaluated in atlas space at the observed zoom; actual
post-pan localization, fresh body proof, the gesture budget and thresholds remain
unchanged. This is a route correction supported by saved evidence, not new live
acceptance. Corrected-candidate Wall entry and owned return remain pending.

## Northeast camera coverage, 2026-09-23

V44 final live002 on 157_farm captured clear 900x1600 Home views where the
camera faced the northeast district — Sauroi Lair, Watch Tower approach and
the moat fortification — and every existing catalog landmark scored below
floor, so two consecutive frames returned no correspondences. Readiness,
identity and lease checks passed and no input was sent; the failure was
catalog coverage, not geometry or identity.

Three fixed-structure crops extend the catalog northeast. They were measured
on the normalized 900x1600 rendering of the tracked
`home_city_campaign_hud_occluded_20260916.png` fixture (image translation
(-891,-707), atlas (-1423,-485)) and remeasured against live002 baseline
frame0004 at normalized template scores .9828/.9220/.9779. Their authored
reference bounds are Sauroi pier (1361,957,90,125) in the new
sauroi_lair_structure group, and moat cap (1246,1112,95,115) plus moat shaft
(1291,1227,70,95) joined to east_fortification — cap and shaft are two parts
of one physical fortification, not independent votes. The lead inspected all
three: fixed pier arches and moat architecture, no HUD, nameplate, promotion
or level badge. All three are fixed landmarks; no new camera target or tap
was authorized.

The tracked holdout `home_city_northeast_holdout_20260923.png` is the native
900x1600 RGBA live002 frame
`20260923T020508Z_core_20260923T020504Z_1de57f30_0003_c1_home_baseline_a.png`
with only the private-chat band (rows 1390-1484) masked. The consecutive
same-pose frame `..._0004_c1_home_baseline_b.png` (eleven seconds later)
corroborates locally but is not cross-pose proof. Crop-source build (the
2026-09-16 fixture session) is unrecorded; the final 2026-09-23 live002 build
was not freshly read, so no client version is claimed here.

Expected regression transform: zoom ~1.0, atlas translation about
(-1251,+139), three fixed correspondences across sauroi_lair_structure and
east_fortification. This is calibration coverage for an observed blind spot,
not broader qualification: no route, tap, zoom range or additional slot
coverage is claimed, and live acceptance of any corrected route remains
pending. The campaign_left_pedestal landmark added below now also matches
this holdout at .9714, so the current catalog corroborates it through a
third independent group.

## Campaign pedestal and the wall corridor, 2026-09-23

V44 final live turn003 on 157_farm (run 20260923T054248Z_9c46e534) re-passed
the Institute, Tower and Campaign entry/return legs, but the Wall leg's
second pan landed on a clear corridor view (frame0064) where only the
east_fortification crops could vote: the movable Alliance Hall cannot
establish a camera and the Sauroi pier sat behind the top HUD. Wall never
opened; the same localization failure left the Goddess, Blacksmith,
discovery and wheel cases pending. No popup, identity or host incident
occurred and nothing was spent.

One fixed landmark corrects the gap without changing the voting rules:
campaign_left_pedestal at reference bounds (1371,1222,85,135), a second
measured region of the same fixed Campaign structure. It joins the existing
campaign_portal group alongside the portal body, so the two crops are one
structure's correspondences and can never count as independent votes; no
new camera target, tap geometry or route is added. The lead authored the
crop from the tracked home_city_campaign_hud_occluded_20260916.png fixture
(source rectangle (480,515,85,135) on its (-891,-707) normalized
rendering); the asset carries the stone pedestal and stairs with the cyan
inset and no nameplate, HUD, badge or tappable promise. Measured scores on
the real matcher: .9729 on the failed corridor frame0064, .9708 on the
consecutive frame0072, .9714 on the northeast holdout.

The tracked fixture home_city_wall_corridor_regression_20260923.png is the
native 900x1600 RGBA turn003 frame
20260923T055023Z_..._0064_c3c_wall_home_post.png with only the private-chat
band (rows 1390-1484) masked. It was the diagnosis source for this
correction, so it is a live regression sample, not an unseen holdout; the
later frame0072 (same pose) corroborates but is not cross-pose proof. On it
the camera localizes at zoom 1.0, atlas translation (-1298,-645), through
campaign_portal plus east_fortification with the movable Alliance Hall
corroborating only; the existing Wall slot-2 body qualifies at action
point (456,1057), score .9846, projection error 1.41. Masking the pedestal
region reproduces the live INSUFFICIENT outcome.

This is catalog coverage measured offline on saved live frames: no new live
pass, Wall entry/return, destination or route qualification is claimed, and
the still-pending Goddess, Blacksmith, discovery and wheel cases keep their
own live requirements on an integrated candidate.

## Goddess statue body retarget, 2026-09-23

V44 final live005 on 157_farm (run `20260923T105322Z_174413f3`) reached the
Goddess case and sent one tap from frame 0066; the workflow stayed Home.
Lead review showed the `goddess_drum` target matched the circular platform
trim at native `(316,283,160,36)`, candidate `(396,303)` — scene decoration
never proved clickable, so the platform is no longer input authority.

The retargeted body is the static gold statue lower column/plinth measured
on that same frame: native crop `(368,145,60,78)` under camera `(-595,-847)`
at zoom 1.0, converted through the existing atlas offset `(-532,+222)` to
reference bounds `(431,1214,60,78)`. The action stays inside the column at
reference `(461,1269)` in a `20x20` box; the crop excludes the upper HUD,
the mutable level badge at the statue's right edge, the floating nameplate
and the platform ring below. Slot 15, the `.90` score floor and the 12px
projection bound are unchanged; no landmark vote or localization rule moved.

The whole native RGBA frame is tracked as
`tests/data/home_city_slot_bodies/home_city_goddess_slot15_0066_20260923.png`
(chat rows 1390-1484 masked; source and derivative digests in the manifest).
It is an observed regression/validation sample, not an independent holdout.
On it the body matches slot 15 at `(368,145,60,78)` score `1.0` and the
candidate action lands at `(398,200)` — above the HUD-safe tap band — so
production must pan and reobserve before tapping; the observed no-entry is
consistent with that requirement, not proof the tap works.

On the 2026-09-22 wheel fixtures the body matches the zoomed holdout at
`(462,1201)` score `.9794` and the restored frame at `(461,1120)` score
`.9754`; it also matches the older tower_pan_28 and mega_castle views at
`(277,245)` and `(103,473)`. The zoom baseline honestly stays unmatched —
that capture renders the column uniformly darker (`0.877` below the floor)
— and the slot12_f2 banner view occludes the column (`0.846`). Thresholds
were not loosened. Final Goddess entry/return and the pending discovery and
wheel cases still require integrated live validation.

## Eastern final-pan ground segment, 2026-09-23

Final034 live005 frame `20260923T105703Z_core_20260923T105322Z_174413f3_0040`
localizes at `(-1562,-845)`, zoom 1. Its short Campaign correction proposal
crosses the Wall at native `(216,774)` to `(216,825)`; the next live frame
is Wall. The reduced trace did not retain issued coordinates, so gesture
length alone is not an established cause.

The saved frame visibly contains open grass below Campaign at native
`Bounds(375,300,30,65)`, atlas `Bounds(1937,1145,30,65)`. Final measured
eastern corrections now project this scene-owned segment through the fresh
camera proof and place the whole gesture inside it and the existing HUD
band. A missing or clipped segment refuses input. The measured motion goal,
gain, corridor bounds, and requirement to localize and match again before
tapping are unchanged. Native/normalized geometry, the prior Wall pose and
center-preserving zoom, and clipped-ground refusal pass 27 planner checks.
Confidence is saved-frame geometry plus deterministic planning; actual
movement and final Wall/Campaign transitions remain pending live validation
on the combined candidate. The observed run used the client's 5.2.81 hot
update; no cross-account ground or click qualification is claimed.

## Fountain wheel trajectory, 2026-09-27

**Live-observed:** V44 input/perception turn003 on157_farm, candidate
`a1179981`, runtime `20260927T173755Z_152e21f4`, used the production executor
and `scrcpy_control_v4` transport at a current-frame fountain match. A-1 wheel
changed the fixed-landmark scale from1.0 to1.07294; a+1 returned it to1.0.
Two more+1 inputs reached0.93519 then0.87963 while retaining Home. The next
input was correctly refused: the fountain was visible but no authored template
scale matched. No pan occurred before widest normalization. Installed build
was not recorded in this run; this is evidence for the captured appearance.

**Saved-frame measured:** native frames0030 and0033 retain the fountain at the
two intermediate sizes. The former matches template scales0.88–0.98, best0.94
with score0.97475 and current point(450,699); the latter matches0.84–0.92,
best0.88 with score0.97537 and point(450,657). The catalog adds these measured
positive search scales at the unchanged0.9 floor. It retains direct patch
matching, correspondence agreement, the calibrated in-patch offset, native-size
and HUD gates. Search scales are template sizes, not endpoint classifications.
The two native fixtures and their source/file/decoded-pixel hashes are in
`tests/data/home_city_camera/manifest.json`; only private chat rows1390–1484
are masked. They are correlated regression samples from this run.

Wheel qualification does not authorize a tap or drag on the fountain. A missing
current patch still stops input. Broad all-pose coverage, completion of widest
normalization and exact measured-lane pan/post-pan proof remain live gates on
the corrected candidate. Canonical54-slot map geometry is unchanged.

## Endpoint-first observation amendment, 2026-09-29

**User-confirmed behavior goal:** Before a public Home body/pan action, zoom
out until the city agrees with the calibrated minimum, including when the
first frame is already at that minimum. A still frame after a wheel can mean
an ineffective input; it cannot itself prove saturation.

**Repository-proven design on this candidate:** The same Home camera catalog
and fixed-landmark localizer first test the calibrated endpoint-scale
hypothesis. A qualified current scenery anchor permits one bounded outward
wheel when that probe has not proved the endpoint. The next frame must either
fit the endpoint or show a shrinking same-patch anchor/measured scale change
before another wheel. An endpoint candidate receives a fresh unrestricted
localization to reject cross-scale rivals. Only then does the request retain
the normalization fact. Subsequent pans acquire fresh landmark translation,
body pixels, action bounds and slot identity at the endpoint scale on each
new frame; no old point is reused. Session, frame, Home identity, calibration,
input budget and interruption gates remain in the core operation.

The endpoint interval `[0.738,0.744]`, nearest non-endpoint rung at `0.74692`,
and qualified fountain/moat wheel patches come from
`pnc_automation/app/pnc/vision/data/home_city_camera/normalization.json` and
the native 2026-09-25/27 captures described above. The first endpoint
certification still runs a broad scale sweep. A failed candidate can prompt
another fresh certification within the operation's passive, wheel-input and
deadline limits; a successful operation uses fixed-scale fresh reacquisition
after certification,
including later pans. Native trajectory fixtures prove only observed segments:
the 2026-09-27 fountain .935 to .879 pair and the 2026-09-25 moat .871 to
.824 pair are within-run, while the saved endpoint and Warehouse post-pan
frames come from other sessions. The authored native regression therefore
does not claim a continuous wheel-to-endpoint or same-operation pan trace.
This candidate has only lightweight fake/static checks so far. Native
matching, timing, and actual wheel-to-endpoint acceptance remain pending after
CPU/live release.
