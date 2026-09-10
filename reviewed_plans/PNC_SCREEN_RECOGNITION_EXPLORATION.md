# PNC screen recognition investigation — 2026-09-10

## Recommendation

Use a **screen-first visual pipeline**: recognize the screen family and blocking overlays, establish the active tab/layout, then resolve fixed controls through guarded normalized geometry. Use cropped OCR for variable content. Evaluate a small custom object detector for objects that genuinely move or vary in appearance, rather than training one detector to recognize every screen, number, and button.

This is the best-supported architecture from this investigation, not a claim that a trained model has won a PNC benchmark. No YOLO model was trained or evaluated. The immediate priority is to fix observation scope and establish a real visual-anchor baseline; replacing OCR wholesale would leave a demonstrated failure intact.

## Evidence collected

- Inspected the canonical observation builder, selector engine/catalog, screen classifier, OCR service, enrichment, navigation, daily return-home caller, and live runtime wiring.
- Inventory: 211 selectors — 70 template, 6 collection, 9 OCR-region, 126 planned. **Zero expected template files exist** in the default registry's resolved template paths. Planned selectors can still have geometry or receive derived evidence; this is not a count of unusable controls.
- The current Pillow matcher searches every pixel using mean channel difference. It is not a modern normalized, masked, region-constrained matcher. Its current implementation does not establish a fair template-versus-detector comparison.
- The enrichment module has 7,022 lines and owns many text-based screen predicates. Size alone is not a defect, but screen identity and content extraction are tightly connected here.
- Inventoried 2,577 archived PNG files before the new captures. Sampled the 657 screenshots with unidentified-OCR sidecars from September 10: 382 at 900×1600, 275 at 540×960. These are correlated operational artifacts, not an independently labelled dataset.
- Visually inspected Event Center, Hero Hall, Daily Quest, and the live invitation, Home, More, Settings, and Manage Char screens.

## A reproduced failure that changing the OCR engine will not fix

`ConnectedDailyQuestSession.return_home` in `pnc_automation/app/automation/daily_maintenance/live_session.py:85` requests `ObservationRequest.daily_quest_follow_up()`. That request only permits Main Quest and Daily Quest OCR families.

On `artifacts/2026-09-10/mega_old_acc/20260910T151754Z_daily_return_home_start.png`, the visible screen is Hero Hall and the archived OCR correctly reads “Hero Hall”, “Recruit”, and “Exchange”. Replaying the exact same image through the current canonical builder gives:

| Request | Result |
|---|---|
| `daily_quest_follow_up()` | `unknown` |
| Default full observation | `pnc_hero_hall` |

The screen is excluded by the request, rather than being unreadable. Preserve scoped content extraction for efficiency, but do not let its scope erase global screen/overlay identity. The smallest repair is to give return-home its correct source-screen scope; the architectural repair is to separate cheap global state recognition from optional task-specific extraction.

The historical Event Center unknown frame `20260910T133151Z_canary_identity_unknown_retry_1.png` also classifies as Event Center in a current full replay. Its historical unknown result is therefore not evidence of a remaining OCR defect. The original request and revision would be needed to distinguish historical code changes from scope differences there.

Reproduction result: `artifacts/recognition_exploration/scope_replay.json`.

## Small visual-anchor experiment

`artifacts/recognition_exploration/explore.py` normalizes the two same-aspect-ratio resolutions to 540×960, extracts one header patch for each of three screen families, and uses OpenCV normalized correlation in the top screen region. Source frames are excluded from positive summaries.

| Header patch | Other historically matching frames | Lowest matching score | Highest score on historically different known screens |
|---|---:|---:|---:|
| Hero Hall | 24 | 0.965 | 0.638 across 617 frames |
| Quest | 56 | 0.999 | 0.637 across 585 frames |
| Event Center | 0 | Not available | 0.550 across 641 frames |

The visually inspected historical unknown Event Center and Hero Hall examples both match their respective patches at approximately 1.0. This supports the feasibility of stable visual anchors.

