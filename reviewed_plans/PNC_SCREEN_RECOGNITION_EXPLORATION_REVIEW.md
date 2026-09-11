# PNC screen recognition exploration review — 2026-09-10

## Findings

### High — The document selects an architecture before its own decision evidence exists (`ARCH-01`)

**Plan locations:** recommendation lines 5–7, visual experiment lines 35–49, alternatives lines 66–76, acceptance checks lines 103–108.

The recommendation calls OpenCV visual anchors plus guarded geometry the best-supported first choice, but the experiment covers only three header families. Its historical labels come from the current observation pipeline rather than an independent ground-truth review, adjacent operational frames are correlated, Event Center has no independent positive, and unknown frames are excluded from the negative set. The experiment does not test overlays, active tabs, disabled controls, different aspect ratios, localization, game-version changes, or a trained classifier/detector on the same split. The plan acknowledges most of these limitations and then places the missing comparative work in its acceptance checks.

This proves that visual anchors deserve a controlled prototype. It does not yet prove that they should own global screen recognition. Treat the first implementation slice as a benchmark/decision gate. Select anchor matching, a small classifier, or a hybrid only after the same manually reviewed dataset and safety-weighted metrics are applied to each viable candidate. False actionable classifications must be a separate, stricter metric from unknown/miss rates.

### High — This is an investigation report, not an executable implementation plan (`PLAN-01`)

**Plan locations:** proposed ownership lines 53–64 and acceptance checks lines 101–108.

The document provides sound boundaries, but it does not name implementation phases, exact files/interfaces, selector-catalog schema changes, model/asset lifecycle, migration of existing OCR screen builders, fallback ordering, ambiguity policy, thresholds, rollback, or exact offline and live checks for each slice. “Use multiple distinctive visual anchors” does not specify how an anchor is represented, combined, versioned, or converted into `ScreenEvidence`. “Recognize overlays independently” does not define whether an observation carries a base screen plus overlays or preserves the current single `ScreenType` contract.

Implementation would require engineers to make architecture-changing decisions that should be decided in the plan. Add deliverable-oriented slices with dependencies, acceptance criteria, exact tests, and exact bounded live entry points. Until then, only the return-home regression test and a non-production benchmark harness are ready to start.

### Medium — The proposed return-home repair has no defined source-screen contract (`SCOPE-02`)

**Plan location:** line 29 and acceptance check line 103.

The causal reproduction is valid: `ConnectedDailyQuestSession.return_to_home()` requests `daily_quest_follow_up()`, which only enables Main/Daily Quest recognition; the saved Hero Hall frame becomes `unknown` under that request and `pnc_hero_hall` under a full request. However, “give return-home its correct source-screen scope” does not state what that scope is or who owns it.

`DailyMaintenanceCoordinator.return_to_home()` is called both after a read-only Daily survey and after capability execution. Capability work can leave Hero Hall, Bag/resource, or other feature screens, while popup/update recovery remains global. Define one navigation-oriented observation request owned by the return-to-safe-root flow, or derive a precise request from a typed capability post-state. Add deterministic tests proving Daily Quest, Hero Hall, Bag/resource, blocking popup, and required-update handling. Do not solve the defect with an unconstrained duplicate list in `ConnectedDailyQuestSession`.

### Medium — The More overlay versus Settings contract is left unresolved even though geometry depends on it (`LAYOUT-01`)

**Plan locations:** global/layout proposal lines 57–59 and live observation line 97.

The repository currently classifies both the bottom-right More overlay and the full-screen Settings page as `PNC_MORE_MENU`. The OCR enricher has separate builders for these layouts, but both emit the same screen evidence. The selector registry binds controls from both layouts to that one screen type, with different materialization behavior. The plan says a visual model could use a layout variant or migrate the screen contract, but does not choose one.

This decision must precede guarded geometry. Otherwise, classification can be correct at the enum level while controls from the wrong layout are eligible for materialization or planning. Define an explicit layout/substate field or separate screen types, migrate the registry and flows to it, and test that each layout exposes only its own controls.

### Medium — Two of the six claimed live transitions lack a durable same-trace action record (`LIVE-TRACE-01`)

**Plan locations:** live table lines 86–95 and trace claim line 99.

The screenshots visibly support all listed states, and the surviving JSON files prove these transitions: popup → Home, Home → More, Settings → Manage Char, and Settings → Home. `live_trace.jsonl`, however, contains only the last two `home` runs. The reusable `live_roster.json` was overwritten by the later Settings → Manage Char run, so the earlier More → Settings record is absent. The Manage Char → Settings result is also absent from the JSONL trace. Screenshot names alone do not prove the named preceding action.

Correct the plan to distinguish `live_observed` transitions from `artifact_state_only`, or reconstruct a durable manifest from the executor’s immediate `post_action_1` artifacts and logs if those records exist. Future probes should use unique run IDs, append before acting, record the exact typed pre/post observation, and avoid overwriting per-step JSON.

