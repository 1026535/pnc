# V44-1 — Native input and dispatch evidence

Parent: [V44](../V44_FULL_HOME_CITY_NAVIGATION.md#5-implementation-stages-and-integration-ownership).
Status: **specified slice accepted in private integration; isolated publication validation pending**. One substantial Devin implementation package; lead owns
transport design, interfaces, review and acceptance. Planning alone does not dispatch it.

## Outcome and dependency

Deliver the production input capability needed by V44: one authorized native wheel
detent and existing deliberate drag execution, with evidence of what actually
reached the device. The input layer reports dispatch, not zoom or navigation success.

Prerequisites: reviewed Stage 0 findings and the binding
[interface agreement, sections 2–3 and 6](V44_INTERFACE_CONTRACT.md).
Implement in parallel with V44-2 from the same clean immutable base. Use doubles
for the specified observation contract while V44-2 is under construction. This
slice does not import V44-2's new anchor type; it consumes coordinates plus the
existing authorizing Observation. Safe-anchor selection belongs to V44-3.
V44-3 consumes the integrated result and owns normalization/gesture sequencing.

## Exclusive code ownership

- `pnc_automation/core/infra/emulator/session.py` and the smallest necessary
  adjacent input-transport/lifecycle implementation.
- `pnc_automation/app/pnc/domain/action_requests.py` for the agreed input request;
  `pnc_automation/app/automation/engine/action_executor.py` for its dispatch.
- Corresponding session/actuator test doubles and focused input tests. Announce
  changed shared doubles in the brief; perception tests must not edit them concurrently.
- `read_only_policy.py`: explicit wheel permission only. `core_runtime.py`:
  input recorder wiring, cleanup and event-specific trace serialization only.
- New `core/infra/emulator/input_dispatch.py`, `scroll_transport.py` and pinned
  server asset/notice under its `data/`; their package-data entry in `pyproject.toml`.

Do not edit camera matching, landmark/body catalogs, observation publishers,
`NavigationCore`, scan policy or feature workflows. The lead reviews the preserved
uncommitted dispatch patch and supplies only reusable hunks relevant to this slice.

## Cohesive implementation scope

1. Productionize the smallest reviewed native scroll capability behind the
   canonical session/input boundary. The Stage 0 control-only scrcpy helper is
   evidence and reusable protocol knowledge, not a second runtime or a harness to
   copy wholesale. Contract section 3.3 fixes the pinned package asset, session
   ownership, setup/send limits, close order and no-replay behavior.
2. Support one signed detent at current native-frame coordinates through a typed
   action. Preserve frame authorization, input invalidation, account role/capability,
   task lease and current display-mapping checks. Keep Home zoom direction/endpoint
   policy outside the generic transport. Reject unsupported input explicitly.
3. Publish the actual sent drag endpoints, duration and input primitive after
   jitter, and the actual wheel point/detent/transport through existing diagnostics.
   A requested gesture or a pre-jitter coordinate is not dispatch evidence.
4. Ensure bounded setup/send failure and owned cleanup. Preserve pre-existing
   instance/process state and keep-warm policy; remove only transport resources
   owned by the operation. Never turn a failed/uncertain send into an automatic
   repeated game action. Preserve existing generic UI swipe behavior.

No normalizer loop, camera gain learning, safe-ground classifier, navigation retry
framework or alternative input backend belongs in this slice.

## Implementation sequence — follow in order

1. Read the reviewed helper's serializer/server options and compare the pinned
   asset hash. Extract the small production transport and package asset/notice;
   do not import from another worktree or `.local-data` at runtime.
2. Implement pure packet validation/encoding and immutable dispatch records.
   Fake the socket/process/ADB boundary before connecting the session owner.
3. Add lazy session transport ownership, bounded startup and cleanup. Preparation
   sends no game input. Validate the source frame after preparation and directly
   before the single send; ordinary session construction must remain side-effect free.
4. Extend the existing swipe at its final jitter/send boundary. Exact Home swipes
   preserve endpoints/duration and enforce current safe bounds. Return actual
   `SwipeDispatch` for both exact and existing generic paths. Apply the same
   exact/actual distinction to the final spatial body tap using the contract's
   `TapSpatialObjectAction.exact_geometry` and `TapDispatch`; generic taps retain jitter.
5. Add `WheelAction`, explicit Home swipe purpose and read-only policy permission.
   Add their executor branches without changing `execute_action`'s boolean API.
6. Bind successful low-level results to the authorizing `FrameRef`, install the
   optional recorder through CoreRuntime and retain typed values through its
   sanitizer. Recorder failure after dispatch is a reported failure, never grounds
   to replay the input. Close restores recorder ownership and cleans the transport.
7. Run the cases below, inspect the actual changed diff, return the source candidate
   for lead review. Live activity starts only in the separately assigned batch.

## Required deterministic cases

Each ID must appear in the evidence manifest with test module/method and result.
Several assertions may share a test; do not create a new framework for this table.

| ID | Setup / action | Required result |
|---|---|---|
| I1 | +1 and -1 single detents at valid native points | Exact 21-byte packets, vertical ±2048, horizontal/buttons zero; no extra touch packet |
| I2 | Boolean/noninteger detent, 0/2, edge-outside point, zero/oversized display, mismatched mapping | Explicit rejection; no input packet; no clipped replacement |
| I3 | Missing/stale/consumed/foreign-session frame; denied capability/lease; blocked guard | Existing authority refusal; no wheel/drag dispatch |
| I4 | Read-only policy allows swipes but not wheel; wheel allowed on another screen | Wheel denied; explicit current-screen wheel permission is required |
| I5 | Generic swipe with deterministic nonzero jitter | Legacy request semantics retained; receipt has post-jitter coordinates and duration |
| I6 | Home exact swipe and a gesture crossing/outside its safe rectangle | Valid gesture sent exactly; invalid one rejected before send; no clipping or jitter escape |
| I7 | Missing/hash-mismatched packaged server, handshake timeout, failed forward setup | Bounded setup failure, no game input; only successfully owned resources cleaned |
| I8 | Partial socket send / failed ADB swipe | Error and input invalidation; zero automatic retries; no success receipt |
| I9 | Close twice, epoch replacement, cleanup failure with primary send error, keep-warm | Owned resources removed before lease release, primary error retained, emulator/foreign resources preserved |
| I10 | Input record through actual CoreRuntime sanitizer; later runtime close | Typed point/count/sequence retained, source frame linked, no secrets; no stale recorder or duplicate event |
| I11 | Installed package / working directory differs | Same pinned server asset resolves; no runtime network/developer-path dependency |
| I12 | Exact spatial body tap with current expected object; generic jittered tap; point outside action bounds | Exact tap stays at the current qualified point; generic semantics preserved; actual receipts for both; unsafe exact tap refused |

Use named existing modules or the repository component groups
`py -3 tools/run_tests.py group unit.core.infra.emulator` and
`py -3 tools/run_tests.py group unit.app.automation.engine` as appropriate.
Do not run both a narrow passing selection and a broader group without a changed
boundary. Finished candidate: `py -3 tools/run_tests.py affected --base origin/main --explain`.

## Live handback cases

- **IL1:** production outward/inward wheel at a currently qualified safe point;
  record native before/after frames, actual detent/point, fresh scale evidence and
  absence of unexpected task-owned menu. A socket send alone fails this case.
- **IL2:** one representative production deliberate Home drag with exact geometry;
  actual receipt remains inside the measured lane and fresh fixed landmarks show
  pan. Include the existing generic swipe regression offline, not a duplicate live tour.
- **IL3:** release the task runtime; prove owned transport cleanup while the
  authorized instance remains warm. No broad process-kill checks or host repair.

IL1/IL2 may share V44-2 captures. Uncertain injection or an unqualified anchor
leaves the dependent case pending; classify and report the actual boundary.

## Acceptance and evidence

**Offline:** use the repository runner with the focused equivalents of
`tests/unit/app/automation/engine/test_swipe_input.py` and
`tests/unit/core/infra/emulator/test_emulator_session.py`, plus narrow native-scroll
transport tests. Cover signed packet/display mapping, fresh-frame/lease enforcement,
actual post-jitter evidence, existing swipe compatibility and owned cleanup after
the observed setup/send failures. Run affected selection once on the finished
candidate according to repository policy; retain its exact SHA and results.

**Applicable live boundary:** after lead review, Devin sends outward/inward wheel
input and one representative deliberate drag through the new production action
executor/session on configured `157_farm`, current active castle, verified clear
Home, canonical lease and current qualified input point. Reuse the parent Stage 0
evidence to choose conditions; do not repeat its exploratory threshold work.
The observable pass is actual dispatch followed by the expected scene-scale/pan
change, no unexpected menu, and verified transport cleanup. Coordinate this with
V44-2's publisher cases in one batch if both are ready; the diagnostic helper alone
cannot validate the new production path.

The batch supplies finite cumulative input limits across all processes. Stop on
uncertain send, unexpected page, unresolved input point or lost authority; record
the stopping boundary without repeating identical actions. Parent live authority,
zero spending, keep-warm and weekly incident policy apply. No production-main
promotion before the required input-boundary evidence passes.

## Handoff to V44-3

Return the exact candidate, reviewed request/dispatch contract, relevant changed
symbols, focused/affected results, actual-dispatch artifact example and remaining
live cases. Lead records review findings, resolves fixes and pins the integrated
input/perception base for V44-3. A successful transport send must never be presented
as normalized-zoom proof.
