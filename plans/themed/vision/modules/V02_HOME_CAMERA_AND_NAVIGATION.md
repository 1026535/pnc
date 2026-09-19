# V02 — Home camera localization and atlas navigation

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01. Deliverable: automatic Home → pan if needed → Institute, without depending on correctly spelled building OCR; qualify Tower and Campaign atlas targets from existing captures.

## Current owners and evidence

Reuse `app/pnc/domain/building_catalog.py` (`HomeCityMapAtlas`, coordinates and IDs), `app/pnc/navigation/spatial_navigation.py` (`HomeCityNavigator`), `app/pnc/vision/spatial_surfaces.py`, and `app/automation/engine/navigation_core.py` (`open_building`, `open_visible_building`). Current atlas helpers can estimate camera movement from gestures; that is not fresh visual proof. The replacement core currently requires observed target geometry.

Use tour 02_home/07_pan/08_institute and the OpenCV probes in the context note. The live shift (-468,-931) differs from the gesture.

## Implementation

1. Tie a small set of reviewed landmark crops to the **existing atlas coordinate system**. Check its origin, dimensions and scale against captures; correct one canonical atlas if necessary. Do not create an unrelated screenshot-coordinate map.
2. Add one PNC camera-localization producer in the vision layer. Match several stable terrain/structure patches with the existing OpenCV matcher; exclude HUD and protruding advertisements. Fit translation at supported scale from agreeing correspondences. Use ORB only if a bounded comparison shows patch matching cannot handle the observed overlap; do not ship two default engines.
3. Publish a small typed camera proof: frame, supported layout/scale, atlas-to-frame translation, matched landmark evidence and residual/quality status. Calibrate acceptance from positive/negative captures; correlation is not a probability. Ambiguous or insufficient landmarks produce unresolved localization.
4. Project the target slot, then verify its visible, unobstructed region and measured clickable body. Publish canonical `DetectedSpatialObject` evidence without labelling an atlas prediction as a template detection. Extend the existing observation contract narrowly if needed.
5. Integrate the navigator's bounded pan planning with this measurement. Invalidate points after pan, observe settled fresh frames, measure actual movement, re-localize and acquire again. Reuse existing attempt bounds; stop if localization stays unresolved or motion stalls. A predicted pan offset alone never authorizes a click.
6. Migrate the changed Home open path and its callers together. Confirm the destination screen after one building click. Keep name OCR as optional supporting evidence.

## Acceptance and proof

Target `test_home_spatial_objects.py`, `test_home_spatial_refresh.py`, `test_home_spatial_observation.py`, `test_open_building_core.py` and navigation tests. Use paired Home captures, a separated validation capture, a World negative, the observed HUD false-match case, and stale-after-pan rejection. Institute remains identifiable with “Insitute” or missing label. Tower/Campaign observed slots publish honest current bounds.

Start groups `unit.app.pnc.vision` and `unit.app.pnc.navigation`, then affected checks. One core-runtime live route starts on testing Home with Institute outside the usable viewport, pans within the existing bound, opens Institute and returns Home. Preserve camera proofs, before/after frames and action trace. Success requires the expected menu and return; stop on unknown localization or a wrong destination. No research is started. Seasonal/event qualification belongs to V03.

## Execution status

**Accepted for stated coverage, 2026-09-16 UTC.** Integrated with accepted
V01/V09 base `32a03492a2b83684582cb1868928d531c2064180`. One canonical camera
producer publishes independent current-frame proof through both observation
paths; sixteen landmarks in ten scene groups support Institute, Tower and
Campaign bodies. Campaign's canonical atlas action point is (2083,1121).

Lead architecture/caller review corrected single-pan handling to measured
replanning within the existing budget and fixed short Campaign corridor
corrections that otherwise overshot the acquisition band. Live findings added
qualified HUD-resistant plaza, Tower, ridge-wall and Alliance Hall evidence.
The Trial profile now uses its stable toolbar; Campaign's persisted southern
map view has a bounded two-anchor profile with the existing Home portal.

**Live passed on the authorized mega_old_acc active castle:**

- Home -> measured pan -> Institute -> Home.
- Measured Tower body -> Trial Challenge -> Home.
- Default Home -> two measured pans -> fresh Campaign body -> recognized
  Campaign map -> Home. Final camera returned to (-532,+222).

All phases used the configured DAILY_CANARY role, canonical scoped reservation
and keep-warm cleanup. No account/castle switch, research, Trial challenge,
battle, item use or resource spending occurred. The lead inspected the actual
menus and returns. Earlier stopped attempts and corrections are retained in
[workflow evidence](../../../../docs/game-reference/workflows/home-camera-navigation.md).

Offline verification: worker vision171 / navigation272 / both-publisher7 passed;
required affected selection fell back to full integration with **2,275 passed
and 7 skipped (2,282 total)**. After lead corrections, 93 navigation checks,
57 camera/pan/publication checks,one new both-publisher HUD regression,
20 Campaign profile checks and 3 profile-metadata checks passed; diff check
passed. The metadata count assertion initially failed after adding the profile
and was corrected before the three metadata checks passed. The full result is
reused for unchanged contracts; the later bounded fixes have targeted proof.

This accepts the captured/current ordinary appearance and three requested
routes. Seasonal/event variants belong to V03; other atlas residuals, Trial
card content and Campaign chapter/stage content remain with their named
packets. This is not a claim of universal Home-map coverage.