### Low — The evidence script’s contract contradicts its live behavior (`EVIDENCE-TOOL-01`)

**Evidence:** `artifacts/recognition_exploration/explore.py`.

The module docstring says it “never click[s] controls,” but `--live --step` executes selector-backed actions. The actions used were safe and bounded, yet the stated contract is false. Rename it as a bounded read-only navigation probe, reject incompatible flags explicitly, use unique artifact labels, and preserve action-executor results. Keep this tool under artifacts or promote a tested version under `tools/`; do not make an untested artifact script a production validation dependency.

## Assumption and evidence matrix

| ID | Plan location | Requirement or assumption | Provenance | Consequence if false | Verification method | Target | Status | Evidence | Required correction or next proof |
|---|---|---|---|---|---|---|---|---|---|
| `ARCH-01` | 5–7, 37–49, 70 | Visual anchors plus guarded geometry are the best first architecture | inference + artifact observation | Wrong canonical recognizer and avoidable migration | Independent labelled benchmark against candidates | Archived and current PNC screens | `unproven` | `results.json` covers three headers with correlated pipeline labels | Make architecture selection a benchmark gate |
| `PLAN-01` | 53–64, 101–108 | Proposed ownership is specific enough to implement | inference | Implementers invent incompatible contracts | Trace proposed changes to files, APIs, phases, tests, live gates | Repository | `unproven` | Ownership names exist, implementation contracts do not | Add executable phases and exact contracts |
| `INV-01` | 12 | Registry has 211 selectors with 70 template, 6 collection, 9 OCR-region, 126 planned and zero resolved template files | repository contract | Misstates current visual baseline | Load default registry and inspect resolved paths | Repository | `repository_answered` | Repeated registry inventory matched all counts | None |
| `MATCH-01` | 13 | Current Pillow matcher is exhaustive mean-difference matching without normalized/masked region constraints | repository contract | Incorrect comparison baseline | Inspect implementation | Repository | `repository_answered` | `core/vision/template/template_matcher.py` | None |
| `SCOPE-01` | 20–29 | Quest-only observation scope causes a visible Hero Hall return frame to classify unknown | repository contract + artifact observation | Misdiagnoses OCR as scope failure | Replay same frame under both requests | Saved Hero Hall frame | `artifact_answered` | `scope_replay.json`; request definition and live-session caller | None |
| `SCOPE-02` | 29, 103 | Correct repair is to give return-home the right source scope | inference | Recovery stays incomplete or becomes unnecessarily broad | Define source-state contract and regression matrix | Daily maintenance navigation | `unproven` | Multiple possible capability exit screens; no return-home tests | Specify canonical navigation request and cases |
| `ANCHOR-01` | 37–47 | Stable header anchors are feasible for sampled Hero Hall/Quest screens | artifact observation | Prototype may not generalize | Manually reviewed independent split | 657 sidecar-associated frames | `artifact_answered` at exploratory scope | Hero Hall and Quest score separation; stated caveats | Do not generalize beyond sampled families |
| `OVERLAY-01` | 58, 64 | Blocking overlays must be recognized independently of underlying Home controls | stakeholder confirmed + live observation | Automation may click through a modal | Typed popup baseline and safe dismissal post-state | Testing / active K287 castle | `live_observed` | Invitation screenshot and popup → Home JSON | Define data model and precedence tests |
| `GEOM-01` | 59 | Geometry should follow screen/layout/control-state proof | repository contract + target design | Wrong-layout controls become actionable | Inspect materialization order; test layout isolation | Observation builder/registry | `repository_answered` for screen-first order; `unproven` for layout/state guards | Geometry materializes after screen classification, but More/Settings share a screen type | Resolve `LAYOUT-01`, then test state guards |
| `LAYOUT-01` | 97 | More overlay and Settings need a layout variant or screen migration | repository contract + live observation | Screen-scoped geometry remains ambiguous | Inspect enrichers/registry and live states | Testing / PNC_MORE_MENU family | `live_observed` problem; `unproven` solution | Separate OCR builders emit the same enum | Choose and specify one contract |
| `YOLO-01` | 61, 72, 108 | A small detector may fit moving objects | external authority + inference | Annotation/training cost may not improve reliability | Same-dataset detector benchmark | World-map/spatial objects | `unproven` | No PNC detector trained or evaluated | Define object set and benchmark gate before adoption |
| `UIA-01` | 76, 99 | UI Automator does not expose useful Settings controls | live observation | A semantic control source may be overlooked | Dump current hierarchy | Testing / Settings | `live_observed` at this screen | Six nodes, zero text nodes, one description node | Keep claim scoped to observed screen/build |
| `LIVE-TRACE-01` | 86–99 | All six transitions have durable same-trace evidence | artifact observation | Review cannot attribute actions to states | Audit manifests, executor artifacts, logs | Testing / active K287 castle | `contradicted` | JSON proves four transitions; JSONL contains only last two runs | Correct claim or recover durable records |
| `PROMOTE-01` | 103–108 | Acceptance checks are sufficient for unattended promotion | inference | Unsafe false positives or incomplete target coverage | Require thresholds, target matrix, recovery and rollback | Each supported instance/layout | `unproven` | Checks name metrics but no values or target cells | Add quantitative gates and per-target outcomes |

