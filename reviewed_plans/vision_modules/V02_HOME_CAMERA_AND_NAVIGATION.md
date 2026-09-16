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

**In progress, 2026-09-16 UTC; not merged.** The implementation checkout is
`codex/vision-v02-home-camera`, integrated with accepted V01/V09 base
`32a03492a2b83684582cb1868928d531c2064180`. The shared producer, both publishers,
current-frame body targets and bounded measured-pan route are implemented.

Lead architectural/caller review corrected the worker's one-pan-only route to
replan from fresh proof within the canonical scan budget. Live testing exposed
HUD occlusion and loss of northern camera landmarks; the catalog now includes
the qualified south-plaza and Tower-body evidence (eight crops, five groups).
The Trial Challenge identity profile now uses its fixed toolbar instead of a
mutable Hero card. Body geometry has one canonical reference per asset.

**Live passed:** Home -> measured pan -> Institute -> Home, and measured Home
Tower body -> Trial Challenge -> Home. Tests used the explicitly authorized
mega_old_acc active castle, configured DAILY_CANARY role, canonical scoped
lease and keep-warm cleanup. No account/castle switch, research, Trial challenge
or spending occurred. See the [workflow evidence](../../docs/game-reference/workflows/home-camera-navigation.md).
The legacy Home-city-map smoke does not prove these new core paths.

Focused lead checks passed: 75 navigation tests; 41 camera/pan/both-publisher
checks before the Tower correction; then 33 camera/profile/publication checks
covering the final Tower correction. The original worker full run was2231passed
+7skipped before V09 integration and lead corrections. Final combined affected
integration checks remain due after the remaining Campaign changes.

**Remaining gate:** Campaign Home-portal calibration and target/route proof.
Worker turn004's bidirectional saved-scene comparison found no reliable bridge.
The lead is capturing one bounded horizontal Home pan from an already measured
camera to supply overlap. Its translation must be measured from scene pixels;
gesture displacement, Campaign/Arena OCR coordinates and the worker's suggested
intermediate coordinates are not proof. Keep V02 unmerged while independent
Research and Campaign-map work continues.
