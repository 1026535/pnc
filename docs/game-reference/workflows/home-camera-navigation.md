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