## Bounded live evidence disposition

No new live action was necessary for this review. The existing same-day artifacts answer the material state/layout questions, and repeating navigation would only accumulate screenshots. The user’s statement that the invitation appears when the active castle is not in an alliance is retained as `stakeholder_confirmed`; the review does not generalize absence of the invitation into proof of alliance membership.

| Evidence question | Disposition | Evidence |
|---|---|---|
| Can a blocking invitation coexist with visible Home controls? | `live_observed` | `20260910T184112Z_recognition_exploration_retry.png` |
| Does the configured testing target safely dismiss it to Home? | `live_observed` | `live_dismiss.json` and `20260910T184256Z_recognition_exploration_dismiss.png` |
| Are More overlay and Settings distinct layouts under one current enum? | `live_observed` | `20260910T184348Z_recognition_exploration_more.png`, `20260910T184423Z_recognition_exploration_roster.png`, and enricher code |
| Does UI Automator expose Settings labels as semantic nodes? | `live_observed` | `live_home.json`: six nodes, zero text nodes |
| Do all six named transitions have attributable trace records? | `artifact_answered` as no | `live_trace.jsonl` and overwritten per-step JSON files |

The recorded target was the configured `testing` BlueStacks display and the selected K287 level-10 castle. PNC was foregrounded through the canonical session. No castle switch, alliance join, claim, recruitment, purchase, or resource-spending action was performed. The final recorded state was Home at `artifacts/2026-09-10/testing/20260910T184700Z_recognition_exploration_home.png`.

## Target-by-slice validation status

| Slice | Target | Status | Basis |
|---|---|---|---|
| Return-home defect reproduction | Saved Hero Hall frame | `passed` | Same frame returns unknown under Quest-only scope and Hero Hall under full scope |
| Visual-anchor feasibility | Historical Hero Hall and Quest samples | `passed` for exploratory feasibility only | Clear sampled score separation; not an accuracy/promotion result |
| Visual-anchor architecture selection | Supported PNC screen/layout matrix | `blocked` | No independent dataset, candidate comparison, thresholds, or overlay/tab coverage |
| Popup precedence | Testing / active K287 | `passed` | Popup typed before safe dismissal; Home observed afterward |
| More/Settings layout representation | Testing / active K287 | `blocked` | Problem observed; target screen/substate contract undecided |
| Android hierarchy fallback | Testing / Settings | `applicability_skip` | Observed hierarchy lacks useful visible control semantics on this screen |
| Unattended runtime promotion | All configured targets | `blocked` | No implementation, full offline validation, per-target matrix, or end-to-end canary |

## Verdicts

- **`implementation_ready`: false for the proposed recognition architecture.** The return-home regression test and a benchmark harness are ready as discovery slices. Production recognizer work is blocked by `ARCH-01`, `PLAN-01`, `SCOPE-02`, and `LAYOUT-01`.
- **`promotion_ready`: false.** Material claims remain unproven or contradicted, no production implementation exists, and there is no complete offline/live target matrix.

## Required revision order

1. Specify and test the canonical return-to-safe-root observation request without duplicating screen lists.
2. Decide the base-screen/overlay/layout data model, including the More overlay versus Settings distinction and popup precedence.
3. Define the anchor/model asset schema, evidence-combination rules, ambiguity rejection, fallback order, and lifecycle ownership.
4. Build an independently reviewed dataset and benchmark anchors, a small classifier, and any justified detector on identical splits and safety-weighted metrics.
5. Select the implementation from that benchmark, then add file-level phases, deterministic tests, exact bounded live commands, per-target outcomes, and rollback criteria.

## Commands and checks

- `py -m unittest tests.test_daily_live_session tests.test_screen_classifier tests.test_capture_and_vision tests.test_ocr_service` — **passed**: 157 tests, one skip.
- Default selector-registry inventory script — **passed**: 211 selectors; kind counts and zero existing resolved template files match the plan.
- Read-only inspection of the plan, implementation, selector catalog, exploration script/results, OCR sidecars, screenshots, and live JSON manifests — **passed**.
- New BlueStacks action — **skipped** because adequate same-day bounded evidence already answers the review’s material live questions.
- Full offline suite — **skipped** because this review does not modify production behavior.
