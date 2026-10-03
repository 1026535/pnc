# V44 navigation: game-knowledge reconciliation — 2026-09-29

## Verdict and scope

**Implementation-ready for the existing widest-first, landmark-localized design.**
**Whole-V44 promotion remains pending its final candidate and route-specific proof.**
The user requested an independent Devin consultation against the recovered UI
mechanics and the extracted Home layout. The coordinator verified the material
claims below; a consultant memo is not runtime acceptance.

The consultation used repaired launcher revision `962b1c0a`, read-only automatic
permissions and packaged5.0.203/versionCode233 evidence. The first run terminated
on a prohibited PowerShell pipeline. An explicit file-read-only retry completed
with `READY_FOR_REVIEW` and an unchanged worktree. This verifies that bounded
consultation works; it does not establish that the launcher now recovers from
all rejected commands. Raw memo/result and copy provenance remain ignored under
`.local-data/devin-game-knowledge/v44-navigation-plan-20260929/` and
`.local-data/consult-context/` in the `v44-navigation-consult-20260929` checkout.

Some supplied plan copies predated the September27 layout clarification and
September28 publication/budget amendments. The coordinator compared them with
`origin/main` at `962b1c0a` before applying this review. The current V44-2/V44-3
layout contract and `max_home_seconds=90` amendment remain authoritative; the
consultation does not revert them or restore historical queue holds.

## What matches the evidence

| Decision | Independently checked evidence and limit |
|---|---|
| Fully zoom out first | Packaged `citymoveitem.lua:20-21,250-262` clamps orthographic size4-10, larger meaning wider. A nonzero wheel-axis sample changes size by0.5. This is not proof that one injected packet yields exactly one game update; current endpoint qualification remains visual. |
| Re-localize after normalization | `citymoveitem.lua:258-261,349-380` applies rebound after zoom. Equal scale does not establish equal pose; fresh fixed-landmark consensus remains required. |
| Reuse all54 ordinary pivots and16 system markers | Tracked `scene_geometry.json` contains those exact counts and the reviewed composed world-to-atlas fit. V44-2 predicts body regions; V44-3 selects pans. Slot eligibility and coordinates never supply current occupancy, hitboxes or availability. |
| Compute relative offsets as needed | `HomeCityCameraProof` uses a900x1600 reference. Existing projection maps `zoom * atlas + translation`, then native-frame scale. Keep signed component offsets and the single atlas; no pairwise table, edge homing or gesture odometry. |
| Pan then observe | `citymoveitem.lua:185-195,267-300,331-402` shows equal nominal axis scaling, direction-dependent boundary damping, clamping and settling. Away from those effects scene content follows finger motion. Actual measured profile direction/post-pan pose remain runtime truth;2.3 is not a universal usable gain. |
| Require fresh body and real destination/return | Packaged click routing gives area/button colliders priority over bodies (`:129-168`). Per-type dispatch and native UI identity are necessary. Existing Campaign entry/return evidence is distinct from the earlier merely-visible failed-tap case. |

All Lua paths above are beneath the primary checkout's
`.local-data/apk-exploration/gameplay-lua/scenes/cityscene/`.
The source baseline is not proof of the currently downloaded client. Existing
native qualification and current operation observations retain that boundary.

## Accepted clarifications

1. V44's final action point must be qualified clear of visible floating action
   bubbles and area/unlock controls. A collider name alone does not identify a
   screen rectangle. Body templates must retain clear native action evidence.
2. Use canonical per-family endpoints and measured returns. The shared military
   prefab is not sufficient identity; existing Infantry/Ranged candidates retain
   title plus family description, with a separate Back match. Cavalry/Siege still
   need their own native evidence. Wall's response-driven opening is handled by
   bounded observation, not by increasing or restarting its operation budget.
3. Resource body dispatch can collect multiple same-type buildings:
   `builditem_1015.lua:132-141`, `citybuildinfotopitem.lua:145-163`, and
   `commands/gain/gaincommand.lua:91-104`. Under the September 30 standing user
   policy, non-Main collection is authorized; observe the resulting state and
   actual arrival. Non-collecting proof applies only to an explicit read-only
   case or protected Main. `uis/resbuild/resbuildwin.lua:98-108` confirms that the resource
   title comes from the selected DTO, not a generic family-independent screen.
4. Preserve uncertainty at fringe views. Do not add landmarks from variable
   event objects, area masks or unknown occupants without native qualification.
   Campaign's capture-derived landmarks do not create an extra ordinary slot.