**Limits:** Scores are similarity measures, not correctness probabilities. Historical labels may be wrong; adjacent captures are correlated. Event Center has no independent positive in the historical known-label subset. The Quest header recognizes the Quest family, **not the Daily tab**; tab selection needs separate evidence. Negative examples do not cover every modal, localization, skin, aspect ratio, loading frame, or game version. No threshold has been validated for unattended use.

Median time for loading, resizing, and matching all three header patches was about 64 ms in this run. Five full canonical observation replays took about 2.8–9.7 seconds each. These workloads differ: the header experiment does not extract content or guard every overlay, and execution was not isolated. Do not present this as an end-to-end speedup benchmark.

Full rows and replay timings: `artifacts/recognition_exploration/results.json`.

## Proposed ownership

Keep `ObservationBuilder` as the single observation entry point, `ScreenClassifier` as the state decision owner, the selector registry as the control catalog, and the existing observed executor/navigation flows as action owners.

1. **Frame and layout:** determine the usable game viewport and supported aspect/layout variant. Same-aspect scaling worked in this sample; arbitrary stretching is not a general solution.
2. **Global state:** use multiple distinctive visual anchors for stable screens, with explicit unknown/ambiguous rejection. Recognize overlays independently of the underlying screen. A small trained classifier is an option if anchor variants become difficult to maintain, but is not justified by current comparative measurements.
3. **Screen-scoped controls:** materialize fixed targets only after screen, active tab, overlay, and required control-state checks. Geometry expresses an expected position; it must not be mistaken for independent proof of presence or clickability.
4. **Variable content:** crop and read quantities, timers, names, coordinates, levels, and dynamically arranged row labels only when requested. Associate repeated Claim/Go buttons with the correct row. A box labelled “Claim” does not identify which quest it belongs to.
5. **Moving objects:** evaluate a small custom YOLO detector for world-map objects and varied spatial targets. Predict object type and location; read variable levels separately where necessary. Feed detections through existing typed spatial/visible-element models.
6. **Action verification:** retain fresh observations, bounded settling, and explicit expected postconditions. Recognition confidence alone never proves an action succeeded.

The alliance invitation illustrates why the overlay guard must be independent: the Home controls remain visible behind the dialog. Recognizing Home must not authorize clicking through it. Store invitation presence separately from task applicability; absence of this popup alone does not prove alliance membership.

## Alternatives assessed

| Approach | Fit and decision |
|---|---|
| OpenCV visual anchors + guarded geometry | Best-supported first choice for fixed menus. Region constraints, masks, and normalization avoid unnecessary full-image search. Requires representative negatives and variant management. |
| Small trained screen classifier | Sensible later comparison when anchor complexity grows. Use screen/layout labels, separate overlay evidence, and unknown rejection. Whole-frame training can learn incidental artwork or account-specific shortcuts. |
| Custom YOLO26n detector | Credible candidate for variable-position objects and controls. Requires domain annotations and validation; pretrained COCO classes do not provide PNC semantics. Not yet proven preferable for this repository's fixed menus. |
| OCR engine replacement | Can improve variable text, but does not fix the reproduced request-scope failure. Benchmark troublesome crops before changing engines. |
| OmniParser | Its reference pipeline combines icon detection/captioning and OCR. It is not a ready-made PNC semantic model or an OCR-free replacement. No local comparative benchmark was performed. |
| General vision-language agent | Potential authoring/diagnostic aid; not established as the best frequent unattended runtime recognizer here. No cost/latency/reliability comparison was performed. |
| Android UI hierarchy | Probed separately below. Prefer semantic controls where actually exposed; do not assume a game exposes its rendered buttons. |

