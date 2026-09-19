# Handoff: Infantry Barracks recognition and Join Alliance dismissal

Prepared September 16, 2026 (America/Toronto). Repository baseline: `5f58d4ed0599ae7447a9d995e29631b2b89a1c39` (`origin/main`). Observation timestamps below are UTC. This is a handoff of existing evidence and decisions, not a claim that either outstanding fix has been accepted.

## Outcome and ownership

Two separate perception failures interrupted Devin's vision work:

| Issue | What worked | What failed | Current disposition |
|---|---|---|---|
| V20 Infantry Barracks | A measured Home building tap opened the actual menu | Menu stayed `UNKNOWN` / guard `UNRESOLVED`; Unit Advantage and return could not proceed | Implementation assigned to Devin; pending review and live proof |
| Join Alliance invitation | OCR recognized the invitation and its Cancel label | Cancel lost its measured geometry; the visual rescue was ineligible after Home | User manually dismissed it; correction remains deferred outside V22 |

Neither was evidence of an emulator deadlock or an ACP transport error. The separate ACP diagnosis commits `a21c6c4` and `5f58d4e` improve worker error reporting; they do not fix game recognition.

The lead owns architecture, review, acceptance and integration. All live execution is delegated through `devin-live-test` on configured `3xx_spies`, role `live_testing`, active castle last verified as `K303 / K3033849ba8778 / level 5`. No further `mega_old_acc` access is authorized. Existing saved Mega evidence may be read. These checks require no spending, training, collection, quantity changes, joining/applying to an alliance, or account/castle switches.

## Where the previous popup fix is documented

- [Popup recognition workflow](../../../docs/game-reference/workflows/popup-recognition.md): independent base identity, demand-driven popup matching, session eligibility, and the previous Lucifer live proof. Its source predicates refer to packaged client **5.0.203 / versionCode 233**; that is not a verified build identifier for the failing live captures.
- [Generalized popup recovery plan](../../themed/vision/PNC_GENERALIZED_POPUP_RECOVERY_PLAN.md): measured dismiss ownership, safe Cancel versus Join/Apply, interruption recovery and acceptance requirements.
- [Screen-first implementation record](../../completed/vision/PNC_NON_YOLO_RECOGNITION_IMPLEMENTATION.md): recognition changes and review history.
- [Captured alliance regression](../../../tests/integration/vision/test_alliance_invitation_captured.py): measured Cancel, both publishers, two viewport sizes, missing-Cancel rejection and legacy fixture coverage.

Relevant landed commits:

| Commit | Previous change | Limit relevant to this handoff |
|---|---|---|
| `a118104` | Complete screen-first recognition and resolve review findings; includes portrait invitation profiles and captured tests | A declared or captured screen is not proof of every session transition |
| `3543a29` | Complete demand-driven popup recognition; includes workflow documentation and session gates | Startup-scoped visual eligibility can exclude a later invitation |
| `75153e76` | Recover current Savannah offer variants | This later popup correction concerns Savannah offers, not the failing Join Alliance path |

Verified with `git merge-base --is-ancestor`: all three commits are ancestors of current `origin/main`, the popup-failure worker commit `354f230`, and the Barracks-failure commit `cf171fd`. Updating to those earlier fixes cannot by itself resolve these captured failures.

## Bug A: Join Alliance loses Cancel after Home

**Observed:** September 16 at 20:45:27Z, `3xx_spies`, worker baseline `354f230`. The invitation has a blue Cancel beside gold Join/Apply. The published reason was `weak_unmeasured_ocr_popup_cancel_button`; no qualified dismiss remained. The user subsequently closed it manually. Manual dismissal is not automated-recovery validation.

**Evidence on this machine** (paths relative to repository root; raw files are not committed):

- Image: `artifacts/2026-09-16/3xx_spies/20260916T204527Z_core_20260916T204516Z_27f807b6_0003_core_route_source.png`.
- Recognition record: same image prefix plus `_recognition_gap.json`.
- Trace: `artifacts/2026-09-16/3xx_spies/20260916T204516Z_27f807b6_core_trace.jsonl`.
- Devin diagnosis: `.local-data/worktrees/vision-v22-blacksmith-gear/.local-data/devin-v22/join-alliance-popup-recognition-gap.md`.
- Curated live manifest: `.local-data/worktrees/vision-v22-blacksmith-gear/.local-data/devin-live-test/runs/v22-gear-evidence/turn-001/evidence.json`.

**Lead-verified cause, high confidence:** OCR measured Cancel at `(380,891,112,35)` on a 900×1600 frame; its center is `(436,908)`, or 48.4% of the width. `_find_popup_dismiss_anchor` accepts the text. `_qualify_modal_action_geometry` then scans both footer buttons: its affirmative-neighbor clipping applies only outside the middle 40–60% band. `resource_inventory.detect_button_runs` requires one horizontal segment, finds two, and returns no button. The publisher removes the unmeasured control and keeps the guard unresolved.

Lead offline replay of the existing detector returned no button for x=184..688, y=804..1012. Narrowing only the right edge to 560 measured Cancel at `(326,873,217,73)`. This establishes the neighboring-button failure; **560 is not a proposed hardcoded production coordinate**.

