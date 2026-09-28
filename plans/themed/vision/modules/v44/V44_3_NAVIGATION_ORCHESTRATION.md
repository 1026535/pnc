# V44-3 — Normalization and navigation orchestration

Parent: [V44](../V44_FULL_HOME_CITY_NAVIGATION.md#5-implementation-stages-and-integration-ownership).
Status: **specified core slice accepted on `5edeb042`; isolated publication runtime validated on `d5e74688`. Whole V44 is incomplete.**
One cohesive Devin implementation package. State transitions, public APIs and
budget/invalidation rules are fixed in the
[binding interface agreement, sections 2 and 5–7](V44_INTERFACE_CONTRACT.md).
The lead supplies reviewed reusable hunks from the preserved candidate at dispatch.

## Outcome and prerequisites

Make `NavigationCore.open_building` and explicit discovery enter through one
normalization gate, then use landmarks and the canonical slot map to navigate:

**recognize Home → normalize fully out → verify endpoint and landmark pose →
resolve target → deliberate pan → fresh rescan → verify body → tap once → verify destination**.

Start from an immutable integration of V44-1's input capability and V44-2's
perception contract, after independent review and required input/anchor proof.
Reuse current scan/occupancy and calibrated geometry where their behavior fits;
this is completion/refactoring of the preserved candidate, not a rewrite of it.
No route consumer may integrate an unfinished version of this shared contract.

## Canonical layout and relative-distance contract

User clarification, 2026-09-27: use Devin's extracted Home-city layout as the
reference for relative distances between **all 54 building slots**.

- **Single geometry owner:**
  `pnc_automation/app/pnc/data/home_city/scene_geometry.json`, consumed through
  `domain/home_city_slots.py` (`home_city_slot_eligibility`, `home_city_slot`,
  `home_city_system_markers`). Keep all slots 1–54, including unbound and locked
  slots, plus the 16 separate system markers. Geometry availability does not
  imply an occupied, unlocked or supported building route.
- **Provenance:** the packaged 5.0.203/233 `BuildingPosition` extraction comes from
  `split-1.apk`, `assets/ABAsset.pkglzma_14`, scene offset 17844917. Its scene-bundle
  SHA-256 is `b4c0a3c4f14ffe286873a040b740b8eaa76def444164449a541e5acd1197b105`,
  matching Devin's 2026-09-25 asset consultation. The packaged geometry retains
  composed world positions, the reviewed world-to-atlas calibration and its
  5.0.204/235 visual corroboration. Reuse this calibrated data; do not substitute
  the consultation note's rounded coordinates or nominal catalog hints.
- **Relative offsets:** for source slot A and target slot B, subtract their
  canonical atlas pivots: `delta = (B.x - A.x, B.y - A.y)`. Horizontal and vertical
  separations are the signed components; diagonal distance is
  `sqrt(delta.x**2 + delta.y**2)`. Derive these as needed from the existing owners;
  no separate 54-by-54 distance table, learned pan-distance map or second atlas.
  In world units the calibrated conversion is
  `atlas_delta = (k * world_delta.x, -k * world_delta.y)` before pivot rounding.
- **Current view:** normalize fully out first, then obtain a fresh fixed-landmark
  pose. Project with `reference_point = zoom * atlas_point + translation` through
  `HomeCityCameraProof`; native pixels additionally use its frame/reference scale.
  Pairwise reference offsets are therefore `zoom * atlas_delta`. A single
  building match cannot establish both unknown zoom and translation. Resolve
  movable/repeated occupants to a currently observed slot before using their
  identity as a location hint.
- **Navigation:** retain the existing scanner's nearest eligible-candidate
  ordering and the camera target's slot-pivot delta. Use the current projected
  target/body region to choose the smallest correction that makes it usable
  inside the safe viewport, subject to qualified gesture length, lane, overlap
  and budget constraints. A qualified longer gesture or intermediate view may
  be necessary. Geometric distance does not establish drag-to-camera gain.
  After every pan, reobserve landmarks and recompute the remaining offset; final
  tapping requires a current matched body and destination proof. Slot pivots do
  not define hitboxes, and a missed tap must not be snapped to the nearest slot.

The dispatch brief must name this source and require the handback to identify the
actual geometry consumers. Review the existing consumers before adding helpers:
`HomeCityScanState.candidate_slots`, `HomeCityCameraTarget.atlas_action_point`, and
`plan_home_city_camera_pan`. Complete their shared orchestration through this
slice; merely loading the layout file is not implementation acceptance.

## Exclusive code ownership

- `pnc_automation/app/automation/engine/navigation_core.py`: Home entry,
  normalization, acquisition/discovery and bounded observation sequencing.
- `pnc_automation/app/pnc/navigation/spatial_navigation.py`: `HomeCityNavigator`
  and Home pan/waypoint planning symbols; preserve unrelated World navigation.
- `pnc_automation/app/pnc/navigation/home_city_scan.py`: request-local coverage,
  occupancy, target candidates, progress and stop reasons.
- Existing core building-acquisition and Home pan/scan/selection tests.

Use V44-1/V44-2's agreed inputs/evidence. Changes to their shared types, transport
or matcher return to their owners through the lead; no shadow helpers or copied
normalizer in feature callers. The lead classifies relevant unfinished source
hunks from `vision-v44-lead` and supplies a reviewed baseline without unrelated edits.

## Cohesive implementation scope

1. Add one bounded normalization sequence at every new Home acquisition/discovery
   entry, including the direct visible-building path. Fresh qualified endpoint
   evidence may make it an observation-only no-op. Reentry, unexpected zoom or lost
   continuity invalidates that proof. Keep it once per operation, not per pan.
2. Consume a fresh V44-2 anchor for each required V44-1 wheel action; distinguish
   ineffective input from proven endpoint convergence. After zoom, discard old
   camera translations/body points and relocalize. Stop explicitly if input,
   anchor, endpoint or pose cannot be established within the finite bound.
3. Resolve visible verified target, observed-slot hint, single eligible geometry,
   nearest uninspected candidate, then bounded search in the parent's order.
   Preserve exact requested slot across reacquisition. Static eligibility never
   asserts occupancy, and an unfound building never becomes unavailable by timeout.
4. Replace unsupported tiny corrections with deliberate qualified pans that
   preserve enough landmark overlap. Use current projection to choose movement;
   actual displacement is measured afterward. Do not assume constant axis gain,
   infer pose from swipe accumulation, or use edge homing as the normal locator.
5. Reuse one request-local scanner for directed acquisition and non-tapping
   discovery, with separate terrain coverage and occupancy inspection. Preserve
   valid corridor revisits while rejecting cycles. Keep the existing shared pan
   budget, separately finite normalization bound and bounded passive observation;
   no phase or retry silently replenishes them.
6. On the observed post-pan localization loss, allow the parent's bounded passive
   reacquisition. Unresolved pose stops further motion/tapping. A stalled action
   may use one genuinely different qualified route within the same budget; do not
   repeat unchanged gestures. Reacquire the requested current body before the
   single tap and require its feature-owned destination/return contract.

This slice owns the full state machine and its deterministic regressions, not
ordinary target-by-target catalog completion. V44-4 consumes the stable result.

## Implementation sequence — follow in order

1. Verify that the assigned immutable base contains reviewed V44-1/V44-2 APIs and
   their input/anchor qualification. Record those dependency SHAs. Do not write
   temporary fallback adapters to an unintegrated worker branch.
2. Add the contract's Home policy limits and stop reasons using existing owners.
   Reuse one request-local scan state and one operation deadline, including the
   normalization gate. Preserve result field meanings and non-Home policy behavior.
3. Implement one internal normalization function shared by all three public
   entrypoints. It accepts current observation/callback/state/deadline, returns
   the confirmed current endpoint observation, and never calls a public entrypoint
   recursively. Qualified endpoint can be a zero-wheel no-op; mere stillness cannot.
4. Wire the current scanner after that gate. Carry the exact requested slot;
   static candidates guide searching, observed bodies prove occupants. Keep direct
   visible acquisition visible-only after normalization and discovery non-tapping.
5. Replace the observed small-correction failure with qualified deliberate motion
   and current-lane exact dispatch. Refuse a too-short safe segment; select a
   different qualified corridor only when current localization supports it.
6. Remeasure endpoint, camera and bodies after input. Handle observed first-frame
   localization loss with bounded passive observations. Apply cycle/progress and
   shared budgets without resetting them on fallback/corridor transitions.
7. Final reacquisition uses current object/point, exact geometry and pinned slot in
   the existing spatial tap contract. Keep one tap, observed destination and feature-owned
   return semantics. Emit the contract's typed navigation/stop events.
8. Complete deterministic cases, hand the candidate to lead review, then run the
   separately assigned final-candidate live batch and return its curated evidence.

## Required deterministic cases

Use scripted observations/actuator doubles; assert both result and complete input
sequence. A passing final screen with extra unapproved inputs is a failing case.

| ID | Observation sequence / request | Required action sequence and result |
|---|---|---|
| N1 | Two current endpoint frames, visible requested body | Zero wheels/pans; one current-body tap; correct destination required |
| N2 | Supported closer start, successive measured zoom changes, two endpoint frames | One outward input per iteration; no old pose/body reuse; normalize before target resolution |
| N3 | Unchanged measured NOT_AT_ENDPOINT after input | Bounded passive classification then ZOOM_INEFFECTIVE; no saturation claim or identical replay |
| N4 | Missing anchor, unresolved endpoint, denied provenance, uncertain send | Correct stop/error boundary; no guessed point, recovery swipe or repeated send |
| N5 | Zoom-input cap, pan cap or operation deadline reached | Exact counters retained; no phase reset; typed exhausted reason and no further input |
| N6 | Reentry/new operation and unexpected mid-route scale | New operation normalizes again; current operation stops ZOOM_CHANGED without recursive restart |
| N7 | Body needs a tiny unsafe correction, or exact stroke would leave lane | Deliberate qualified alternative or NO_SAFE_GESTURE; never shrink/jitter outside qualification |
| N8 | Post-pan ambiguous first frame then localized frame; all frames ambiguous | Passive recovery then continue in first case; localization stop without another pan in second |
| N9 | Slots 11–13 eligible, exact repeated-instance selector supplied | Search geometry distinct from occupancy; selector survives every pan and final reacquisition |
| N10 | Inspect candidate but no body match; repeated-view corridor progress/cycle | Unknown occupancy retained; useful transit allowed, repeated no-progress cycle bounded |
| N11 | Visible-only entry loses target during normalization; explicit discovery | Visible-only does not start offscreen search; discovery never taps an occupant |
| N12 | Stale/mismatched final body, callback consumes frame, wrong destination | No stale tap; refresh or stop; wrong destination never accepted and no second building tap |
| N13 | Different frame/reference sizes, clamped movement and asymmetric actual displacement | Correct transform units; next pose is measured, never accumulated from swipe gain |
| N14 | Shared state/result and trace serialization integration | Pan/wheel counts and step/stops survive sanitizer; existing unrelated navigation remains unchanged |
| N15 | All 54 canonical slot pivots; representative horizontal, vertical and diagonal offsets under different camera translations | Domain geometry retains every extracted slot; existing projection/candidate/planner cases prove offsets derive from the canonical pivots, scale correctly and are recomputed after measured motion; no copied distance table or inferred occupancy |

Run the existing focused Home scan/pan/slot modules and
`tests.integration.workflows.test_open_building_core`, or the owning
`py -3 tools/run_tests.py group unit.app.pnc.navigation` group for a shared planner
change. Finish with `py -3 tools/run_tests.py affected --base origin/main --explain`.
No raw test discovery or automatic separate full-suite run after a passing full fallback.

## Required live cases and evidence mapping

| ID | Distinct behavior | Required proof |
|---|---|---|
| NL1 | Supported closer start and already-wide start | Production gate converges with measured feedback; already-wide entry sends no unnecessary wheel |
| NL2 | Offscreen acquisition across meaningful pan | Qualified exact gesture, fresh fixed pose, current requested body, one tap and intended destination |
| NL3 | Campaign/Wall correction regression | The actual problematic geometry is handled by qualified motion or a truthful bounded stop; an unresolved required route is not accepted |
| NL4 | Available configurable/repeated-slot request | Current occupant and exact requested slot maintained to final body/route proof |
| NL5 | Institute/Tower/Campaign affected entry/return regressions | Existing supported destination and feature return survive the new gate on the final candidate |

Combine overlapping NL2/NL3/NL5 cases when one route exercises the same boundary;
map all relevant IDs to it. Live denial/uncertainty cases need not be provoked when
deterministic proof suffices. If a required target is positively unavailable,
record that evidence and applicability; a failed scan remains unresolved. The
shared slice can report partial qualified coverage but cannot mark pending required
cases passed or release a dependent route as accepted.

The manifest must include the actual imported source root and candidate SHA,
native before/after frames, per-frame endpoint/pose/body proof, actual input records,
target/slot decisions, cumulative counters, destination/return observations and
weekly incident IDs. Trace completeness is checked before accepting the batch.
For the existing offscreen NL2/NL3 case, include the selected canonical target
slot/marker, projected target offset and measured post-pan offset. This proves
the layout guides production navigation without adding 54 separate live runs.

## Acceptance and evidence

**Offline:** use the repository runner for the existing `test_open_building_core`
module and focused `test_home_city_camera_pan`, `test_home_city_scan`,
`test_home_city_slot_selection` and `test_home_city_duplicate_targets` modules.
Cover normalization from differing starts/no-op at endpoint, ignored input,
pre-normalization anchor failure, invalidation on reentry/zoom, lost-pose passive
recovery/stop, deliberate correction versus unqualified microdrag, correct units,
slot11–13 candidates, exact-instance persistence, unknown occupancy, corridor
progress versus cycles, budgets and wrong-destination refusal. Run the repository
affected selection once on the final candidate; let shared-contract risk expand it.

**Applicable live boundary:** after independent review, Devin executes production
`build_core_runtime`/`CoreWorkflowRunner` navigation on the exact clean candidate.
Use the parent batch and representative materially different Home views/start
zooms. Prove normalization, an off-screen acquisition with pan/rescan, fresh-body
tap, intended destination and verified return. Cover the observed Campaign/Wall
correction issue and available configurable/repeated-slot behavior without running
every building yet. Include Institute/Tower/Campaign regressions affected by the
new entry gate; retain unchanged valid evidence where dependencies permit.

Preconditions: configured `157_farm`, active castle identity, clear Home, canonical
lease and available target. Batch records finite cumulative actions and saved
before/after frames, endpoint/landmark proof, actual dispatch, decisions and stops.
Zero spending; no castle/account switch. Unknown destination, exhausted bound or
unresolved authority stops dependent input; parent incident policy and keep-warm
rules apply. Fixes require affected review/retest on the final candidate.

## Handoff to V44-4

Return the reviewed API/selection/error contract, exact integration revision,
deterministic and live evidence, current qualified routes, and explicit outstanding
coverage. V44-4 may then migrate independent target groups. Slice acceptance proves
shared navigation for stated cases; all available ordinary routes still need the
parent's coverage gate before V44 is complete.

## 2026-09-28 implementation and gesture amendment

The integration candidate now shares widest-first normalization and a narrow,
guarded Home observation request. The measured planner replaces the former 2.33
gain, universal 70px floor and proportional corridor corrections with individual
native profiles. It uses the same canonical 54-slot/system-marker geometry and
fresh matched bodies; every subsequent pose is observed, never predicted.

Current profile scope is native 900x1600 with calibrated widest endpoint evidence:

- Paved courtyard `Bounds(1216,806,194,62)`: exact horizontal 114px/429ms;
  both directions independently reviewed from dandy turn007 native receipts and
  before/after frames. This proves sampled displacement, not all routes.
- Tower/Blacksmith strip `Bounds(1042,1510,60,265)`: exact vertical 179px/425ms.
  Earlier downward motion remains scoped evidence; upward production behavior
  requires the next candidate live check.
- Institute/courtyard `Bounds(1152,754,258,400)`: only a current TEMPLATE Institute
  at slot9 may start at body-center+(0,1), with exact vector(+73,-207)/488ms.
  This is the named Stage0 exception, not permission to drag arbitrary buildings.
  Final production bridge/route evidence is still required.

The usable region is the inward-rounded intersection of the independently mapped
region and native `Bounds(150,250,620,920)`, which excludes side docks and the
entire bottom quest/chat area. This amends the development harness's unnecessarily
strict whole-original-envelope rule: clipping removes area and never expands
it, changes the stroke length, or builds bounds from its endpoints. The complete
fixed stroke must fit the resulting rectangle; clear-ground profiles retain 9px
end margins. A matched foreign body overlapping that rectangle refuses the
proposal. Existing screen/popup/provenance gates remain mandatory.

This resolves the observed 1–3px post-pan settle refusal without widening the HUD
window. Unsupported display/scale, missing current endpoint/body, insufficient
lane extent and stalled directions stop explicitly. Required closer-start,
Campaign/Wall, configurable-slot and entry/return cases remain pending until their
actual postconditions are observed on the final candidate. Broader live coverage
is not implied by deterministic profile geometry tests. The durable coordinator
ledger and live batches under ignored `.local-data/` own exact candidate and
acceptance evidence.

### Turn009 route findings and final-frame correction

Campaign was acquired by production perception after four actual pans on
365304ad. The next mandatory body capture pushed elapsed time from40.14s to45.66s,
past the unchanged45s operation deadline. On a later operation, a body matched on
the endpoint frame then disappeared on the extra frame as an animated offer glow
overlapped its template. These are distinct observed stopping boundaries; they do
not establish that the Campaign route had no planner proposals or no visible body.

The final tap now validates the latest endpoint-confirmation or post-pan observation
and its matched body directly. This is a fresh observation from the same operation,
not a cached older point. An intervening target callback still forces a new capture;
absent, ambiguous, stale, wrong-slot and wrong-destination proof still stops input.
The45s operation bound and30s session provenance bound are unchanged. A visual-test
approval must occur outside a paused input call; turn009's93s gate correctly failed
the session guard and does not justify weakening production freshness.

The eastern view also exposed a missing westward return lane. A candidate exact
rightward114px/429ms profile uses independently inspected paved ground west of
Alliance Hall: atlasBounds(1448,1343,213,66), from native x200..360,y635..685 at
translation(-886,-372),zoom.75 in turn009 frame0028. Inward projection gives
Bounds(200,636,159,48), with candidate(222,659)->(336,659). The current pose, clear
Home, mapped-region/safe-window intersection and observed foreign-body exclusions
still apply. This new lane permits rightward return only, with9px ground margins
on both axes; it needs live qualification before acceptance. Do not infer leftward
coverage or camera gain from it. It is a source correction to the observed dead end,
not authorization for arbitrary map drags.


### September 28 turn013 acceptance amendment

Candidate `5b838b10` passed the affected runner: 3,421 portable tests passed,
7 skipped. Campaign entry/return was accepted on production-identical `026694d2`;
Tower of Trial entry/return passed on `5b838b10`. These are sampled route proofs,
not completion of this slice. The coordinator reviews are
`.local-data/devin-vision-pipeline/v44-live-turn012-review-20260928.md` and
`v44-live-turn013-review-20260928.md` in the primary checkout.

Two remaining defects now have explicit decisions:

1. **Home operation lifetime.** Six qualified outward detents and eight fresh
   observations consumed 50.152 seconds on the supported closer start. The old
   45-second operation correctly stopped before Institute input. Sepia turn008
   measured the complete narrow pipeline on two saved frames; path/decode caching
   saved at most 0.11 seconds per observation and did not address the bottleneck.
   Apply the interface contract's `max_home_seconds=90` to the entire Home
   operation from its original start, including normalization, scan and final
   destination confirmation. Preserve ordinary `max_seconds=45`, the 12-wheel
   cap, pan budget, per-frame qualification and 30-second input provenance.
   Callers setting a custom Home time limit must use `max_home_seconds`.
   N5 covers the recorded six-detent timing and refusal at the same later deadline.
   NL1 must still pass a complete public operation from a closer view on the
   final candidate; extending the budget is not live acceptance.
2. **Southern horizontal route.** At pose `(-110,-414)`, zoom `.738873`, Wall and
   exact Blacksmith slot 12 require leftward motion while the existing horizontal
   terrain regions are outside the input window. Canonical offline replay of the
   exact native frame correctly recognizes Blacksmith in slot 12; no slot-binding
   exception is warranted. Correction `2b0bf267` adds the independently surveyed
   southern terrace `Bounds(860,1815,215,70)`, projecting to native
   `Bounds(526,928,158,50)`. The provisional left stroke is
   `(661,952)->(547,952)` in 429ms. Existing routes on both axes retain priority;
   the terrace is considered only when those fail. Current body intrusion,
   display/scale, endpoint, margin, exact-dispatch and stalled-direction guards
   remain mandatory. The 53 focused planner/scan/slot checks pass. The new region
   needs candidate live qualification and successful Wall/Blacksmith routes.

Next coherent live batch: qualify the terrace while opening Wall and exact
Blacksmith slot 12, and prove Institute entry from a supported closer starting
view within the new total budget. Campaign's reviewed entry/return may be used
once to establish the naturally closer Home view observed in turn012, with its
own explicit batch allocation. Do not manually move the camera to hide a missing
production route or relax current-body/slot proof. Retain unaffected Tower proof;
retest any changed boundary. Recheck accepted route priority offline.

Manor/Workshop remains pending an authorized castle level 24 or higher. The
C15 target's observed lock toast is a feature-unlock precondition, not a missed
click. The existing incident remains linked from the coordinator ledger. Legacy
`ScreenFlows`/`HomeCityNavigator` consumers are not claimed migrated by these
three core entrypoints; V44-4 and the broad plan queue remain held.

### September 28 turn014 core acceptance

The coordinator independently accepted NL1-NL5 on `5edeb042321cf756e61923a7266124a72bf39672`, combining final turn014 evidence with unaffected Campaign turn012 and Tower turn013 proof. Turn014 opened Wall using two measured southern-terrace strokes, exact Blacksmith slot12, and Institute after six outward detents from an observed closer start; all owned returns passed. The closer-start operation took70.945 seconds within the single90-second Home lifetime. The final affected gate passed3,426 tests with7 skips.

This acceptance covers the shared APIs and specified routes. Remaining legacy caller migration belongs to V44-4; Manor/Workshop still needs an authorized C24+ target. M retains its separate45-second bound, which the measured closer-start case does not meet. Publication scope and retained evidence are defined in [V44-1/2/3 publication](V44_1_3_PUBLICATION.md).