Primary sources consulted: [OpenCV template matching](https://docs.opencv.org/4.13.0/de/da9/tutorial_template_matching.html), [YOLO26 models](https://docs.ultralytics.com/models/yolo26), [classification versus detection](https://docs.ultralytics.com/tasks/classify), [dataset collection guidance](https://docs.ultralytics.com/guides/data-collection-and-annotation), [OmniParser reference implementation](https://github.com/microsoft/OmniParser/blob/master/gradio_demo.py), and [Android UI Automator](https://developer.android.com/training/testing/other-components/ui-automator).

## Live observations

Target: configured `testing` display, existing active castle in K287, level 10, verified from the selected roster row and canonical current-castle observation. No castle switch, claim, recruitment, alliance join, or resource expenditure was performed.

The first canonical connection succeeded but screenshot capture timed out after 20 seconds. A retry captured the BlueStacks Store with PNC not foregrounded. The subsequent run invoked `ensure_app_foregrounded()` and observed PNC. Whether the first resolver launched the emulator or found it already running was not recorded, so no claim is made about that distinction.

| Observed trace | Screenshot under `artifacts/2026-09-10/testing/` |
|---|---|
| Store baseline, classified unknown | `20260910T183916Z_recognition_exploration_retry.png` |
| PNC alliance invitation, classified popup | `20260910T184112Z_recognition_exploration_retry.png` |
| Dismiss invitation → Home | `20260910T184256Z_recognition_exploration_dismiss.png` |
| Home → More overlay | `20260910T184348Z_recognition_exploration_more.png` |
| More → Settings, represented as `pnc_more_menu` | `20260910T184423Z_recognition_exploration_roster.png` |
| Settings → Manage Char, selected castle observed | `20260910T184500Z_recognition_exploration_roster.png` |
| Manage Char → Settings | `20260910T184555Z_recognition_exploration_home.png` |
| Settings → Home, final resting state | `20260910T184700Z_recognition_exploration_home.png` |

This also exposes a layout consideration: the small More overlay and full Settings page share the current screen enum. A future visual model needs to preserve that distinction as a layout variant or migrate the screen contract, rather than silently assuming one geometry per enum.

Six navigation transitions were performed. The final state is Home. The first UI Automator attempt using `/dev/tty` returned no readable XML. A second attempt dumped a dedicated diagnostic file and read it through the canonical ADB client. On Settings it exposed six nodes: four FrameLayouts, one LinearLayout, and one View; zero text-bearing nodes and one content-description node. This does not expose the visible Settings labels/buttons as useful semantic controls. It rules against relying on UI Automator for this observed screen, not against every Android surface. Result: `artifacts/recognition_exploration/live_home.json` and `live_trace.jsonl`.

## Acceptance checks before implementation promotion

- Correct the return-home scope and add a deterministic test using the reproduced frame or a safe committed fixture.
- Build a manually reviewed, deduplicated dataset split by session/account/day; never use adjacent frames from one run as independent train/test evidence.
- Compare visual anchors and any trained classifier on the same known screens, unexpected screens, tab variants, disabled controls, and blocking dialogs. Measure false actionable classifications separately from misses.
- Check click-point containment in manually labelled intended controls, including repeated-row association. Record end-to-end task completion, wrong actions, unknown rates, and latency distributions.
- Prove one read-only route first on the active testing castle, preserving canonical action/postcondition checks. Mutating tasks require their own explicit action/target/budget authorization.
- Train a detector only for a defined object/control set where visual anchors fail the agreed acceptance checks or annotation/maintenance costs favor learning. Do not label every timer value or monster level as its own class.

## Validation and scope

- `py -m unittest tests.test_screen_classifier tests.test_capture_and_vision tests.test_ocr_service`: passed, 156 tests, one skip. The command was run twice during investigation; the retained completion output is from the second run.
- `py artifacts/recognition_exploration/explore.py`: passed; 657-frame exploratory comparison and five full-pipeline replays.
- Exact-frame default-versus-Quest-scoped replay: passed; reproduced `pnc_hero_hall` versus `unknown`.
- `py tools/validate_navigation_selectors.py`: failed argument parsing because `--account` is required; no live action occurred. A broad navigation validation run was not substituted for the bounded exploration.
- Live probes use `py artifacts/recognition_exploration/explore.py --live`, with one `--step dismiss|more|roster|home` per invocation. Initial capture failure was retried; subsequent recorded transitions succeeded.
- No production code or authored/local config was changed. The exploration script/results are local artifacts; this report is the tracked deliverable. Concurrent skill edits observed during the investigation were left untouched.
- `py -m py_compile artifacts/recognition_exploration/explore.py`: passed. `git diff --check`: passed.
- Full offline suite and trained-model evaluation were not run: this task investigates and recommends, without changing production runtime behavior.