**Secondary constraint:** `PopupRecognitionSessionState.allow` in `visual_screen_recognizer.py` disallows alliance-invitation profiles after `post_login_proven`. Home had already been recognized in this session, so `reconcile_visual_modal_guard` in `observation_builder.py` had no visual invitation evidence to rescue the rejected OCR control. Devin reported successful dismissal in a fresh observation session. The exact 20:45 frame has not been independently replayed against an enabled visual profile; do not claim that counterfactual is proven. The worker memo's name `VisualPopupMatcherState` is stale; the current owner is `PopupRecognitionSessionState`.

**Why the prior regression did not cover this:** the existing test constructs a new builder and starts with the invitation frame. It does not first recognize Home and then present the invitation in the same session/epoch. Its passing result therefore does not prove the failing session transition.

**Next work:** use the already saved [deferred correction plan](../../themed/operations/PNC_ALLIANCE_INVITATION_DISMISSAL_FOLLOWUP_PLAN.md), committed as `2efd3ea`. Select the uniquely measured button segment containing the accepted Cancel anchor, keeping the neighboring affirmative action excluded. Add the real capture as a fixture and test Home → invitation in one session through both publishers, plus absent/ambiguous Cancel. Change session eligibility only if the corrected canonical geometry path still needs visual rescue. Do not lower guards, add blind taps, or broaden all popup matching. Live acceptance is typed Cancel → newer clear Home when the popup naturally appears on the authorized account; if absent, report that proof as pending.

## Bug B: Infantry Barracks opens but cannot classify

**Observed:** September 17 at 00:02:49Z (September 16 locally), baseline `cf171fd`. Fresh Home had typed Castle and Infantry Barracks objects. The canonical executor dispatched one `TapSpatialObjectAction` for the observed Barracks at `(128,1122)`. Pixels then show **Infantry Barracks**, level 1/45, Recruit T1, locked T2–T4, selected quantity 40/40, costs, Train 00:09:06, Train Now 19, Unit Advantage and Back.

**Evidence on this machine:**

- Image: `artifacts/2026-09-17/3xx_spies/20260917T000249Z_live_v20_barracks_barracks_open_step_0_post_action_1.png`.
- Sidecars: same prefix plus `_recognition_gap.json` and `_unidentified_ocr.json`.
- Manifest: `.local-data/worktrees/vision-v01-foundation/.local-data/devin-live-test/runs/home-atlas-route-refresh/turn-003/evidence.json`.
- Action/observation trace: `.local-data/worktrees/vision-v01-foundation/.local-data/devin-live-test/runs/home-atlas-route-refresh/harness_run_log_turn003.json`.

**Lead-verified diagnosis:** the header selector is only `planned` / `semantic`, with no independent visual-profile producer. Screen-scoped OCR refines an already identified surface; it cannot bootstrap this unknown menu. Only the bounded modal OCR region ran, excluding the top header. The frame stayed unknown/unresolved through 19 passive observations over roughly 55 seconds with the same fingerprint.

The generic weak-X detector returned `(41,17,52,65)`: **the top-left Back arrow**, not the info/disband icon suggested in the worker's initial hypothesis. The bounded modal detector returned `None`. These are two manifestations of the missing qualified base identity: the existing recognized-base guard path already suppresses generic weak-close fallback, and `reconcile_visual_modal_guard` handles weak-only X evidence for independently proved ordinary screens. A global popup exception is not the chosen fix.

No Unit Advantage/unlock panel was opened; no qualified Back was available. The instance was preserved on the benign Barracks menu and the lease released. This is not a completed Home-return proof. The menu's `140` display must not be called training capacity: packaged `campmainpanel.lua` distinguishes free-troop counters from the selected amount and batch limit shown as 40/40. Unknown widget semantics remain unknown.

**Assigned work:** [V20 plan](../../themed/vision/modules/V20_BARRACKS_TRAINING.md), one qualified Infantry visual profile with independent static anchors, measured controls, a shared typed content producer, both publishers and frame provenance. No guessed other-family layouts, queue state or uncaptured detail/return edges. Captured regression must reject masked identity and prevent a requested different family from forcing classification. After review, Devin must prove recognition on the live menu, then acquire the read-only detail/close and Home return where qualified.

## Continuation without duplicate writers

At this handoff, these persistent implementation assignments remain with their existing Devin sessions:

- **V20:** `puddle-transport`, resumed turn 006, checkout `.local-data/worktrees/vision-v01-foundation`, branch `codex/vision-v20-barracks`, launch base `5f58d4e`. Brief: `.local-data/worktrees/vision-v01-foundation/.local-data/devin-v20/menu-implementation-brief.md`, followed by `resume-after-app-restart.md` in that directory.
- **V22 Gear:** `classic-hydrangea`, resumed turn 002, checkout `.local-data/worktrees/vision-v22-blacksmith-gear`, branch `codex/vision-v22-blacksmith-gear`, launch base `24129fc`. Its scope excludes the deferred alliance-popup correction.

Do not edit either active worker's checkout. On completion, the lead reviews the stable diff and saved evidence, resolves findings, delegates applicable live testing, and only then accepts/merges/pushes. The deferred popup plan is available for a separately assigned correction; this handoff does not silently expand V22. The continuous vision pipeline remains at 14/43 accepted pending those results.
