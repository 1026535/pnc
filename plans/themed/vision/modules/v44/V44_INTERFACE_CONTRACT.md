# V44 — Binding interface and implementation agreement

Design revision: **2026-09-25 / contract 1, with dated amendments below**. Status: **shared V44-1/2/3 publication accepted for its recorded cases; V44-4 in progress**.
Parent: [V44](../V44_FULL_HOME_CITY_NAVIGATION.md). Implementation owners:
[V44-1](V44_1_NATIVE_INPUT.md), [V44-2](V44_2_NORMALIZED_VIEW_PERCEPTION.md),
[V44-3](V44_3_NAVIGATION_ORCHESTRATION.md), [V44-4](V44_4_BUILDING_ROUTE_MIGRATION.md).
This reference is shared by exactly four slices; it is not another delivery slice.
The user has resumed V44 and the dependent queue. The coordinator ledger owns
current dispatch and candidates; this reference does not release a new live run.

## 1. Decisions already made

1. Every new Home acquisition or discovery normalizes to **fully zoomed out**.
   A fresh positively recognized endpoint can satisfy this without sending input.
2. Camera position comes from current fixed-landmark consensus. Gesture distance
   proposes a next view; it never supplies the resulting camera position.
3. Reuse `HomeCityCameraProof`, `FrameRef`, `Bounds`, `HomeCitySlotSelector`,
   `DetectedSpatialObject`, `HomeCityScanState` and `HomeCityScanResult`.
   Keep the canonical 54 ordinary slot definitions and 16 system pivots.
   Devin's extracted layout is the relative-distance reference for **all 54
   slots**: derive horizontal, vertical and diagonal offsets from their packaged
   coordinates. The source, transform and consumer requirements are specified in
   [V44-3's layout contract](V44_3_NAVIGATION_ORCHESTRATION.md#canonical-layout-and-relative-distance-contract).
4. Native wheel input is one signed detent through the session/action boundary.
   The production backend is the reviewed **scrcpy 4.0 control-only transport**.
   No pinch backend, runtime downloader, general mouse API or second runtime.
5. Qualified Home pans and final body taps preserve their planned geometry exactly.
   Generic existing swipes/taps retain their current jitter behavior. Both exact
   and generic paths publish actual dispatch.
6. A current body match authorizes the final tap; a projected slot never does.
   A fresh destination observation proves arrival. Feature owners prove return.
   This requires the [reviewed entry semantics](V44_4_BUILDING_ROUTE_MIGRATION.md#entry-semantics-and-non-collecting-preconditions):
   current action-point qualification, family-specific destination evidence and
   resource non-collecting preconditions are not supplied by a body match alone.
7. Required live proof runs through the actual production candidate after lead
   review, under a separate bounded Devin assignment. Offline success is not live acceptance.

**Reading order for workers:** current AGENTS and applicable skills → parent V44
sections 1–4 and reviewed Stage 0 findings → this agreement → assigned slice.
Use current source for existing behavior; the additions below describe intended
implementation. Do not claim these APIs already exist on the planning branch.

The inspected source baseline is `6e2e3ea2a1e1d58435b8d5e935a73abff66c92f7`.
Planning commits follow it. At execution resumption the lead supplies an immutable
current base and reconciles intervening changes. This does not reopen the decisions
here unless source evidence exposes a concrete incompatibility.

## 2. Units, identity and proof lifetime

| Value | Unit and owner | Required interpretation |
|---|---|---|
| Frame point / `Bounds` on input or matched object | Integer native screenshot/display pixels | Origin top left; x right, y down; valid points satisfy `0 <= x < width`, `0 <= y < height` |
| `Bounds` | Existing x, y, width, height model | Positive extent; use half-open right/bottom edges for input containment |
| Reference image | Existing 900 × 1600 basis | Resolution-normalized image pixels, not Android input pixels |
| Atlas point / slot pivot | Existing canonical atlas units | Reuse scene geometry and atlas transforms; signed coordinates do not imply camera limits |
| `HomeCityCameraProof.zoom` | Relative atlas-to-reference scale | Not client orthographic size; not display resolution; ~0.743 is one sampled fit, not a universal constant |
| `translation` | Reference pixels | `reference_point = zoom * atlas_point + translation`; native projection uses the proof's frame/reference sizes |
| Wheel detent | Integer exactly -1 or +1 | Transport sign only; V44-3 maps +1 to outward using the qualified Home profile |
| Gesture duration | Integer milliseconds | Actual dispatched value; never infer movement from duration alone |
| Slot identity | `HomeCitySlotSelector` | Preserve requested slot across reacquisition; semantic object ID alone does not identify a repeated instance |
| Frame identity | Existing `FrameRef` | Session ID/epoch, capture and input sequence, timestamp; never reconstruct one from a filename |

All actionable view evidence must match its containing observation's frame,
screen, layout and frame size. A missing frame reference is permitted for pure
offline image analysis, but cannot authorize input. Bind proof once through the
canonical provenance publisher; reject conflicting binding rather than overwrite it.

Any input consumes its source frame. After zoom/pan, discard old body points and
pose for dispatch. A new observation supplies new proof. A normalization result
may remain a request-local fact across a qualified pan only while fresh measured
scale still agrees with the endpoint profile and instance/castle continuity holds.
Reentry, unexpected zoom, session epoch change or lost identity discards that fact.
No cache of actionable points or normalized state survives a public operation.

## 3. V44-1: input requests and actual dispatch

### 3.1 Public action contract

In `app/pnc/domain/action_requests.py`, add the following frozen, slotted action
with keyword-only required fields (inherited `ActionRequest` defaults stay unchanged):

```python
class WheelAction(ActionRequest):
    x: int
    y: int
    vertical_detent: int
```

Reject booleans/nonintegers; detent must be exactly -1 or +1. Bounds and display
mapping are validated against the authorizing observation at execution. Wheel
coordinates receive **no jitter**. No horizontal scroll, pressed buttons, tap
prefix, tap suffix or implicit repeat. `observe_after`/`follow_up_request` retain
their existing meanings; V44-3 explicitly observes each normalization action.

Extend existing `SwipeAction` by adding:

```python
exact_geometry: bool = False
safe_bounds: Bounds | None = None
```

Add `SwipePurpose.HOME_CITY_CAMERA = "home_city_camera"`. Home camera actions
require explicit start/end ratios, `exact_geometry=True` and nonempty native
`safe_bounds`. Both resolved endpoints, and therefore their straight segment,
must lie inside this rectangle and the current display. Reject rather than clip
an invalid gesture. Exact geometry disables endpoint **and duration** jitter.
For non-Home swipes defaults preserve existing behavior and primitive support.
If optional bounds are supplied for another swipe, validate its actual post-jitter
endpoints before sending. A rectangle is a qualified gesture lane, not a claim
that every point on the city map is noninteractive.

Also add `TapSpatialObjectAction.exact_geometry: bool = False`. When True, require
the current `expected_object`, matching target point and nonempty action bounds;
the point must lie inside those bounds and the current display. The executor passes
those bounds and exact mode to the session. Home final-body taps use True. This
closes the same requested-versus-dispatched gap for clicks: `tap_point` currently
jitters coordinates, so merely validating the requested body point is insufficient.
Other tap callers retain defaults; this does not add a second spatial tap action.

`NavigationActuator.execute_action(action, observation) -> bool` and
`ActionExecutor.execute_action(...) -> bool` keep their signatures and meaning:
True means input dispatched, not scene changed or destination reached.
The action executor must validate read-only policy, action eligibility, current
guard, frame provenance, deadline/input budget and session lease/capabilities.
Wheel never inherits permission merely from `allow_swipe`.

Add `ReadOnlyProbePolicy.allow_wheel: bool = False` and
`allowed_wheel_screens: frozenset[ScreenType] = frozenset()` using the existing
swipe-policy pattern. With read-only enforcement enabled, both wheel opt-in and
matching screen are required. Preserve the disabled policy's current behavior;
this policy does not replace live role, lease or spending authority.

### 3.2 Session boundary and evidence types

`BlueStacksSession.swipe` retains existing parameters and accepts keyword-only
`exact_geometry=False`, `safe_bounds=None`; return a `SwipeDispatch` on success.
Existing callers may ignore that return. Add:

```python
def scroll_wheel(
    self, x: int, y: int, *, vertical_detent: int,
    frame_size: tuple[int, int],
) -> WheelDispatch: ...

def tap_point(self, x: int, y: int, *, exact_geometry: bool = False,
              safe_bounds: Bounds | None = None) -> TapDispatch: ...
```

Use the existing dispatch lock/input-sequence decorator and `_require_input`.
The executor retains `authorized_input(observation.frame_ref)`. The scroll
transport must not bypass the session, build its own account connection or acquire
a competing task lease. Validate native display 0 mapping; if the current frame
is scaled, rotated inconsistently or cannot be mapped, refuse input explicitly.

New immutable records belong in `core/infra/emulator/input_dispatch.py`:

| Type | Required fields |
|---|---|
| `SwipeDispatch` | `start: tuple[int,int]`, `end: tuple[int,int]`, `duration_ms: int`, `input_source: str`, `gesture_primitive: str`, `input_sequence: int` |
| `WheelDispatch` | `point: tuple[int,int]`, `frame_size: tuple[int,int]`, `vertical_detent: int`, `transport: str`, `input_sequence: int` |
| `TapDispatch` | `point: tuple[int,int]`, `input_sequence: int` |
| `InputDispatchRecord` | `source_frame: FrameRef`, `dispatch: SwipeDispatch \| WheelDispatch \| TapDispatch` |

`transport` is `scrcpy_control_v4` for this backend. Records describe successful
command/socket submission; Android injection and game response are asynchronous.
Create the low-level result from the actual values at the final send boundary,
never from the incoming request. Do not synthesize a successful receipt after an
exception. Pre-dispatch validation failure sends nothing; a partial/failed send
is uncertain, invalidates the old proof and cannot be automatically replayed.
Retain `DeviceConnectionError`/existing provenance error families with an explicit
failure phase (`setup`, `mapping`, `send`, `cleanup`) in diagnostic details.

Add an optional `ActionExecutor.input_dispatch_recorder` callback taking
`InputDispatchRecord`, default None. Bind the session result to the source frame
inside that executor and emit it immediately after successful dispatch. Existing
logger diagnostics remain usable when no callback is installed. The connected
core attaches its trace adapter once and restores any previous callback on close;
do not leave a recorder pointing at a closed runtime or double-emit records.

### 3.3 Transport ownership and deployment

Implement the production backend in new
`core/infra/emulator/scroll_transport.py`. Reuse protocol knowledge from the reviewed
helper, not its diagnostic orchestration. Package the pinned server as
`core/infra/emulator/data/scrcpy-server-v4.0` through the existing setuptools
package-data mechanism; include the pinned upstream license/notice alongside it.
Obtain that notice from the corresponding upstream version before committing the
asset. Do not copy the 2,200-line qualification harness into production.

The asset must be **732226 bytes** and SHA256
`84924bd564a1eb6089c872c7521f968058977f91f5ff02514a8c74aff3210f3a`.
Missing/mismatched asset fails before remote setup. There is no fallback download
or arbitrary local binary selection. Test packaging so an installed distribution
resolves the same asset independently of the current working directory.

The packet is exactly `>BiiHHhhI`, 21 bytes: type 3, signed native x/y,
unsigned width/height, horizontal scroll 0, vertical scroll `detent * 2048`, buttons 0.
Display dimensions are integers in 1..65535. Reuse the reviewed helper's explicit
control-only server options: video/audio/clipboard/settings/power mutations off,
display 0, forward tunnel, one control socket and dummy-byte handshake.

The session lazily owns at most one transport per session epoch. Setup precedes
final source-frame authorization so startup latency cannot make an otherwise
unvalidated stale frame usable; revalidate the original frame immediately before
send, and stop if stale. Transport preparation itself sends no game input.
Reuse the connected session's configured ADB client/serial. Remote jar, server
identifier, localhost forward and owned process handle are unique to this session.
Use no-rebind forwarding; remove only that forward and owned remote file/process.

Bound setup at 10 seconds; socket send at 2 seconds; graceful process exit at
5 seconds followed by at most 2 seconds for owned-process termination. These are
engineering limits, not measured game response times. A setup handshake may retry
within its bound before any input; a scroll/drag send must not retry on uncertainty.
After setup, every input still passes current lease/frame/capability checks.

Close/epoch replacement releases transport resources **before** releasing the
task lease, even after send failure. Cleanup is idempotent and preserves a primary
exception while reporting a secondary cleanup error. Never stop ADB globally,
kill a foreign server or close a keep-warm BlueStacks instance. Offline tests use
fake subprocess/socket/ADB boundaries; importing this module starts nothing.

## 4. V44-2: one scene-evidence producer

### 4.1 Typed additions

Add to existing `app/pnc/domain/home_city_camera.py`:

```python
class HomeCityZoomStatus(StrEnum):
    AT_ENDPOINT = "at_endpoint"
    NOT_AT_ENDPOINT = "not_at_endpoint"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"

@dataclass(frozen=True, slots=True)
class HomeCityZoomAnchor:
    point: tuple[int, int]
    bounds: Bounds
    qualification_id: str

@dataclass(frozen=True, slots=True)
class HomeCityViewEvidence:
    zoom_status: HomeCityZoomStatus
    reason: str
    calibration_id: str | None
    zoom_anchor: HomeCityZoomAnchor | None
    frame_size: tuple[int, int]
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None
```

Add `SpatialSurfaceObservation.home_city_view: HomeCityViewEvidence | None = None`.
Do not duplicate `camera_proof` inside it: relative zoom, translation and landmark
votes remain in `HomeCityCameraProof`. The enclosing evidence binds its anchor to
the same frame. Reasons are diagnostic text; decisions branch on the typed status
or absence, not string matching. At-endpoint requires a qualified calibration ID
and current fixed-landmark scale proof. Non-Home surfaces carry no Home evidence.

Add `HomeCityCameraLocalizer.analyze_view(image, *, camera_proof)` returning
`HomeCityViewEvidence`. Retain `localize(image) -> HomeCityCameraProof` and existing
body matcher signatures. `build_home_city_spatial_surface` invokes localize once,
then analyze_view with that result, then publishes matched bodies as today.
`bind_spatial_surface` binds the added evidence using the existing conflict-rejecting
pattern. Both `ObservationBuilder` and `NavigationPerception` consume this single
producer; neither computes a separate endpoint, anchor or camera transform.

### 4.2 Recognition requirements

Use only qualified **fixed** landmark votes to establish camera pose for V44.
Movable ordinary occupants cannot make an otherwise insufficient fixed consensus
pass. Keep independent group and spatial separation checks; repeated art from one
structure is not several independent anchors. Existing confidence/residual rules
remain unless native holdouts justify an explicit reviewed change.

An endpoint calibration contains: stable ID; supported layout/reference size and
appearance; native source and independent holdout identities; permitted relative
scale interval; fixed landmark groups; fit residual acceptance; and qualified
anchor templates/regions. Store this in the existing Home camera catalog/data
owner, with typed validation. Use existing matcher scores and residuals; no second
camera service or configurable rule engine. If adding structured authored data,
use `vision/data/home_city_camera/normalization.json` and explicitly package it.

Numerical recognition limits are **qualification output**, not invented constants.
V44-2 must report measured endpoint spread, non-endpoint separation and holdout
results before enabling `AT_ENDPOINT`. Overlapping classes yield UNRESOLVED.
The sampled ~0.739–0.743 fits are evidence inputs, not an automatically approved
tolerance. Image resizing only proves transform math. A still image after a wheel
is not evidence of the endpoint without the calibrated scene-scale verdict.

Anchor recognition must work **before normalization**. Match positively qualified
noninteractive scenery in the current view at supported scales and ensure its
point lies inside its native bounds, the viewport and outside HUD/occlusion.
The calibration may nominate fixed scenery known from asset/collider evidence and
reviewed native input; a projected polygon alone cannot prove visible ground.
Neither low image variance, label exclusion, nor an assumed building-free patch
is enough. No suitable anchor yields None; do not substitute a corner or center.
An anchor may be available when pose/endpoint is unresolved, and vice versa.

Current body evidence continues through `HomeCityCameraTargetMatch` and
`DetectedSpatialObject`: canonical semantic ID, native bounds/action bounds and
point, optional typed slot, matching/projection agreement, and frame/context.
Projection narrows a search; native body evidence identifies the target. Conflicting,
occluded, missing and uncalibrated bodies remain unresolved. Negative recognition
does not establish an empty slot or unavailable building.

## 5. V44-3: orchestration contract

### 5.1 Public APIs and operation lifetime

Keep the existing signatures and return types:

```python
open_building(target, *, observe_content, on_target_acquired=None,
              home_city_slot=None) -> Observation
open_visible_building(target, *, observe_content, on_target_acquired=None,
                      require_measured=False, home_city_slot=None) -> Observation
discover_home_city(*, observe_content) -> HomeCityScanResult
```

All three enter one internal normalization gate. `open_visible_building` also
normalizes, but does not acquire a new permission to pan/search offscreen; if the
target is not visible after normalization it fails. `open_building` owns directed
acquisition plus bounded fallback. Discovery never taps a building. Preserve the
existing slot validation and reviewed route lookup before input. Normalization
requires measured camera evidence even when legacy `require_measured=False` is
passed; that flag cannot disable the new gate.

Keep `HomeCityScanError(RuntimeError)` and its `.result`. Extend existing
`HomeCityScanStopReason` with `ZOOM_UNRESOLVED`, `ZOOM_ANCHOR_UNRESOLVED`,
`ZOOM_INEFFECTIVE`, `ZOOM_BUDGET_EXHAUSTED`, `ZOOM_CHANGED`,
`NO_SAFE_GESTURE`, `INPUT_UNCERTAIN`, `UNEXPECTED_DESTINATION`,
`DEADLINE_EXHAUSTED`. Retain existing localization, route, progress and pan-budget
reasons. Add defaulted `zoom_inputs: int = 0` to the result/state; `gestures` keeps
its existing pan count meaning. Acquisition raises with the measured result;
discovery returns the result for ordinary evidence/budget stops. Lease, capability,
provenance and transport exceptions remain hard errors with their original cause
and trace; do not turn them into a successful discovery return.

### 5.2 Required transition order

| State | Evidence/action | Next state or stop |
|---|---|---|
| ENTRY | Validate request, route and slot; observe current clear Home through canonical runtime | NORMALIZE; guard/identity/unknown-surface failure stops |
| NORMALIZE | If current endpoint and pose are qualified, obtain one fresh passive confirmation; otherwise require current anchor and send one outward WheelAction | Observe fresh scene, then classify; never use the send result as zoom proof |
| CLASSIFY_ZOOM | Measured movement toward endpoint permits another bounded normalization iteration; two consecutive qualified endpoint frames complete the gate | LOCALIZE; unresolved evidence gets only bounded passive observations; proven unchanged non-endpoint stops ineffective |
| LOCALIZE | Require current fixed-landmark proof and endpoint agreement | RESOLVE; insufficient pose stops after passive allowance |
| RESOLVE | Current requested body; otherwise observed-slot hint; single eligible candidate; nearest uninspected eligible candidate; bounded fallback | TAP if current body safe; PAN if qualified route; explicit unresolved/no-route stop otherwise |
| PAN | Plan deliberate qualified stroke from current projection and lane; exact geometry; consume shared pan budget | OBSERVE; no safe long enough stroke means stop or a different qualified corridor route within the same budget |
| OBSERVE | Fresh content frame; endpoint/pose/body are remeasured, scan facts updated | RESOLVE; bounded passive pose reacquisition; unexpected zoom or lost continuity stops |
| TAP | Reacquire requested semantic ID and pinned slot on fresh frame; valid body/action point; one exact spatial tap | CONFIRM; stale/ambiguous/unsafe body stops |
| CONFIRM | Existing bounded destination observer matches the feature-owned reviewed screen | Return Observation; unexpected destination stops without a second building tap |

Use `TapSpatialObjectAction(exact_geometry=True)` with the current `expected_object` and current point
so stale object/point identity is checked. Invoke `on_target_acquired` only after
the final body is selected; it is notification, not arrival acceptance. If that
callback or any intervening action consumes the frame, obtain new proof before tap.
Do not call the public acquisition entry recursively for internal retries.

### 5.3 Finite limits and progress

- Add `max_home_zoom_inputs=12` and `max_home_pose_observations=3` to the existing
  `NavigationPolicy`, with positive-value validation. Twelve is a conservative
  attempt cap, **not** proof that every starting zoom converges in twelve detents.
- Apply `NavigationPolicy.max_home_seconds=90` as one Home operation deadline,
  starting before the first normalization capture and continuing through scan,
  final body tap and destination confirmation. Validate it within `(0, 120]`
  seconds. Do not restart it at normalization, a pan, fallback or final tap.
  Ordinary screen routing retains `max_seconds=45`; callers that intentionally
  constrain a Home operation set `max_home_seconds` explicitly. Existing outer
  executor deadlines/input caps remain additional stricter limits.
  This September 28 turn013 amendment replaces the original shared 45s limit:
  six qualified outward detents and eight fresh observations took 50.152s before
  any Institute pan/tap. Saved-frame profiling found path/decode caching saved
  at most 0.11s per observation, so it cannot resolve that mismatch. The 90s total
  accommodates this observed normalization plus the measured acquisition work;
  it does not grant more inputs, relax freshness or guarantee every starting
  pose succeeds. N5 must prove normalization consumes the same deadline used
  later, and NL1 must validate the final candidate from a closer starting view.
- Preserve `home_city_scan_step_budget()` as the single pan allowance shared by
  directed acquisition, corridor moves, fallback and correction. Passive pose
  allowance is at most three fresh observations per input, including its first
  post-input capture, within the same deadline.
- Count each attempted wheel/pan before dispatch. An uncertain send consumes the
  allowance and ends dependent input. An observation-only endpoint no-op uses zero
  wheel allowance. Never reset action totals by launching another phase/process.
- Same-operation pan retains normalization only when the new fixed-landmark scale
  agrees. Unexpected scale stops with `ZOOM_CHANGED`; it does not trigger an
  unbounded normalize/search restart. A later user operation starts afresh.
- Require measurable new coverage, newly inspected candidates, or bounded progress
  toward the chosen uninspected candidate. A corridor revisit can be useful, but
  repeating a pose/candidate/direction cycle with no new facts is not progress.
- Permit at most one genuinely different qualified route after a measured stalled
  pan, within the existing allowance. Never replay an unchanged stalled gesture.

Use reviewed deliberate strokes; do not infer shortest valid duration or minimum
length from the sample. A pan profile records its actual qualified native length,
duration and lane conditions. Small desired correction may use a qualified route
that moves the target into a wider useful view; it cannot silently shrink below
the profile or assume that dragging over every building is safe. Keep gain estimates
as bounded proposals and use the next landmark pose as truth, including clamping.
Do not fit a universal horizontal/vertical gain from G1/G2 or add cumulative odometry.

## 6. Shared-file ownership and trace schema

| Owner | Exact additions/changes permitted in shared areas |
|---|---|
| V44-1 | `action_requests.py`: WheelAction, Home swipe purpose/fields, spatial-tap exact flag; `action_executor.py`: wheel/exact swipe/tap dispatch and recorder; `read_only_policy.py`: explicit wheel permission; emulator session and new input/transport modules/data; `pyproject.toml`: server asset/notice packaging |
| V44-1 | `core_runtime.py`: recorder wiring/lifetime and typed input trace serialization; event-specific sanitizer support described below; corresponding generic doubles/tests |
| V44-2 | `domain/home_city_camera.py`: view/anchor/status; `domain/observation.py`: only `home_city_view`; `vision/home_city_camera.py`: canonical recognition/catalog; `spatial_surfaces.py`: Home producer; `observation_provenance.py`: new proof binding; Home wiring in both publishers/enricher; its fixtures/data packaging |
| V44-3 | `navigation_core.py`: Home gate/state machine and NavigationPolicy additions; `spatial_navigation.py`: Home pan planning; `home_city_scan.py`: Home state/result/reasons; related tests |
| V44-4 | Assigned target entries, body fixtures and acquisition caller symbols after V44-3 integration; route-only tests and coverage records; no shared algorithm changes |

V44-1 and V44-2 both may need separate package-data keys in `pyproject.toml`.
They declare the exact key/hunk; lead integrates those tiny additive hunks in order.
No shared-test-double edits by V44-2 in a V44-1-owned file: use local perception
fixtures. Missing symbols/interfaces go back to lead; no parallel shadow types.
V44-3 starts after both integrations; V44-4 takes data ownership only after V44-2
handback. Other feature-owned methods in these files remain outside each slice.

Current `_sanitize_trace_entry` drops non-allowlisted details and stringifies most
values. V44-1 adds **event-specific typed serialization**, not an unrestricted
dictionary pass-through. Preserve existing sanitization for all other events.

| Event | Fields retained in addition to event name |
|---|---|
| `home_city_input_dispatched` | source frame identity/epoch/capture/input sequences; actual wheel, swipe or tap record; source artifact basename |
| `home_city_navigation_step` | operation ID, typed stage, target ID/slot, artifact basename, zoom status/calibration ID, measured zoom/translation/group IDs, wheel/pan counts, elapsed seconds |
| `home_city_scan_stopped` | operation ID, stop reason, counts, inspected/remaining slot IDs and fixed target IDs |
| `home_city_input_failed` | operation ID when present, source frame identity, input kind, failure phase and exception type; no raw command/config text |

V44-1 supplies the serializer and input events. V44-3 supplies step/stop event
producers. Use existing `CoreRuntime.record`; retain numbers/lists as JSON values,
whitelist fields and omit account secrets, identity-bearing roster contents,
reservation receipts and arbitrary exception strings. Existing before/after frame
artifacts remain the evidence; this adds no separate telemetry service or database.
Emit Home event names for Home input; retain ordinary logging for unrelated input.

## 7. Producer/consumer examples and acceptance boundaries

**Already wide:** current Home frame F1 has qualified fixed pose and AT_ENDPOINT;
fresh F2 agrees. No wheel is sent. A current visible body in F2 can be selected.
Neither the F1 body point nor a stored point from yesterday is tapped.

**Closer view:** F1 has NOT_AT_ENDPOINT and a qualified anchor. V44-3 emits one
WheelAction(+1); V44-1 records actual point and input sequence. F2 is localized at
a changed scale. Continue within allowance until two endpoint frames agree. All
pre-wheel body points are discarded. If F2 is unchanged and positively not at the
endpoint, stop ineffective; identical images do not mean fully zoomed out.

**Campaign body visible but click unsafe:** semantic visibility alone does not
authorize tapping a HUD-covered/body-edge point. Plan a qualified deliberate pan
or alternate corridor, remeasure, then reacquire the current body and exact point.
A tiny desired correction does not authorize an unqualified tiny drag.

**Configurable slots 11–13:** geometry gives candidates, not occupants. Observe
bodies; preserve the requested slot, if supplied. An inspected candidate with no
match remains unknown, never empty by inference. Discovery records this honestly.

**First post-pan frame ambiguous:** take bounded passive fresh observations; the
second may localize as in reviewed G3b. If none do, stop. Do not add another swipe
to recover pose without knowing the current camera position.

**Wheel opens an unrelated page:** stop feature input, retain the source/dispatch/
post-frame evidence and classify the boundary. A known unrelated popup may follow
the canonical authorized recovery/weekly reporting workflow; do not misclassify
a task-owned menu as a dismissible popup or resume using the consumed proof.

## 8. Qualification gaps and change control

These remain empirical work with named owners, not discretionary design choices:

| Gap | Owner and required output | What stays blocked |
|---|---|---|
| Endpoint thresholds / supported view profiles | V44-2 measured native calibration and independent holdouts | AT_ENDPOINT outside qualified conditions |
| Safe pre-normalization anchor across required starts | V44-2 recognition evidence; V44-1/2 live production input proof | Wheel input in a view without a current qualified anchor |
| Reliable deliberate lanes and settling | V44-3 reviewed profile plus final-candidate live cases | Motions outside qualified conditions; universal drag-on-building claim |
| All remaining ordinary route bodies/destinations | V44-4 inventory and per-type evidence, with feature owners | Whole-V44 coverage and those route acceptances |

No worker may fill a gap by lowering a threshold until a test passes, claiming an
unseen target unavailable, using privileged game memory as runtime camera truth,
or promoting historical helper evidence into production-candidate acceptance.

To amend this agreement, hand the lead one concrete incompatibility, affected
producer/consumer symbols, proposed minimal change and affected checks. The lead
updates this one source, identifies dependent bases and communicates the revision
before conflicting work continues. A local private helper name need not trigger
contract review; a signature, unit, authority, result meaning or ownership change does.

Each slice returns exact base/candidate SHA, changed owned symbols, case IDs and
results, evidence paths, limitations and remaining owner/trigger. Lead reviews the
diff, resolves findings, then assigns compatible live cases. Conflicts/substantive
integration changes require affected review/retest. `accepted` and `merged/pushed`
are separate states. A worker completion message does not satisfy either state.
