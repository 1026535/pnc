# V44-2 — Normalized-view perception

Parent: [V44](../V44_FULL_HOME_CITY_NAVIGATION.md#5-implementation-stages-and-integration-ownership).
Status: **specified slice accepted; isolated publication runtime validated on `d5e74688`**. One substantial Devin implementation package; lead owns
uncertain evidence interpretation, shared contracts and acceptance.

## Outcome and dependency

From a fresh Home frame, publish the scene evidence needed for normalization and
navigation: a qualified input anchor or explicit absence, observed endpoint/scale
evidence, fixed-landmark camera pose, and current target-body identity/bounds.
This package observes; V44-1 dispatches and V44-3 decides what action to take.

Prerequisites: reviewed Stage 0/native captures, existing canonical geometry and
the [binding interface agreement, sections 2, 4 and 6](V44_INTERFACE_CONTRACT.md).
Implement in parallel with V44-1 using saved frames;
no input-transport dependency is needed for perception implementation.

## Exclusive code ownership

- `pnc_automation/app/pnc/vision/home_city_camera.py`, its existing shared catalog
  and Home camera/body recognition data.
- Home-specific publication in `observation_builder.py` and
  `navigation_perception.py`, with one canonical producer.
- `pnc_automation/app/pnc/domain/home_city_camera.py` and only the minimal agreed
  `SpatialSurfaceObservation.home_city_view` field in existing domain models.
- `spatial_surfaces.py:build_home_city_spatial_surface` and
  `observation_provenance.py:bind_spatial_surface` for the single producer/binding
  path. Home-specific enricher wiring may change only where needed to feed it.
- Camera/body perception fixtures and tests under `tests/unit/app/pnc/vision/`.

V44-1 owns session/actions/executor changes. V44-3 owns planner, normalizer and scan
policy. Existing 54 ordinary pivots plus 16 system markers remain the geometry
source. V44-4 later adds assigned route data/target keys through these interfaces;
this packet does not attempt every feature's menu or route migration.

### Extracted layout in perception

The user's 2026-09-27 layout clarification applies to **V44-2 as well as V44-3**.
Use `pnc_automation/app/pnc/data/home_city/scene_geometry.json` through
`home_city_slots.py` as the canonical relative-position reference for all 54
ordinary slots and the separate system markers. Its reviewed source and distance
transform are specified in [the layout contract](V44_3_NAVIGATION_ORCHESTRATION.md#canonical-layout-and-relative-distance-contract).

V44-2 combines the fresh landmark camera pose with those relative coordinates to
predict where each eligible slot's body should appear. Reuse
`HomeCityCameraTarget.atlas_action_point` and
`HomeCityCameraLocalizer.match_target_candidates`: the latter shifts an authored
body region by the candidate-minus-reference slot pivot, applies current scale
and translation, then requires a current image match before publishing occupancy
or an action point. Geometry alone cannot identify an unseen occupant. Preserve
all 54 coordinates even where no appearance or route has yet been qualified.
V44-3 consumes this evidence and chooses the pan; V44-2 performs no input.

Cover this contract through the existing P3/P9 transform and slot-body cases.
The handback must identify the geometry source and consumers, and distinguish
complete slot geometry from the subset of visually qualified building bodies.

## Cohesive implementation scope

1. Audit and reuse the current localizer/body matcher. Qualify its fully zoomed-out
   evidence using the native endpoint and held-out captures; distinguish relative
   game zoom from image resolution. Do not turn the observed ~0.743 fit into a
   universal camera constant or treat an unchanged image as proof of saturation.
2. Define endpoint recognition and uncertainty from measured, calibrated scene
   evidence. Supply the observations needed for V44-3 to distinguish actual
   convergence from ignored input. Do not publish an endpoint or transform from
   ambiguous/insufficient evidence merely to keep normalization running.
3. Supply a fresh visually qualified noninteractive scene anchor for zoom input,
   with frame/bounds provenance. Anchor detection before normalization must not
   require a normalized camera pose. A low-variance image patch or exclusion of
   label boxes alone does not establish noninteractive ground. If no qualified
   anchor exists in the supported view, return an explicit unresolved result.
4. Retain fixed-landmark consensus, independent scene groups and separated matches.
   Asset-derived candidates must agree with native screenshots before replacing
   reviewed patches. Variable building occupancy cannot establish a universal
   fixed anchor; projected candidates cannot prove their own identity.
5. Produce fresh normalized-view body identity, bounds/action geometry and slot
   association through existing catalogs. Keep unknown/occluded distinct from
   empty/unavailable. Publish the same evidence through both production publishers;
   retain invalidation on input, frame/context change and unexpected zoom.

Do not introduce a second map/matcher, synthetic navigation success, automatic
input, an occupancy database, or feature-specific route branches.

**2026-09-29 observation cost amendment:** The normalizer first asks the
canonical camera localizer for one endpoint-scale hypothesis. It does not run
the 15-scale search to classify every arbitrary intermediate zoom. A first
endpoint candidate receives a fresh unrestricted certification so the
existing cross-scale ambiguity/rival rule remains authoritative. Subsequent
same-operation normalized observations remeasure fixed landmarks at the
certified endpoint scale and resolve bodies/slots from their own frames. The
fixed-scale path is request-scoped and cannot make a non-endpoint or unresolved
frame actionable. A failed candidate may lead to another fresh certification
within the operation's passive, wheel-input and deadline limits; after success,
normalized pans do not repeat the sweep. Initial certification still incurs a
full sweep; it is
not a promise of an under-2.5-second first observation.

## Implementation sequence — follow in order

1. Inventory the retained native Stage 0 frames and current camera/body fixtures.
   Record source hashes, crop origins, actual native resolution and which frames
   are independent holdouts. Exclude overwritten/missing initial-phase artifacts
   and sparse-patch cumulative scale estimates from acceptance evidence.
2. Add exactly the view status/anchor/evidence types and `home_city_view` field
   specified in contract section 4. Keep the camera transform in the existing
   `HomeCityCameraProof`; keep current body/slot models and matcher signatures.
3. Qualify fixed-landmark endpoint scale against native endpoint and non-endpoint
   holdouts. Record measured spread, ambiguity and supported views before choosing
   the acceptance interval. A numerical limit requires this report and lead review;
   do not silently copy ~0.743 or manufacture independent frames by resizing.
4. Qualify noninteractive scene anchors at the pre-normalized supported scales.
   Link each anchor's visual identity to the reviewed native input and/or asset
   collider evidence. Define supported region and occlusion/HUD exclusions. If the
   evidence cannot establish a usable anchor in a required start view, report the
   exact gap; do not guess or ask V44-1 to pick a point.
5. Implement `analyze_view(image, *, camera_proof)` and the one shared producer.
   Bind frame/context through the existing provenance helper. Endpoint and anchor
   availability are independent; do not make anchor detection depend on AT_ENDPOINT.
6. Exercise current normalized body recognition and configurable/repeated-slot
   associations. Preserve existing independently qualified routes; route inventory
   expansion belongs to V44-4 after this shared algorithm handback.
7. Replay the same fixtures through both production publishers. Return calibration,
   current coverage and uncertainties for lead review before the combined live batch.

## Calibration handback — required fields

For each enabled calibration ID, supply one compact table or JSON artifact with:
native source/holdout paths and hashes, game build if known, layout/appearance,
frame/reference sizes, fixed group IDs, measured scale/residual values, accepted
interval and why non-endpoint examples do not overlap, anchor templates/regions,
native input evidence, rejected/unknown examples and unsupported view conditions.
This report is under ignored `.local-data`; authored templates and their sanitized
provenance/qualification metadata belong in tracked package/test data.

Do not bake account names, castle names, live frame paths or machine-specific
absolute paths into runtime qualification. No missing fixture may be replaced by
an unreported skip and still count as a passed recognition case.

## Required deterministic cases

| ID | Setup / input | Required result |
|---|---|---|
| P1 | Independent native endpoint views supported by a calibration | AT_ENDPOINT plus fixed-landmark pose, calibration ID and correct frame binding |
| P2 | Native closer view, ambiguous scale or unsupported layout | NOT_AT_ENDPOINT only when measured; otherwise UNRESOLVED/UNSUPPORTED; no invented transform |
| P3 | Same native scene at another display resolution versus genuine game zoom | Correct coordinate conversion; resizing alone cannot qualify endpoint recognition |
| P4 | Repeated art / movable occupant votes / conflicting or insufficient fixed groups | No false fixed camera consensus; projected candidate cannot validate itself |
| P5 | Supported pre-normalization scenery anchor while endpoint is false or unknown | Valid current native anchor where positively qualified; no circular endpoint prerequisite |
| P6 | Only low-variance ground, excluded labels, occluded anchor or HUD overlap | Anchor None unless positively qualified; no fallback coordinate |
| P7 | Both publishers analyze identical captured input with identical context | Same semantic view/camera/body evidence; producer invoked once per publisher path |
| P8 | Contradictory frame/context binding, old body after input | Provenance rejection; stale evidence cannot become actionable by rebinding |
| P9 | Body projection with missing/conflicting native match, repeated/configurable candidates | No tap-ready object or invented occupancy; current typed slot retained when proved |
| P10 | No connected session / ADB when importing or replaying perception | Pure offline result; no input, runtime connection or live artifact dependency |

Use the named Home camera/body/spatial modules in this packet or
`py -3 tools/run_tests.py group unit.app.pnc.vision` for changed shared publication.
Run `py -3 tools/run_tests.py affected --base origin/main --explain` once on the
finished candidate; reuse the passing result for unchanged source.

## Live handback cases

- **PL1:** from a supported non-endpoint start, the new publisher finds a qualified
  safe anchor before the production wheel input; its source frame and native point
  match V44-1's actual receipt. No point is chosen manually to hide matcher absence.
- **PL2:** after reaching the endpoint, the actual candidate publishes calibrated
  endpoint and fixed pose on fresh frames. Capture one deliberate pan and fresh
  pose/body afterward, sharing IL2 rather than sending duplicate gestures.
- **PL3:** document unresolved or unsupported observations encountered in those
  cases and confirm dependent input stops. Do not manufacture a disruptive live
  state just to cover a deterministic rejection already proven offline.

Live scope is the stated supported views. A complete recognition API with a missing
required anchor/endpoint calibration is still awaiting qualification for that view.

## Acceptance and evidence

**Offline:** use focused repository-runner selections for
`tests/unit/app/pnc/vision/test_home_city_camera.py`,
`test_home_city_slot_bodies.py` and `test_home_spatial_objects.py`, plus affected
publisher tests. Cover native endpoint recognition, unknown endpoint/anchor,
variable-occupant exclusion, separated/conflicting landmarks, HUD overlap,
scale versus resolution, stale body points and same-frame publisher agreement.
Use native holdouts for recognition; resized images prove only transform math.
Run affected selection once on the finished candidate under repository policy.

**Applicable live boundary:** in the reviewed V44-1/V44-2 combined batch,
capture the actual candidate's
publisher outputs at the reached endpoint and after a deliberate pan. Require a
qualified safe zoom point before input, correct fresh pose/body evidence afterward,
and explicit unresolved results where evidence is insufficient. Saved-frame replay
remains useful; it does not prove new anchor-controlled live input. Do not add
duplicate gestures merely to create a separate packet's evidence folder.

Use configured `157_farm`, current active castle, canonical lease, zero spending
and parent reporting/keep-warm rules. Stop dependent action on unresolved anchor,
pose or body; preserve the relevant frame and continue independent offline cases.
Whole-city recognition is claimed only for views actually qualified.

## Handoff to V44-3 / V44-4

Return the exact candidate and consumed evidence contract, supported endpoint/view
conditions, fixtures/provenance, current body/catalog coverage and unresolved gaps.
Lead pins the shared integration with V44-1. V44-3 consumes evidence without
duplicating matching; V44-4 extends target data without changing shared contracts
or relaxing thresholds independently.