These changes clarify existing owners in [V44-4](V44_4_BUILDING_ROUTE_MIGRATION.md#entry-semantics-and-collection-effects).
They do not add another engine, registry, detector family or implementation slice.

## Consultant claims corrected or not promoted

- **Slot52/system13 proximity:** canonical coordinates differ by
  `(0.015002,-0.099)` world units, distance0.10013, or10.8388 unrounded atlas
  pixels. Rounded atlas delta is `(2,11)`. The memo's0.01world/~1pixel estimate
  is wrong. Close pivots still cannot identify either occupant; keep both unbound.
- **Zoom arithmetic:** at a900x1600 reference and orthographic10, the predicted
  relative scale is `80/108.2469877 = 0.73905`. This agrees with sampled endpoint
  fits but remains a model inference. Do not set a new tolerance from the memo's
  proposed±0.02 rule or infer injected detent counts from the source's0.5step.
  Retain qualified positives/negatives and existing saturation proof.
- **Empty dispatch branches:** `buildtabledata.lua:196-203` has empty VALKYRIE
  and TREASURE branches. That does not prove they can never open any current UI:
  building-specific handlers/current code were not established for that claim.
- **MerchantShip:** `buildtabledata.lua:167-173` directly opens a parameterized
  shop. The memo's classification with asynchronous send-driven destinations is
  not supported by that excerpt; do not add an async branch because of it.
- **Resource coverage:** the five resource types' collection risk does not block
  all35 configurable slots or the Recruiting/Infirmary occupants they also allow.
- **Extra validation:** do not repeat accepted zoom qualification or launch a new
  fringe exploration from this memo. Reuse final-candidate-valid evidence and
  collect missing observations during already-required route/discovery cases.

## Smallest remaining evidence and owners

| Boundary | Next owner/action | Acceptance limit |
|---|---|---|
| Scanner cycling and performance | Existing perception worker completes correction; coordinator reviews and integrates | Bank discovery and accepted route regressions use the final candidate; existing body absence is not positive unavailability. |
| Infantry5/Ranged7/Hall14 | Body worker qualifies native bodies; existing route candidate supplies endpoints/Back; Devin runs bundled public entry/return after integrated offline proof | Exact slot/body, intended family and canonical Home return; incidental completed-troop collection allowed on non-Main. Deeper actions only when needed by the assigned case. |
| Cavalry6/Siege8 | After body review, coordinator releases a bounded native endpoint/Back capture to live Devin, then reviews route qualification | Capture alone is not public-route acceptance; no bypass of the current public refusal counted as success. |
| Resource types | Live Devin captures body and popup-area views during the coherent route batch | Non-Main collection is authorized. Observe its effect, then prove actual selected-family destination and return; a collected resource is not route-arrival proof. |
| Fringe landmark sufficiency | Observe pose during the already-required discovery/route batch | Missing pose remains unresolved; no inferred bounds or unsolicited calibration tour. |

Live execution remains in the existing bounded batch on an exact reviewed clean
candidate, with leases, identity continuity and current CPU scheduling. This
planning review performed no live inputs and accepts no additional routes.

## October 3 native evidence and Cavalry acceptance

The coordinator independently reviewed Devin live015 on clean runtime
`e75c16363803d24e642870eeb8525dc84c602d03`, configured `157_farm`, active
`K157:0 sticker NPC`. The production Cavalry route normalized the camera,
panned, tapped the freshly measured slot-6 body once, observed its own
`building_cavalry_barracks` endpoint, and used the current visual Back match
to return to guarded Home. Cavalry opens directly on its body tap;
Watchtower's body-then-chip entry is a separate observed route. The evidence
validator and its fake now retain that distinction. No resource action was
recorded. Confidence is live-observed for this candidate and castle; the
installed client build was not measured in this batch.

The same batch's one slot-8 body tap opened the visible Siege Factory panel.
That frame supplies Siege's own title, artwork, family description and Back
appearance. This is discovery evidence: Siege still needs its own recognition
profile, measured Back, reviewed return edge and production open/return proof.
Neither its capture nor Cavalry's acceptance proves whole-V44 coverage.

Provenance: primary checkout
`.local-data/devin-live-test/runs/v44-q4-bank-watchtower-20261001/turn-015/evidence.json`;
original raw evidence and frames are linked there. The lead's independent
review is `.local-data/devin-vision-pipeline/V44_CAVALRY_LIVE015_REVIEW_20261003.json`.
The earlier Cavalry/Siege pending statements above are superseded to this
extent. The resource-capture row is superseded by the October 3 user scope
exclusion; all 54 atlas slots remain geometry evidence.
